import os
import sys
import numpy as np
import pandas as pd
import tensorflow as tf
from sklearn.metrics import f1_score
import logging

# Ensure parent directory is in sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from models.architectures import build_hybrid_cnn_bilstm

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Loss Functions
def masked_bce_loss():
    """Calculates standard Binary Cross-Entropy ignoring -1 labels."""
    def loss(y_true, y_pred):
        mask = tf.cast(tf.not_equal(y_true, -1), tf.float32)
        y_true_clean = tf.where(tf.equal(y_true, -1), tf.zeros_like(y_true), y_true)
        y_pred = tf.clip_by_value(y_pred, 1e-7, 1.0 - 1e-7)
        bce = -y_true_clean * tf.math.log(y_pred) - (1.0 - y_true_clean) * tf.math.log(1.0 - y_pred)
        masked_bce = bce * mask
        return tf.reduce_sum(masked_bce, axis=-1) / (tf.reduce_sum(mask, axis=-1) + 1e-7)
    return loss

def masked_weighted_bce_loss(pos_weights):
    """Calculates weighted BCE ignoring -1 labels."""
    def loss(y_true, y_pred):
        mask = tf.cast(tf.not_equal(y_true, -1), tf.float32)
        y_true_clean = tf.where(tf.equal(y_true, -1), tf.zeros_like(y_true), y_true)
        y_pred = tf.clip_by_value(y_pred, 1e-7, 1.0 - 1e-7)
        bce = -pos_weights * y_true_clean * tf.math.log(y_pred) - (1.0 - y_true_clean) * tf.math.log(1.0 - y_pred)
        masked_bce = bce * mask
        return tf.reduce_sum(masked_bce, axis=-1) / (tf.reduce_sum(mask, axis=-1) + 1e-7)
    return loss

def masked_focal_loss(gamma=2.0, alpha=0.25):
    """Calculates Focal Loss ignoring -1 labels."""
    def loss(y_true, y_pred):
        mask = tf.cast(tf.not_equal(y_true, -1), tf.float32)
        y_true_clean = tf.where(tf.equal(y_true, -1), tf.zeros_like(y_true), y_true)
        y_pred = tf.clip_by_value(y_pred, 1e-7, 1.0 - 1e-7)
        p_t = y_true_clean * y_pred + (1.0 - y_true_clean) * (1.0 - y_pred)
        focal_weight = alpha * y_true_clean * tf.pow(1.0 - p_t, gamma) + (1.0 - alpha) * (1.0 - y_true_clean) * tf.pow(1.0 - p_t, gamma)
        cross_entropy = -y_true_clean * tf.math.log(y_pred) - (1.0 - y_true_clean) * tf.math.log(1.0 - y_pred)
        masked_loss = focal_weight * cross_entropy * mask
        return tf.reduce_sum(masked_loss, axis=-1) / (tf.reduce_sum(mask, axis=-1) + 1e-7)
    return loss

def compute_masked_macro_f1(y_true, y_pred_prob, threshold=0.5):
    """Computes F1-score for each class and overall macro F1 ignoring -1 labels."""
    f1_list = []
    class_names = ['AF', 'Tachycardia', 'Bradycardia', 'Hypoxemia', 'Fever']
    
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

def retrain_pipeline(data_path="dataset/retrain_dataset.npz", out_model_dir="models/retrained_1000"):
    os.makedirs(out_model_dir, exist_ok=True)
    
    # 1. Load data
    logger.info(f"Loading dataset from {data_path}...")
    data = np.load(data_path)
    X_train_ecg, X_train_vit, y_train = data["X_train_ecg"], data["X_train_vit"], data["y_train"]
    X_val_ecg, X_val_vit, y_val = data["X_val_ecg"], data["X_val_vit"], data["y_val"]
    
    logger.info(f"Train ECG shape: {X_train_ecg.shape}, Vitals shape: {X_train_vit.shape}, Labels shape: {y_train.shape}")
    
    # Calculate class imbalance and weights (excluding -1)
    pos_weights_list = []
    for c in range(y_train.shape[1]):
        col = y_train[:, c]
        n_pos = np.sum(col == 1)
        n_neg = np.sum(col == 0)
        weight = n_neg / (n_pos + 1e-7)
        pos_weights_list.append(weight)
    pos_weights = np.array(pos_weights_list, dtype=np.float32)
    logger.info(f"Class imbalance positive weights: {pos_weights_list}")
    
    # Define loss function candidates
    loss_candidates = {
        "Standard_BCE": masked_bce_loss(),
        "Weighted_BCE": masked_weighted_bce_loss(pos_weights),
        "Focal_Loss": masked_focal_loss(gamma=2.0, alpha=0.25)
    }
    
    best_macro_f1 = -1.0
    best_loss_name = None
    best_model_history = None
    
    for name, loss_fn in loss_candidates.items():
        logger.info("\n" + "="*50)
        logger.info(f"Training Model with Loss: {name}")
        logger.info("="*50)
        
        # Build 5-output model with dynamic vitals shape
        vitals_dim = X_train_vit.shape[1]
        model = build_hybrid_cnn_bilstm(ecg_shape=(90, 1), vitals_shape=(vitals_dim,), num_classes=5)
        
        # Compile with AdamW
        model.compile(
            optimizer=tf.keras.optimizers.AdamW(learning_rate=2e-4, weight_decay=1e-4),
            loss=loss_fn,
            metrics=['binary_accuracy']
        )
        
        # Callbacks
        checkpoint_path = os.path.join(out_model_dir, f"checkpoint_{name}.keras")
        callbacks = [
            tf.keras.callbacks.EarlyStopping(
                monitor='val_loss', 
                patience=10, 
                restore_best_weights=True,
                verbose=1
            ),
            tf.keras.callbacks.ReduceLROnPlateau(
                monitor='val_loss', 
                factor=0.5, 
                patience=3, 
                min_lr=1e-5,
                verbose=1
            ),
            tf.keras.callbacks.ModelCheckpoint(
                filepath=checkpoint_path, 
                monitor='val_loss', 
                save_best_only=True,
                verbose=1
            )
        ]
        
        history = model.fit(
            [X_train_ecg, X_train_vit], y_train,
            validation_data=([X_val_ecg, X_val_vit], y_val),
            epochs=50,
            batch_size=32,
            callbacks=callbacks,
            verbose=1
        )
        
        # Load best weights
        if os.path.exists(checkpoint_path):
            model = tf.keras.models.load_model(checkpoint_path, compile=False)
            
        # Predict on validation set
        y_val_pred = model.predict([X_val_ecg, X_val_vit])
        val_f1, per_class_f1 = compute_masked_macro_f1(y_val, y_val_pred)
        logger.info(f"Validation Macro-F1 with {name}: {val_f1:.4f}")
        logger.info(f"Per-Class F1 with {name}: {per_class_f1}")
        
        if val_f1 > best_macro_f1:
            best_macro_f1 = val_f1
            best_loss_name = name
            best_model_history = history.history
            # Save best overall model
            model_save_path = os.path.join(out_model_dir, "best_retrained_model.keras")
            model.save(model_save_path)
            
    logger.info("\n" + "="*50)
    logger.info(f"Loss comparison complete. Best Loss: {best_loss_name} (Val Macro-F1: {best_macro_f1:.4f})")
    logger.info("="*50)
    
    # Save training history to CSV
    if best_model_history:
        history_df = pd.DataFrame(best_model_history)
        history_df.to_csv(os.path.join(out_model_dir, "training_history.csv"), index=False)
        
    # Write training report
    report_path = "reports/training_report.md"
    with open(report_path, "w") as f:
        f.write("# Model Retraining Report\n\n")
        f.write(f"- **Best Loss Function**: {best_loss_name}\n")
        f.write(f"- **Validation Macro-F1**: {best_macro_f1:.4f}\n")
        f.write(f"- **Optimizer**: AdamW (lr=2e-4, weight_decay=1e-4)\n")
        f.write("- **Saved Model Path**: `models/retrained_1000/best_retrained_model.keras`\n\n")
        
        f.write("## Validation Performance Breakdown per Class\n\n")
        f.write("| Condition | F1-Score (Val) |\n")
        f.write("| --- | --- |\n")
        class_names = ['AF', 'Tachycardia', 'Bradycardia', 'Hypoxemia', 'Fever']
        # Load best model and evaluate again to be sure
        best_model = tf.keras.models.load_model(os.path.join(out_model_dir, "best_retrained_model.keras"), compile=False)
        y_val_pred_best = best_model.predict([X_val_ecg, X_val_vit])
        _, best_per_class_f1 = compute_masked_macro_f1(y_val, y_val_pred_best)
        for name, score in zip(class_names, best_per_class_f1):
            f.write(f"| {name} | {score:.4f} |\n")
            
    print(f"Training report written to {report_path}")

if __name__ == "__main__":
    retrain_pipeline()
