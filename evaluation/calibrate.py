import os
import sys
import json
import numpy as np
import tensorflow as tf
from scipy.optimize import minimize
import matplotlib.pyplot as plt
from sklearn.calibration import calibration_curve

# Ensure parent directory is in sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

CLASSES = ['Normal', 'PVC', 'PAC', 'AFib', 'Bradycardia', 'Tachycardia', 'HeartBlock', 'BundleBranchBlock', 'Ischemia', 'Infarction']

def logit(p, eps=1e-7):
    p = np.clip(p, eps, 1.0 - eps)
    return np.log(p / (1.0 - p))

def sigmoid(x):
    return 1.0 / (1.0 + np.exp(-x))

def nll_loss(T, logits, labels):
    """Computes Negative Log Likelihood for Temperature Scaling."""
    scaled_logits = logits / T
    probs = sigmoid(scaled_logits)
    # Clip to avoid log(0)
    probs = np.clip(probs, 1e-7, 1.0 - 1e-7)
    loss = -labels * np.log(probs) - (1.0 - labels) * np.log(1.0 - probs)
    return np.mean(loss)

def calibrate_model(model_path="models/best_ecg_model.keras", data_path="dataset/preprocessed_data.npz", plot_dir="docs/plots"):
    """
    Learns class-wise Temperature Scaling parameters on the validation set,
    saves the calibration parameters, and plots reliability curves.
    """
    os.makedirs(plot_dir, exist_ok=True)
    
    if not os.path.exists(model_path):
        print(f"[Calibration] Error: Model not found at {model_path}")
        return
        
    print(f"[Calibration] Loading best model from {model_path}...")
    model = tf.keras.models.load_model(model_path, compile=False)
    
    print(f"[Calibration] Loading preprocessed data from {data_path}...")
    data = np.load(data_path)
    X_val_ecg, X_val_vit, y_val = data["X_val_ecg"], data["X_val_vit"], data["y_val"]
    X_test_ecg, X_test_vit, y_test = data["X_test_ecg"], data["X_test_vit"], data["y_test"]
    
    # 1. Generate validation and test predictions
    print("[Calibration] Running inference on validation and test sets...")
    val_probs = model.predict([X_val_ecg, X_val_vit], batch_size=256)
    test_probs = model.predict([X_test_ecg, X_test_vit], batch_size=256)
    
    # Convert probabilities to logits
    val_logits = logit(val_probs)
    test_logits = logit(test_probs)
    
    temperatures = {}
    calibrated_val_probs = np.zeros_like(val_probs)
    calibrated_test_probs = np.zeros_like(test_probs)
    
    print("[Calibration] Tuning temperatures per class...")
    for i, name in enumerate(CLASSES):
        class_val_logits = val_logits[:, i]
        class_val_labels = y_val[:, i]
        
        # Optimize temperature T to minimize validation NLL
        # Initial guess T=1.0, bounds between 0.1 and 10.0
        res = minimize(nll_loss, x0=[1.0], args=(class_val_logits, class_val_labels), method='L-BFGS-B', bounds=[(0.1, 10.0)])
        T_opt = float(res.x[0])
        temperatures[name] = T_opt
        print(f"  Class: {name:20s} | Opt Temperature: {T_opt:.4f}")
        
        # Apply scaling
        calibrated_val_probs[:, i] = sigmoid(class_val_logits / T_opt)
        calibrated_test_probs[:, i] = sigmoid(test_logits[:, i] / T_opt)
        
    # Save calibration parameters
    calib_path = "models/calibration_parameters.json"
    with open(calib_path, "w") as f:
        json.dump(temperatures, f, indent=2)
    print(f"[Calibration] Saved temperature parameters to {calib_path}")
    
    # 2. Plot Reliability Diagram before and after calibration on the Test Set
    plt.figure(figsize=(14, 10))
    for i, name in enumerate(CLASSES):
        if np.sum(y_test[:, i]) > 10:  # Only plot classes with sufficient samples
            # Before calibration
            prob_true_before, prob_pred_before = calibration_curve(y_test[:, i], test_probs[:, i], n_bins=10)
            # After calibration
            prob_true_after, prob_pred_after = calibration_curve(y_test[:, i], calibrated_test_probs[:, i], n_bins=10)
            
            plt.subplot(2, 5, i+1)
            plt.plot(prob_pred_before, prob_true_before, marker='o', linestyle='--', color='red', label='Uncalibrated')
            plt.plot(prob_pred_after, prob_true_after, marker='x', linestyle='-', color='green', label='Calibrated')
            plt.plot([0, 1], [0, 1], color='gray', linestyle=':')
            plt.title(name, fontsize=10)
            plt.xlabel('Mean Pred', fontsize=8)
            plt.ylabel('True Frac', fontsize=8)
            plt.grid(True)
            if i == 0:
                plt.legend(fontsize=8)
                
    plt.suptitle("Probability Calibration reliability Curves: Before vs After Temperature Scaling", fontsize=14)
    plt.tight_layout()
    plot_save_path = os.path.join(plot_dir, "calibration_reliability_comparison.png")
    plt.savefig(plot_save_path, dpi=150)
    plt.close()
    print(f"[Calibration] Saved reliability comparison plot to {plot_save_path}")

if __name__ == "__main__":
    calibrate_model()
