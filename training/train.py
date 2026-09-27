import os
import sys
import numpy as np
import tensorflow as tf
from sklearn.metrics import accuracy_score, precision_recall_fscore_support
import logging

# Ensure parent directory is in sys.path for local module imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Import hybrid models including the SOTA PulseTech_v4
from models.architectures import (
    build_hybrid_resnet, 
    build_hybrid_cnn_bilstm, 
    build_hybrid_attention,
    build_pulsetech_v4
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

def asymmetric_loss(gamma_neg=4.0, gamma_pos=1.0, clip=0.05, eps=1e-7):
    """
    Asymmetric Loss (ASL) for multi-label classification.
    Focuses on hard positive/negative samples and discounts easy negatives.
    Highly effective for extremely imbalanced medical targets.
    """
    def loss(y_true, y_pred):
        y_true = tf.cast(y_true, tf.float32)
        y_pred = tf.clip_by_value(y_pred, eps, 1.0 - eps)
        
        # Positive and negative logits
        xs_pos = y_pred
        xs_neg = 1.0 - y_pred
        
        # Asymmetric clipping for negatives
        if clip is not None and clip > 0:
            xs_neg = xs_neg + clip
            xs_neg = tf.clip_by_value(xs_neg, 0.0, 1.0)
            
        # Basic cross entropy terms
        loss_pos = y_true * tf.math.log(xs_pos)
        loss_neg = (1.0 - y_true) * tf.math.log(xs_neg)
        
        # Asymmetric focusing
        if gamma_pos > 0:
            loss_pos *= tf.pow(1.0 - xs_pos, gamma_pos)
        if gamma_neg > 0:
            loss_neg *= tf.pow(1.0 - xs_neg, gamma_neg)
            
        asym_loss = - (loss_pos + loss_neg)
        return tf.reduce_sum(asym_loss, axis=-1)
    return loss

def train_and_evaluate_all(data_path="dataset/preprocessed_data.npz", out_model_dir="models"):
    """
    Loads preprocessed multimodal dataset, trains candidate hybrid models
    (including PulseTech_v4 with multi-scale Conv, Squeeze-Excitation, and Transformers),
    compares their test metrics, and saves the best model.
    """
    os.makedirs(out_model_dir, exist_ok=True)
    os.makedirs("logs/tensorboard", exist_ok=True)
    
    # 1. Load data
    logger.info(f"Loading preprocessed data from {data_path}...")
    data = np.load(data_path)
    X_train_ecg, X_train_vit, y_train = data["X_train_ecg"], data["X_train_vit"], data["y_train"]
    X_val_ecg, X_val_vit, y_val = data["X_val_ecg"], data["X_val_vit"], data["y_val"]
    X_test_ecg, X_test_vit, y_test = data["X_test_ecg"], data["X_test_vit"], data["y_test"]
    
    vitals_dim = X_train_vit.shape[1]
    logger.info(f"Train sizes - ECG: {X_train_ecg.shape}, Vitals (dynamic dim {vitals_dim}): {X_train_vit.shape}, Labels: {y_train.shape}")
    
    # Define models to train
    model_builders = {
        "Hybrid_ResNet": build_hybrid_resnet,
        "Hybrid_CNN_BiLSTM": build_hybrid_cnn_bilstm,
        "Hybrid_CNN_BiLSTM_Attention": build_hybrid_attention,
        "PulseTech_v4": build_pulsetech_v4
    }
    
    results = {}
    best_f1 = -1
    best_model_name = None
    
    epochs = 20
    batch_size = 128  # Lower batch size for better generalisation on clinical datasets
    
    for name, builder in model_builders.items():
        logger.info("\n" + "="*50)
        logger.info(f"Training Model: {name}")
        logger.info("="*50)
        
        # Instantiate hybrid model dynamically
        model = builder(ecg_shape=(90, 1), vitals_shape=(vitals_dim,), num_classes=10)
        
        # Configure optimizer: AdamW with weight decay for better regularisation (especially on Transformer)
        optimizer = tf.keras.optimizers.AdamW(learning_rate=1e-3, weight_decay=1e-4)
        
        # Compile with SOTA Asymmetric Loss for multi-label arrhythmia imbalance
        model.compile(
            optimizer=optimizer,
            loss=asymmetric_loss(gamma_neg=4.0, gamma_pos=1.0, clip=0.05),
            metrics=['binary_accuracy']
        )
        
        # Callbacks
        checkpoint_path = os.path.join(out_model_dir, f"checkpoint_{name}.keras")
        
        # Dynamic Cosine Decay learning rate scheduler
        lr_schedule = tf.keras.callbacks.LearningRateScheduler(
            lambda epoch, lr: 1e-3 * 0.5 * (1.0 + np.cos(np.pi * epoch / epochs))
        )
        
        callbacks = [
            tf.keras.callbacks.EarlyStopping(
                monitor='val_loss', 
                patience=5, 
                restore_best_weights=True,
                verbose=1
            ),
            lr_schedule,
            tf.keras.callbacks.ModelCheckpoint(
                filepath=checkpoint_path, 
                monitor='val_loss', 
                save_best_only=True,
                verbose=1
            ),
            tf.keras.callbacks.TensorBoard(
                log_dir=f"logs/tensorboard/{name}",
                histogram_freq=0
            )
        ]
        
        # Train with multi-modal inputs
        model.fit(
            [X_train_ecg, X_train_vit], y_train,
            validation_data=([X_val_ecg, X_val_vit], y_val),
            epochs=epochs,
            batch_size=batch_size,
            callbacks=callbacks,
            verbose=1
        )
        
        # Load best weights (load without compiling to bypass custom loss function serialization issues)
        if os.path.exists(checkpoint_path):
            model = tf.keras.models.load_model(checkpoint_path, compile=False)
            
        # Evaluate on Test Set
        logger.info(f"Evaluating model {name} on Test Set...")
        y_pred_prob = model.predict([X_test_ecg, X_test_vit], batch_size=256)
        
        # Threshold at 0.5 for multi-label targets
        y_pred = (y_pred_prob >= 0.5).astype(int)
        
        # Calculate metrics
        subset_acc = accuracy_score(y_test, y_pred) # Exact matches
        prec, rec, f1, _ = precision_recall_fscore_support(y_test, y_pred, average='macro', zero_division=0)
        
        # Hamming accuracy
        hamming_acc = 1.0 - np.mean(np.abs(y_test - y_pred))
        
        logger.info(f"Model {name} Test Metrics:")
        logger.info(f"Subset Accuracy: {subset_acc:.4f} | Hamming Accuracy: {hamming_acc:.4f}")
        logger.info(f"Macro Precision: {prec:.4f} | Macro Recall: {rec:.4f} | Macro F1-Score: {f1:.4f}")
        
        results[name] = {
            "accuracy": subset_acc,
            "hamming_accuracy": hamming_acc,
            "precision": prec,
            "recall": rec,
            "f1_score": f1,
            "checkpoint_path": checkpoint_path
        }
        
        # Track best model by Macro F1
        if f1 > best_f1:
            best_f1 = f1
            best_model_name = name
            
    # Save the best model
    logger.info("\n" + "="*50)
    logger.info(f"Model Comparison Results:")
    for name, metrics in results.items():
        logger.info(f"- {name}: Subset Acc={metrics['accuracy']:.4f}, Hamming Acc={metrics['hamming_accuracy']:.4f}, Macro-F1={metrics['f1_score']:.4f}")
        
    logger.info(f"Best performing model by Macro-F1: {best_model_name} (F1: {best_f1:.4f})")
    
    # Save as final best model
    best_checkpoint = results[best_model_name]["checkpoint_path"]
    best_model = tf.keras.models.load_model(best_checkpoint, compile=False)
    best_model_save_path = os.path.join(out_model_dir, "best_ecg_model.keras")
    best_model.save(best_model_save_path)
    logger.info(f"Saved best model to {best_model_save_path}")
    
    # Write comparison results
    with open(os.path.join(out_model_dir, "model_comparison.txt"), "w") as f:
        f.write("PulseTech Multimodal Hybrid Model Comparison Results\n")
        f.write("===================================================\n\n")
        for name, metrics in results.items():
            f.write(f"Model: {name}\n")
            f.write(f"  Subset Accuracy:  {metrics['accuracy']:.4f}\n")
            f.write(f"  Hamming Accuracy: {metrics['hamming_accuracy']:.4f}\n")
            f.write(f"  Precision:        {metrics['precision']:.4f}\n")
            f.write(f"  Recall:           {metrics['recall']:.4f}\n")
            f.write(f"  F1-Score:         {metrics['f1_score']:.4f}\n\n")
        f.write(f"Best Model Selected: {best_model_name}\n")

if __name__ == "__main__":
    train_and_evaluate_all()
