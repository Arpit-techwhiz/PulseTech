import os
import sys
import json
import datetime
import logging
import numpy as np
import tensorflow as tf
import matplotlib.pyplot as plt
import seaborn as sns
from sklearn.metrics import (
    roc_curve, 
    auc, 
    precision_recall_curve, 
    confusion_matrix,
    matthews_corrcoef,
    average_precision_score,
    f1_score
)
from sklearn.calibration import calibration_curve

# Ensure parent directory is in sys.path for local module imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

CLASSES = ['Normal', 'PVC', 'PAC', 'AFib', 'Bradycardia', 'Tachycardia', 'HeartBlock', 'BundleBranchBlock', 'Ischemia', 'Infarction']

def compute_multilabel_confusion_matrix(y_true, y_pred, threshold=0.5):
    """
    Computes individual 2x2 confusion matrices for each class.
    """
    cms = {}
    for i, name in enumerate(CLASSES):
        cm = confusion_matrix(y_true[:, i], y_pred[:, i] >= threshold)
        cms[name] = cm
    return cms

def compute_sensitivity_specificity(y_true, y_pred_binary):
    """
    Computes Sensitivity (Recall), Specificity, and Matthews Correlation Coefficient (MCC) for each class.
    """
    metrics = {}
    for i, name in enumerate(CLASSES):
        cm = confusion_matrix(y_true[:, i], y_pred_binary[:, i])
        tn, fp, fn, tp = cm.ravel() if cm.size == 4 else (0, 0, 0, 0)
        
        sensitivity = tp / (tp + fn) if (tp + fn) > 0 else 0
        specificity = tn / (tn + fp) if (tn + fp) > 0 else 0
        mcc = matthews_corrcoef(y_true[:, i], y_pred_binary[:, i])
        
        metrics[name] = {
            "sensitivity": sensitivity,
            "specificity": specificity,
            "mcc": mcc
        }
    return metrics

def bootstrap_confidence_intervals(y_true, y_pred_prob, thresholds, n_bootstraps=200, ci=0.95):
    """
    Computes 95% Confidence Intervals for F1-score and AUPRC using bootstrapping.
    This provides rigorous statistical backing required for medical project publication/vivas.
    """
    rng = np.random.RandomState(42)
    bootstrapped_f1s = {name: [] for name in CLASSES}
    bootstrapped_auprcs = {name: [] for name in CLASSES}
    
    logger.info("Computing bootstrap confidence intervals (n=200)...")
    for b in range(n_bootstraps):
        indices = rng.choice(len(y_true), len(y_true), replace=True)
        if len(np.unique(y_true[indices])) < 2:
            continue
            
        for i, name in enumerate(CLASSES):
            t = thresholds[name]
            y_t = y_true[indices, i]
            y_p_prob = y_pred_prob[indices, i]
            y_p_bin = (y_p_prob >= t).astype(int)
            
            # F1
            f1 = f1_score(y_t, y_p_bin, zero_division=0)
            bootstrapped_f1s[name].append(f1)
            
            # AUPRC
            if np.sum(y_t) > 0:
                auprc = average_precision_score(y_t, y_p_prob)
                bootstrapped_auprcs[name].append(auprc)
            else:
                bootstrapped_auprcs[name].append(0.0)
                
    intervals = {}
    lower_pct = (1.0 - ci) / 2.0 * 100
    upper_pct = (1.0 + ci) / 2.0 * 100
    
    for name in CLASSES:
        f1_sorted = np.sort(bootstrapped_f1s[name])
        auprc_sorted = np.sort(bootstrapped_auprcs[name])
        
        intervals[name] = {
            "f1_ci": (np.percentile(f1_sorted, lower_pct), np.percentile(f1_sorted, upper_pct)),
            "auprc_ci": (np.percentile(auprc_sorted, lower_pct), np.percentile(auprc_sorted, upper_pct))
        }
    return intervals

def compute_gradcam_1d(model, ecg_input, vitals_input, class_idx):
    """
    Computes 1D Grad-CAM for a given ECG waveform.
    Dynamically finds the last Conv1D layer.
    """
    conv_layer_name = None
    # Traverse in reverse to find the last Conv1D layer
    for layer in reversed(model.layers):
        if isinstance(layer, tf.keras.layers.Conv1D) or 'conv1d' in layer.name:
            conv_layer_name = layer.name
            break
            
    if conv_layer_name is None:
        logger.warning("No Conv1D layer found in model for Grad-CAM.")
        return np.zeros(ecg_input.shape[0])
        
    grad_model = tf.keras.models.Model(
        inputs=model.inputs,
        outputs=[model.get_layer(conv_layer_name).output, model.output]
    )
    
    ecg_batch = np.expand_dims(ecg_input, axis=0)
    vitals_batch = np.expand_dims(vitals_input, axis=0)
    
    with tf.GradientTape() as tape:
        conv_outputs, predictions = grad_model([ecg_batch, vitals_batch])
        loss = predictions[0, class_idx]
        
    grads = tape.gradient(loss, conv_outputs)
    pooled_grads = tf.reduce_mean(grads, axis=(0, 1))
    
    conv_outputs = conv_outputs[0]
    gradcam = tf.reduce_sum(pooled_grads * conv_outputs, axis=-1)
    gradcam = tf.maximum(gradcam, 0.0) # Apply ReLU
    
    max_val = tf.reduce_max(gradcam)
    if max_val > 0:
        gradcam = gradcam / max_val
        
    # Interpolate back to length of ECG input
    gradcam_interp = np.interp(
        np.linspace(0, len(gradcam)-1, len(ecg_input)),
        np.arange(len(gradcam)),
        gradcam.numpy()
    )
    return gradcam_interp

def compute_vital_feature_importance(model, ecg_input, vitals_input, class_idx):
    """
    Computes vital sign importance using saliency mapping (gradients of output w.r.t input).
    """
    ecg_batch = tf.convert_to_tensor(np.expand_dims(ecg_input, axis=0), dtype=tf.float32)
    vitals_batch = tf.convert_to_tensor(np.expand_dims(vitals_input, axis=0), dtype=tf.float32)
    
    with tf.GradientTape() as tape:
        tape.watch(vitals_batch)
        predictions = model([ecg_batch, vitals_batch])
        loss = predictions[0, class_idx]
        
    grads = tape.gradient(loss, vitals_batch)
    saliency = tf.abs(grads)[0][:9].numpy() # Gradients for the 9 synthesized vitals
    sum_saliency = np.sum(saliency)
    if sum_saliency > 0:
        saliency = saliency / sum_saliency
    return saliency

def tune_thresholds(y_true, y_pred_prob):
    """
    Searches for optimal thresholds per class to maximize per-class F1-score on the validation set.
    """
    optimal_thresholds = {}
    for i, name in enumerate(CLASSES):
        best_threshold = 0.5
        best_f1 = 0.0
        for t in np.linspace(0.05, 0.95, 91):
            preds = (y_pred_prob[:, i] >= t).astype(int)
            tp = np.sum((y_true[:, i] == 1) & (preds == 1))
            fp = np.sum((y_true[:, i] == 0) & (preds == 1))
            fn = np.sum((y_true[:, i] == 1) & (preds == 0))
            
            precision = tp / (tp + fp) if (tp + fp) > 0 else 0
            recall = tp / (tp + fn) if (tp + fn) > 0 else 0
            f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0
            
            if f1 > best_f1:
                best_f1 = f1
                best_threshold = float(t)
        optimal_thresholds[name] = best_threshold
        logger.info(f"Class: {name:25s} | Optimal Threshold: {best_threshold:.2f} | Best Validation F1: {best_f1:.4f}")
    return optimal_thresholds

def evaluate_best_model(model_path="models/best_ecg_model.keras", data_path="dataset/preprocessed_data.npz", plot_dir="docs/plots"):
    """
    Runs multi-label evaluation, reliability curves, 1D Grad-CAM explainability,
    Matthews Correlation Coefficient (MCC), AUPRC, bootstrap CIs, and saves clinical performance report.
    """
    os.makedirs(plot_dir, exist_ok=True)
    
    if not os.path.exists(model_path):
        logger.error(f"Best model not found at {model_path}. Train a model first.")
        return
        
    logger.info(f"Loading best model from {model_path}...")
    model = tf.keras.models.load_model(model_path, compile=False)
    
    logger.info(f"Loading data from {data_path}...")
    data = np.load(data_path)
    X_val_ecg, X_val_vit, y_val = data["X_val_ecg"], data["X_val_vit"], data["y_val"]
    X_test_ecg, X_test_vit, y_test = data["X_test_ecg"], data["X_test_vit"], data["y_test"]
    
    # 1. Run predictions on validation set for threshold tuning
    logger.info("Running predictions on validation set for threshold tuning...")
    y_val_pred_prob = model.predict([X_val_ecg, X_val_vit], batch_size=256)
    optimal_thresholds = tune_thresholds(y_val, y_val_pred_prob)
    
    # Save optimal thresholds to models directory
    thresholds_path = os.path.join(os.path.dirname(model_path), "optimal_thresholds.json")
    with open(thresholds_path, "w") as f:
        json.dump(optimal_thresholds, f, indent=2)
    logger.info(f"Saved optimal thresholds to {thresholds_path}")
    
    # 2. Run predictions on test set
    logger.info("Running predictions on test set...")
    y_pred_prob = model.predict([X_test_ecg, X_test_vit], batch_size=256)
    
    # Apply optimal class-specific thresholds
    y_pred_binary = np.zeros_like(y_pred_prob, dtype=int)
    for i, name in enumerate(CLASSES):
        t = optimal_thresholds[name]
        y_pred_binary[:, i] = (y_pred_prob[:, i] >= t).astype(int)
    
    # 3. Compute Metrics
    logger.info("Computing Sensitivity, Specificity, and MCC...")
    sens_spec_metrics = compute_sensitivity_specificity(y_test, y_pred_binary)
    bootstrap_cis = bootstrap_confidence_intervals(y_test, y_pred_prob, optimal_thresholds)
    
    # 4. Plot ROC and PR curves
    logger.info("Generating ROC and Precision-Recall Curves...")
    plt.figure(figsize=(12, 10))
    for i, name in enumerate(CLASSES):
        fpr, tpr, _ = roc_curve(y_test[:, i], y_pred_prob[:, i])
        roc_auc = auc(fpr, tpr)
        plt.plot(fpr, tpr, label=f'{name} (AUROC = {roc_auc:.4f})')
        
    plt.plot([0, 1], [0, 1], color='gray', linestyle='--')
    plt.xlabel('1 - Specificity')
    plt.ylabel('Sensitivity (True Positive Rate)')
    plt.title('Multi-Label Receiver Operating Characteristic (ROC) Curves')
    plt.legend(loc="lower right")
    plt.grid(True)
    plt.tight_layout()
    roc_path = os.path.join(plot_dir, "roc_curves.png")
    plt.savefig(roc_path, dpi=150)
    plt.close()
    
    plt.figure(figsize=(12, 10))
    for i, name in enumerate(CLASSES):
        precision, recall, _ = precision_recall_curve(y_test[:, i], y_pred_prob[:, i])
        pr_auc = average_precision_score(y_test[:, i], y_pred_prob[:, i])
        plt.plot(recall, precision, label=f'{name} (AUPRC = {pr_auc:.4f})')
        
    plt.xlabel('Recall (Sensitivity)')
    plt.ylabel('Precision (PPV)')
    plt.title('Multi-Label Precision-Recall (PR) Curves')
    plt.legend(loc="lower left")
    plt.grid(True)
    plt.tight_layout()
    pr_path = os.path.join(plot_dir, "precision_recall_curves.png")
    plt.savefig(pr_path, dpi=150)
    plt.close()
    
    # 5. Plot Reliability Calibration Curves
    logger.info("Generating Reliability Calibration Curves...")
    plt.figure(figsize=(10, 8))
    for i, name in enumerate(CLASSES):
        if np.sum(y_test[:, i]) > 5:
            prob_true, prob_pred = calibration_curve(y_test[:, i], y_pred_prob[:, i], n_bins=10)
            plt.plot(prob_pred, prob_true, marker='o', label=f'{name}')
            
    plt.plot([0, 1], [0, 1], color='gray', linestyle='--', label='Perfectly Calibrated')
    plt.xlabel('Mean Predicted Probability')
    plt.ylabel('Fraction of Positives')
    plt.title('Multi-Label Probability Calibration Reliability Curves')
    plt.legend(loc="lower right")
    plt.grid(True)
    plt.tight_layout()
    calib_path = os.path.join(plot_dir, "calibration_curves.png")
    plt.savefig(calib_path, dpi=150)
    plt.close()
    
    # 6. Generate 1D Grad-CAM Explainability Map
    logger.info("Generating Explainability Grad-CAM map for Infarction beat...")
    infarction_indices = np.where(y_test[:, 9] == 1)[0]
    if len(infarction_indices) > 0:
        sample_idx = infarction_indices[0]
        ecg_sample = X_test_ecg[sample_idx]
        vitals_sample = X_test_vit[sample_idx]
        
        gradcam = compute_gradcam_1d(model, ecg_sample, vitals_sample, class_idx=9)
        
        plt.figure(figsize=(10, 5))
        plt.plot(ecg_sample[:, 0], color='blue', label='ECG Signal')
        plt.scatter(
            np.arange(len(ecg_sample)), ecg_sample[:, 0],
            c=gradcam, cmap='Oranges', s=50, zorder=3,
            label='Grad-CAM Activation'
        )
        plt.colorbar(label='Feature Importance Weight')
        plt.title('1D Grad-CAM Activation Map (Target: Myocardial Infarction)')
        plt.xlabel('Waveform Samples (100 Hz)')
        plt.ylabel('Amplitude')
        plt.legend()
        plt.grid(True)
        plt.tight_layout()
        gradcam_path = os.path.join(plot_dir, "gradcam_explainability.png")
        plt.savefig(gradcam_path, dpi=150)
        plt.close()
        logger.info(f"Saved Grad-CAM explainability map to {gradcam_path}")
        
        # 7. Vitals Feature Importance Saliency
        logger.info("Generating Vitals Feature Importance chart...")
        vital_names = ['Age', 'Gender', 'HR', 'SpO2', 'Temp', 'BP Sys', 'BP Dia', 'Resp Rate', 'Symptom']
        saliency = compute_vital_feature_importance(model, ecg_sample, vitals_sample, class_idx=9)
        
        plt.figure(figsize=(8, 5))
        sns.barplot(x=saliency, y=vital_names, palette='viridis')
        plt.title('Vital Signs Contribution Importance (Target: Myocardial Infarction)')
        plt.xlabel('Relative Gradient Contribution')
        plt.tight_layout()
        saliency_path = os.path.join(plot_dir, "vitals_importance.png")
        plt.savefig(saliency_path, dpi=150)
        plt.close()
        logger.info(f"Saved Vitals Importance plot to {saliency_path}")
        
    # Save clinical evaluation report
    report_path = "docs/performance_report.md"
    with open(report_path, "w") as f:
        f.write("# PulseTech Multimodal Edge AI - Clinical Performance Report\n\n")
        f.write(f"- **Evaluation Date**: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"- **Primary Classifier**: {model.name}\n\n")
        
        f.write("## Per-Class Sensitivity, Specificity, MCC, and Tuned Decision Thresholds\n\n")
        f.write("| Class Name | Sensitivity (Recall) | Specificity | MCC | Optimal Threshold | F1-Score [95% CI] | AUPRC [95% CI] |\n")
        f.write("| --- | --- | --- | --- | --- | --- | --- |\n")
        for i, name in enumerate(CLASSES):
            sens = sens_spec_metrics[name]["sensitivity"]
            spec = sens_spec_metrics[name]["specificity"]
            mcc = sens_spec_metrics[name]["mcc"]
            t = optimal_thresholds[name]
            
            # Calculate validation F1 for this class at optimal threshold
            preds_val = (y_val_pred_prob[:, i] >= t).astype(int)
            tp = np.sum((y_val[:, i] == 1) & (preds_val == 1))
            fp = np.sum((y_val[:, i] == 0) & (preds_val == 1))
            fn = np.sum((y_val[:, i] == 1) & (preds_val == 0))
            prec_val = tp / (tp + fp) if (tp + fp) > 0 else 0
            rec_val = tp / (tp + fn) if (tp + fn) > 0 else 0
            f1_val = 2 * prec_val * rec_val / (prec_val + rec_val) if (prec_val + rec_val) > 0 else 0
            
            f1_ci = bootstrap_cis[name]["f1_ci"]
            auprc_ci = bootstrap_cis[name]["auprc_ci"]
            
            f.write(f"| {name} | {sens:.4f} | {spec:.4f} | {mcc:.4f} | {t:.2f} | {f1_val:.4f} [{f1_ci[0]:.3f}, {f1_ci[1]:.3f}] | {average_precision_score(y_test[:, i], y_pred_prob[:, i]):.4f} [{auprc_ci[0]:.3f}, {auprc_ci[1]:.3f}] |\n")
            
        f.write("\n## Evaluation Visualizations\n\n")
        f.write("### Receiver Operating Characteristic (ROC) Curves\n")
        f.write("![ROC Curves](plots/roc_curves.png)\n\n")
        f.write("### Precision-Recall Curves\n")
        f.write("![PR Curves](plots/precision_recall_curves.png)\n\n")
        f.write("### Reliability Calibration Curves\n")
        f.write("![Calibration Curves](plots/calibration_curves.png)\n\n")
        if len(infarction_indices) > 0:
            f.write("### Explainable AI - Grad-CAM ECG Map\n")
            f.write("![Grad-CAM Map](plots/gradcam_explainability.png)\n\n")
            f.write("### Vital Parameters Contribution Saliency\n")
            f.write("![Vitals Saliency](plots/vitals_importance.png)\n\n")
            
    logger.info(f"Saved Clinical Performance Report to {report_path}")

if __name__ == "__main__":
    evaluate_best_model()
