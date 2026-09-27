import os
import sys
import json
import numpy as np
import tensorflow as tf
import matplotlib.pyplot as plt
import seaborn as sns
from sklearn.metrics import roc_curve, auc, precision_recall_curve, confusion_matrix, f1_score, precision_score, recall_score
import logging

# Ensure parent directory is in sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

CLASS_NAMES = ['AF', 'Tachycardia', 'Bradycardia', 'Hypoxemia', 'Fever']

def compute_masked_macro_f1(y_true, y_pred_prob, threshold=0.5):
    """Computes F1-score for each class and overall macro F1 ignoring -1 labels."""
    f1_list = []
    for c in range(y_true.shape[1]):
        mask = y_true[:, c] != -1
        if np.sum(mask) > 0 and np.sum(y_true[mask, c] == 1) > 0:
            y_t_clean = y_true[mask, c]
            y_p_clean = (y_pred_prob[mask, c] >= threshold).astype(int)
            f1 = f1_score(y_t_clean, y_p_clean, zero_division=0)
            f1_list.append(f1)
        else:
            f1_list.append(0.0)
    return np.mean(f1_list), f1_list

def tune_thresholds(y_val, y_val_pred_prob):
    """Tunes decision thresholds on validation set to maximize per-class F1-score."""
    optimal_thresholds = {}
    for i, name in enumerate(CLASS_NAMES):
        best_threshold = 0.5
        best_f1 = 0.0
        mask = y_val[:, i] != -1
        
        # Only tune if there are positive samples in validation set
        if np.sum(mask) > 0 and np.sum(y_val[mask, i] == 1) > 0:
            y_t_clean = y_val[mask, i]
            y_p_clean_prob = y_val_pred_prob[mask, i]
            
            for t in np.linspace(0.01, 0.99, 99):
                preds = (y_p_clean_prob >= t).astype(int)
                f1 = f1_score(y_t_clean, preds, zero_division=0)
                if f1 > best_f1:
                    best_f1 = f1
                    best_threshold = float(t)
            logger.info(f"Class {name}: tuned threshold = {best_threshold:.2f} (Val F1 = {best_f1:.4f})")
        else:
            logger.info(f"Class {name} has no positive validation samples, defaulting threshold to 0.5")
            
        optimal_thresholds[name] = best_threshold
        
    return optimal_thresholds

def evaluate_performance(y_true, y_pred_prob, thresholds):
    """Computes all required metrics for each class on test set."""
    metrics = {}
    for i, name in enumerate(CLASS_NAMES):
        mask = y_true[:, i] != -1
        t = thresholds[name]
        
        if np.sum(mask) > 0:
            y_t_clean = y_true[mask, i]
            y_p_clean_prob = y_pred_prob[mask, i]
            y_p_clean_bin = (y_p_clean_prob >= t).astype(int)
            
            # Precision, Recall, F1
            prec = precision_score(y_t_clean, y_p_clean_bin, zero_division=0)
            rec = recall_score(y_t_clean, y_p_clean_bin, zero_division=0)
            f1 = f1_score(y_t_clean, y_p_clean_bin, zero_division=0)
            
            # AUROC
            try:
                fpr, tpr, _ = roc_curve(y_t_clean, y_p_clean_prob)
                auroc_val = auc(fpr, tpr)
            except Exception:
                auroc_val = 0.5
                
            # AUPRC
            try:
                precision_vals, recall_vals, _ = precision_recall_curve(y_t_clean, y_p_clean_prob)
                auprc_val = auc(recall_vals, precision_vals)
            except Exception:
                auprc_val = 0.0
                
            metrics[name] = {
                'precision': prec,
                'recall': rec,
                'f1': f1,
                'auroc': auroc_val,
                'auprc': auprc_val,
                'support': int(np.sum(y_t_clean == 1))
            }
        else:
            metrics[name] = {
                'precision': 0.0,
                'recall': 0.0,
                'f1': 0.0,
                'auroc': 0.5,
                'auprc': 0.0,
                'support': 0
            }
    return metrics

def run_evaluation(model_path="models/retrained_1000/best_retrained_model.keras",
                   data_path="dataset/retrain_dataset.npz",
                   plot_dir="docs/plots"):
    os.makedirs(plot_dir, exist_ok=True)
    
    # 1. Load data and models
    logger.info("Loading model and test data...")
    model = tf.keras.models.load_model(model_path, compile=False)
    data = np.load(data_path)
    
    X_val_ecg, X_val_vit, y_val = data["X_val_ecg"], data["X_val_vit"], data["y_val"]
    X_test_ecg, X_test_vit, y_test = data["X_test_ecg"], data["X_test_vit"], data["y_test"]
    
    # 2. Tune Thresholds on Val Set
    y_val_pred_prob = model.predict([X_val_ecg, X_val_vit])
    optimal_thresholds = tune_thresholds(y_val, y_val_pred_prob)
    
    # Save thresholds
    with open("models/retrained_1000/optimal_thresholds.json", "w", encoding="utf-8") as f:
        json.dump(optimal_thresholds, f, indent=4)
        
    # 3. Predict on Test Set
    y_test_pred_prob = model.predict([X_test_ecg, X_test_vit])
    
    # Apply thresholds
    y_test_pred_bin = np.zeros_like(y_test_pred_prob)
    for i, name in enumerate(CLASS_NAMES):
        t = optimal_thresholds[name]
        y_test_pred_bin[:, i] = (y_test_pred_prob[:, i] >= t).astype(int)
        
    # 4. Calculate metrics
    metrics = evaluate_performance(y_test, y_test_pred_prob, optimal_thresholds)
    
    # Compute overall metrics (Macro-F1, Micro-F1, Hamming Loss)
    # Mask out -1s for overall micro/macro
    y_test_flat_true = []
    y_test_flat_pred = []
    y_test_flat_prob = []
    
    for i in range(len(CLASS_NAMES)):
        mask = y_test[:, i] != -1
        y_test_flat_true.extend(y_test[mask, i])
        y_test_flat_pred.extend(y_test_pred_bin[mask, i])
        y_test_flat_prob.extend(y_test_pred_prob[mask, i])
        
    y_test_flat_true = np.array(y_test_flat_true)
    y_test_flat_pred = np.array(y_test_flat_pred)
    y_test_flat_prob = np.array(y_test_flat_prob)
    
    micro_f1 = f1_score(y_test_flat_true, y_test_flat_pred, zero_division=0)
    macro_f1 = np.mean([metrics[name]['f1'] for name in CLASS_NAMES])
    hamming_loss = np.mean(y_test_flat_true != y_test_flat_pred)
    
    # 5. Generate Plots
    # ROC Curves
    plt.figure(figsize=(10, 8))
    for i, name in enumerate(CLASS_NAMES):
        mask = y_test[:, i] != -1
        if np.sum(y_test[mask, i] == 1) > 0:
            fpr, tpr, _ = roc_curve(y_test[mask, i], y_test_pred_prob[mask, i])
            roc_auc = auc(fpr, tpr)
            plt.plot(fpr, tpr, label=f"{name} (AUC = {roc_auc:.4f})")
    plt.plot([0, 1], [0, 1], 'k--', alpha=0.5)
    plt.xlabel('1 - Specificity')
    plt.ylabel('Sensitivity')
    plt.title('ROC Curves (Retrained Model)')
    plt.legend(loc="lower right")
    plt.grid(True)
    plt.tight_layout()
    plt.savefig(os.path.join(plot_dir, "roc_curves.png"), dpi=150)
    plt.close()
    
    # Precision-Recall Curves
    plt.figure(figsize=(10, 8))
    for i, name in enumerate(CLASS_NAMES):
        mask = y_test[:, i] != -1
        if np.sum(y_test[mask, i] == 1) > 0:
            precision, recall, _ = precision_recall_curve(y_test[mask, i], y_test_pred_prob[mask, i])
            pr_auc = auc(recall, precision)
            plt.plot(recall, precision, label=f"{name} (AUC = {pr_auc:.4f})")
    plt.xlabel('Recall')
    plt.ylabel('Precision')
    plt.title('Precision-Recall Curves (Retrained Model)')
    plt.legend(loc="lower left")
    plt.grid(True)
    plt.tight_layout()
    plt.savefig(os.path.join(plot_dir, "precision_recall_curves.png"), dpi=150)
    plt.close()
    
    # Confusion Matrices
    fig, axes = plt.subplots(2, 3, figsize=(15, 10))
    axes = axes.ravel()
    for i, name in enumerate(CLASS_NAMES):
        mask = y_test[:, i] != -1
        cm = confusion_matrix(y_test[mask, i], y_test_pred_bin[mask, i])
        sns.heatmap(cm, annot=True, fmt='d', cmap='Blues', ax=axes[i], cbar=False)
        axes[i].set_title(f"{name} Confusion Matrix")
        axes[i].set_xlabel('Predicted')
        axes[i].set_ylabel('True')
    axes[-1].axis('off')  # Turn off the empty slot
    plt.tight_layout()
    plt.savefig(os.path.join(plot_dir, "confusion_matrix.png"), dpi=150)
    plt.close()
    
    # Write Evaluation Report
    report_path = "reports/evaluation_report.md"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("# Model Evaluation Report (Retrained on 1,000 Samples)\n\n")
        f.write(f"- **Overall Macro-F1**: {macro_f1:.4f}\n")
        f.write(f"- **Overall Micro-F1**: {micro_f1:.4f}\n")
        f.write(f"- **Hamming Loss**: {hamming_loss:.4f}\n\n")
        
        f.write("## Per-Class Evaluation Metrics\n\n")
        f.write("| Condition | Precision | Recall | F1 | AUROC | AUPRC | Support |\n")
        f.write("| --- | ---: | ---: | ---: | ---: | ---: | ---: |\n")
        for name in CLASS_NAMES:
            m = metrics[name]
            f.write(f"| {name} | {m['precision']:.4f} | {m['recall']:.4f} | {m['f1']:.4f} | {m['auroc']:.4f} | {m['auprc']:.4f} | {m['support']} |\n")
        f.write(f"| **Macro-F1** | | | {macro_f1:.4f} | | | |\n")
        
    print(f"Evaluation report written to {report_path}")
    
    # 6. Compare with Existing Model
    run_comparison(model, X_test_ecg, X_test_vit, y_test, macro_f1, micro_f1, hamming_loss, metrics)
    
    # 7. Ablation Study
    run_ablation_study(model, X_test_ecg, X_test_vit, y_test, optimal_thresholds)
    
    # 8. Error Analysis
    run_error_analysis(y_test, y_test_pred_bin, y_test_pred_prob, X_test_vit)

def run_comparison(retrained_model, X_test_ecg, X_test_vit, y_test, r_macro, r_micro, r_hamming, r_metrics):
    """Compares retrained model vs existing 10-class model on the test split."""
    logger.info("Running comparison against existing model...")
    existing_model_path = "models/best_ecg_model.keras"
    
    if not os.path.exists(existing_model_path):
        logger.warning(f"Existing model not found at {existing_model_path}. Skipping direct comparison.")
        return
        
    existing_model = tf.keras.models.load_model(existing_model_path, compile=False)
    y_exist_pred_prob = existing_model.predict([X_test_ecg, X_test_vit])
    
    # Existing model output mapping:
    # Index 3: AFib -> AF
    # Index 4: Bradycardia -> Bradycardia
    # Index 5: Tachycardia -> Tachycardia
    # Hypoxemia: N/A (0.0)
    # Fever: N/A (0.0)
    
    # Apply threshold 0.5 for existing model
    y_exist_pred_bin = np.zeros_like(y_test)
    y_exist_pred_bin[:, 0] = (y_exist_pred_prob[:, 3] >= 0.5).astype(int)  # AF
    y_exist_pred_bin[:, 1] = (y_exist_pred_prob[:, 5] >= 0.5).astype(int)  # Tachy
    y_exist_pred_bin[:, 2] = (y_exist_pred_prob[:, 4] >= 0.5).astype(int)  # Brady
    # Hypoxemia and Fever are not predicted by existing model (set to 0)
    
    # Compute metrics for existing model
    exist_metrics = {}
    class_indices_exist = [3, 5, 4]  # AF, Tachy, Brady
    
    for i, name in enumerate(CLASS_NAMES[:3]):
        mask = y_test[:, i] != -1
        y_t = y_test[mask, i]
        y_p = y_exist_pred_bin[mask, i]
        exist_metrics[name] = f1_score(y_t, y_p, zero_division=0)
        
    exist_metrics['Hypoxemia'] = 0.0
    exist_metrics['Fever'] = 0.0
    
    exist_macro = np.mean([exist_metrics[name] for name in CLASS_NAMES])
    
    # Overall micro F1 and Hamming for existing model on known targets
    y_test_flat_true = []
    y_exist_flat_pred = []
    for i in range(len(CLASS_NAMES)):
        mask = y_test[:, i] != -1
        y_test_flat_true.extend(y_test[mask, i])
        y_exist_flat_pred.extend(y_exist_pred_bin[mask, i])
        
    y_test_flat_true = np.array(y_test_flat_true)
    y_exist_flat_pred = np.array(y_exist_flat_pred)
    
    exist_micro = f1_score(y_test_flat_true, y_exist_flat_pred, zero_division=0)
    exist_hamming = np.mean(y_test_flat_true != y_exist_flat_pred)
    
    # Write comparison report
    report_path = "reports/model_comparison.md"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("# Model Comparison Report: Existing vs Retrained\n\n")
        f.write("| Metric | Existing Model | Retrained Model |\n")
        f.write("| --- | ---: | ---: |\n")
        f.write(f"| **Macro-F1** | {exist_macro:.4f} | {r_macro:.4f} |\n")
        f.write(f"| **Micro-F1** | {exist_micro:.4f} | {r_micro:.4f} |\n")
        f.write(f"| **Hamming Loss** | {exist_hamming:.4f} | {r_hamming:.4f} |\n")
        f.write(f"| **AF F1** | {exist_metrics['AF']:.4f} | {r_metrics['AF']['f1']:.4f} |\n")
        f.write(f"| **Tachycardia F1** | {exist_metrics['Tachycardia']:.4f} | {r_metrics['Tachycardia']['f1']:.4f} |\n")
        f.write(f"| **Bradycardia F1** | {exist_metrics['Bradycardia']:.4f} | {r_metrics['Bradycardia']['f1']:.4f} |\n")
        f.write(f"| **Hypoxemia F1** | {exist_metrics['Hypoxemia']:.4f} | {r_metrics['Hypoxemia']['f1']:.4f} |\n")
        f.write(f"| **Fever F1** | {exist_metrics['Fever']:.4f} | {r_metrics['Fever']['f1']:.4f} |\n\n")
        
        f.write("## Findings\n")
        if r_macro > exist_macro:
            f.write("- **The Retrained model outperforms the existing model in overall Macro-F1.**\n")
            f.write("- This improvement is primarily driven by: (1) multi-label training across five distinct clinical targets, (2) the introduction of clinical vitals (like SpO₂ and Temperature) in the training data, allowing supervised prediction of Hypoxemia and Fever, and (3) threshold tuning on the validation set.\n")
        else:
            f.write("- The retrained model has similar or lower performance, which might be due to the limited training sample size (1,000 samples) compared to the original dataset.\n")
            
    print(f"Comparison report written to {report_path}")

def run_ablation_study(model, X_test_ecg, X_test_vit, y_test, thresholds):
    """Evaluates the model under different input masking scenarios to test multimodal fusion."""
    logger.info("Running ablation study...")
    
    # Baseline defaults
    NORMAL_VITALS_LIST = [50.0, 0.0, 75.0, 98.0, 36.8, 120.0, 80.0, 15.0, 0.0]
    
    # 1. ECG-only: Vitals set to normal defaults, handcrafted features kept
    X_test_vit_ecg_only = np.copy(X_test_vit)
    for i in range(len(X_test_vit_ecg_only)):
        # replace the first 9 vitals with default values
        X_test_vit_ecg_only[i, :9] = NORMAL_VITALS_LIST
        
    y_pred_ecg_only = model.predict([X_test_ecg, X_test_vit_ecg_only])
    f1_ecg_only, _ = compute_masked_macro_f1(y_test, y_pred_ecg_only)
    
    # 2. Vitals-only: ECG set to all zeros, handcrafted features set to all zeros
    X_test_ecg_zeros = np.zeros_like(X_test_ecg)
    X_test_vit_vitals_only = np.copy(X_test_vit)
    X_test_vit_vitals_only[:, 9:] = 0.0  # Zero out handcrafted features
    
    y_pred_vitals_only = model.predict([X_test_ecg_zeros, X_test_vit_vitals_only])
    f1_vitals_only, _ = compute_masked_macro_f1(y_test, y_pred_vitals_only)
    
    # 3. ECG + HR + SpO2: Keep ECG and HR/SpO2, set other vitals to defaults
    X_test_vit_partial = np.copy(X_test_vit)
    for i in range(len(X_test_vit_partial)):
        hr = X_test_vit[i, 2]
        spo2 = X_test_vit[i, 3]
        X_test_vit_partial[i, :9] = NORMAL_VITALS_LIST
        X_test_vit_partial[i, 2] = hr
        X_test_vit_partial[i, 3] = spo2
        
    y_pred_partial = model.predict([X_test_ecg, X_test_vit_partial])
    f1_partial, _ = compute_masked_macro_f1(y_test, y_pred_partial)
    
    # 4. Full multimodal: ECG + PPG + HR + SpO2 + Temp
    y_pred_full = model.predict([X_test_ecg, X_test_vit])
    f1_full, per_class_f1_full = compute_masked_macro_f1(y_test, y_pred_full)
    
    # Write ablation study report
    report_path = "reports/ablation_study.md"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("# Ablation Study: Multimodal Fusion Verification\n\n")
        f.write("| Experiment | Description | Test Macro-F1 |\n")
        f.write("| --- | --- | ---: |\n")
        f.write(f"| **A** | ECG Only (Clinical vitals masked) | {f1_ecg_only:.4f} |\n")
        f.write(f"| **B** | Vitals Only (ECG wave and features masked) | {f1_vitals_only:.4f} |\n")
        f.write(f"| **C** | ECG + HR + SpO₂ (Partial multimodal) | {f1_partial:.4f} |\n")
        f.write(f"| **D** | ECG + PPG + HR + SpO₂ + Temp (Full Fusion) | {f1_full:.4f} |\n\n")
        
        f.write("## Ablation Discussion\n")
        if f1_full > f1_ecg_only and f1_full > f1_vitals_only:
            f.write("- **Multimodal Fusion successfully improves classification performance.** Full fusion outperforms both unimodal branches.\n")
        else:
            f.write("- Multimodal fusion did not lead to a significant increase in Macro-F1 compared to unimodal inputs. This could be due to missing values and the imputation strategy.\n")
            
    print(f"Ablation study report written to {report_path}")

def run_error_analysis(y_true, y_pred_bin, y_pred_prob, X_vit):
    """Performs detailed error analysis and extracts false positive/negative cases."""
    logger.info("Running error analysis...")
    report_path = "reports/error_analysis.md"
    
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("# Error Analysis Report\n\n")
        
        for i, name in enumerate(CLASS_NAMES):
            mask = y_true[:, i] != -1
            y_t = y_true[mask, i]
            y_p = y_pred_bin[mask, i]
            
            # False Positives
            fp_indices = np.where((y_t == 0) & (y_p == 1))[0]
            # False Negatives (Missed cases)
            fn_indices = np.where((y_t == 1) & (y_p == 0))[0]
            
            f.write(f"## Class: {name}\n")
            f.write(f"- **False Positives**: {len(fp_indices)} cases\n")
            f.write(f"- **False Negatives (Missed)**: {len(fn_indices)} cases\n\n")
            
            if len(fp_indices) > 0:
                f.write("### Example False Positive Cases (Vitals)\n")
                f.write("| Case | HR | SpO2 | Temp | Prob |\n")
                f.write("| --- | ---: | ---: | ---: | ---: |\n")
                for idx in fp_indices[:3]:
                    # Extract vital parameters (HR = idx 2, SpO2 = idx 3, Temp = idx 4)
                    hr = X_vit[mask][idx][2]
                    spo2 = X_vit[mask][idx][3]
                    temp = X_vit[mask][idx][4]
                    prob = y_pred_prob[mask, i][idx]
                    f.write(f"| Sample {idx} | {hr:.1f} | {spo2:.1f} | {temp:.2f} | {prob:.4f} |\n")
                f.write("\n")
                
            if len(fn_indices) > 0:
                f.write("### Example Missed Cases (Vitals)\n")
                f.write("| Case | HR | SpO2 | Temp | Prob |\n")
                f.write("| --- | ---: | ---: | ---: | ---: |\n")
                for idx in fn_indices[:3]:
                    hr = X_vit[mask][idx][2]
                    spo2 = X_vit[mask][idx][3]
                    temp = X_vit[mask][idx][4]
                    prob = y_pred_prob[mask, i][idx]
                    f.write(f"| Sample {idx} | {hr:.1f} | {spo2:.1f} | {temp:.2f} | {prob:.4f} |\n")
                f.write("\n")
                
            f.write("---\n\n")
            
    print(f"Error analysis report written to {report_path}")

if __name__ == "__main__":
    run_evaluation()
