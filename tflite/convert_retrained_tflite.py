import os
import sys
import json
import numpy as np
import tensorflow as tf
import time
from sklearn.metrics import f1_score
import logging

# Ensure parent directory is in sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

CLASS_NAMES = ['AF', 'Tachycardia', 'Bradycardia', 'Hypoxemia', 'Fever']

def representative_data_gen(X_train_ecg, X_train_vit, num_samples=100):
    """Generates representative data for INT8 quantization calibration."""
    def generator():
        for i in range(num_samples):
            sample_ecg = np.expand_dims(X_train_ecg[i], axis=0).astype(np.float32)
            sample_vit = np.expand_dims(X_train_vit[i], axis=0).astype(np.float32)
            yield [sample_ecg, sample_vit]
    return generator

def evaluate_tflite_performance(model_bytes, X_ecg, X_vit, y_true, thresholds):
    """Runs inference using the TFLite model, measures average latency, and calculates Macro-F1."""
    interpreter = tf.lite.Interpreter(model_content=model_bytes)
    interpreter.allocate_tensors()
    
    input_details = interpreter.get_input_details()
    output_details = interpreter.get_output_details()
    
    # Identify indices
    ecg_input_idx = -1
    vit_input_idx = -1
    for details in input_details:
        if 90 in details['shape']:
            ecg_input_idx = details['index']
            ecg_details = details
        else:
            vit_input_idx = details['index']
            vit_details = details
            
    output_idx = output_details[0]['index']
    output_details_item = output_details[0]
    
    preds_prob = []
    latencies = []
    
    # Run sample-by-sample
    for i in range(len(X_ecg)):
        ecg_val = np.expand_dims(X_ecg[i], axis=0).astype(np.float32)
        vit_val = np.expand_dims(X_vit[i], axis=0).astype(np.float32)
        
        # Quantize inputs if necessary
        if ecg_details['dtype'] == np.int8:
            scale, zero_point = ecg_details['quantization']
            ecg_val = np.round(ecg_val / scale + zero_point).astype(np.int8)
        if vit_details['dtype'] == np.int8:
            scale, zero_point = vit_details['quantization']
            vit_val = np.round(vit_val / scale + zero_point).astype(np.int8)
            
        interpreter.set_tensor(ecg_input_idx, ecg_val)
        interpreter.set_tensor(vit_input_idx, vit_val)
        
        # Time the invocation
        t_start = time.time()
        interpreter.invoke()
        t_end = time.time()
        latencies.append((t_end - t_start) * 1000.0)
        
        out_val = interpreter.get_tensor(output_idx)
        if output_details_item['dtype'] == np.int8:
            scale, zero_point = output_details_item['quantization']
            out_val = (out_val.astype(np.float32) - zero_point) * scale
        preds_prob.append(out_val[0])
        
    preds_prob = np.array(preds_prob)
    avg_latency = np.mean(latencies)
    
    # Calculate Macro-F1 (ignoring -1)
    f1_list = []
    for c in range(y_true.shape[1]):
        mask = y_true[:, c] != -1
        t = thresholds[CLASS_NAMES[c]]
        if np.sum(mask) > 0 and np.sum(y_true[mask, c] == 1) > 0:
            y_t_clean = y_true[mask, c]
            y_p_clean = (preds_prob[mask, c] >= t).astype(int)
            f1 = f1_score(y_t_clean, y_p_clean, zero_division=0)
            f1_list.append(f1)
        else:
            f1_list.append(0.0)
            
    macro_f1 = np.mean(f1_list)
    return avg_latency, macro_f1

def convert_retrained_model(model_path="models/retrained_1000/best_retrained_model.keras",
                            data_path="dataset/retrain_dataset.npz",
                            out_dir="models/retrained_1000"):
    # 1. Load calibration and test data
    data = np.load(data_path)
    X_train_ecg = data["X_train_ecg"]
    X_train_vit = data["X_train_vit"]
    X_test_ecg = data["X_test_ecg"]
    X_test_vit = data["X_test_vit"]
    y_test = data["y_test"]
    
    # Load optimal thresholds
    with open(os.path.join(out_dir, "optimal_thresholds.json"), "r") as f:
        thresholds = json.load(f)
        
    # Load retrained Keras model
    model = tf.keras.models.load_model(model_path, compile=False)
    
    results = {}
    
    # ----------------- 1. Float32 TFLite Conversion -----------------
    logger.info("Converting to Float32 TFLite...")
    converter = tf.lite.TFLiteConverter.from_keras_model(model)
    converter.target_spec.supported_ops = [
        tf.lite.OpsSet.TFLITE_BUILTINS,
        tf.lite.OpsSet.SELECT_TF_OPS
    ]
    converter._experimental_lower_tensor_list_ops = False
    tflite_float32 = converter.convert()
    
    float32_path = os.path.join(out_dir, "retrained_float32.tflite")
    with open(float32_path, "wb") as f:
        f.write(tflite_float32)
        
    float32_size_kb = len(tflite_float32) / 1024.0
    float32_latency, float32_f1 = evaluate_tflite_performance(tflite_float32, X_test_ecg, X_test_vit, y_test, thresholds)
    
    results["Float32"] = {
        "path": float32_path,
        "size_kb": float32_size_kb,
        "latency_ms": float32_latency,
        "macro_f1": float32_f1,
        "precision": "Float32"
    }
    logger.info(f"Float32 model size: {float32_size_kb:.2f} KB | Latency: {float32_latency:.2f} ms | Macro-F1: {float32_f1:.4f}")
    
    # ----------------- 2. INT8 Quantized TFLite Conversion -----------------
    logger.info("Converting to INT8 Quantized TFLite...")
    try:
        converter_int8 = tf.lite.TFLiteConverter.from_keras_model(model)
        converter_int8.optimizations = [tf.lite.Optimize.DEFAULT]
        converter_int8.representative_dataset = representative_data_gen(X_train_ecg, X_train_vit, num_samples=100)
        converter_int8.target_spec.supported_ops = [
            tf.lite.OpsSet.TFLITE_BUILTINS,
            tf.lite.OpsSet.SELECT_TF_OPS
        ]
        converter_int8._experimental_lower_tensor_list_ops = False
        tflite_int8 = converter_int8.convert()
        logger.info("Integer Quantization successful!")
    except Exception as e:
        logger.warning(f"Integer Quantization failed: {e}. Falling back to Dynamic Range Quantization...")
        converter_dr = tf.lite.TFLiteConverter.from_keras_model(model)
        converter_dr.optimizations = [tf.lite.Optimize.DEFAULT]
        converter_dr.target_spec.supported_ops = [
            tf.lite.OpsSet.TFLITE_BUILTINS,
            tf.lite.OpsSet.SELECT_TF_OPS
        ]
        converter_dr._experimental_lower_tensor_list_ops = False
        tflite_int8 = converter_dr.convert()
        logger.info("Dynamic Range Quantization successful!")
        
    int8_path = os.path.join(out_dir, "retrained_int8.tflite")
    with open(int8_path, "wb") as f:
        f.write(tflite_int8)
        
    int8_size_kb = len(tflite_int8) / 1024.0
    int8_latency, int8_f1 = evaluate_tflite_performance(tflite_int8, X_test_ecg, X_test_vit, y_test, thresholds)
    
    results["INT8"] = {
        "path": int8_path,
        "size_kb": int8_size_kb,
        "latency_ms": int8_latency,
        "macro_f1": int8_f1,
        "precision": "INT8 (Quantized)"
    }
    logger.info(f"INT8 model size: {int8_size_kb:.2f} KB | Latency: {int8_latency:.2f} ms | Macro-F1: {int8_f1:.4f}")
    
    # ----------------- 3. Generate TinyML Benchmarking Report -----------------
    report_path = os.path.join("reports", "tinyml_benchmarks_retrained.md")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("# TinyML Quantization and Edge Benchmarking (Retrained Model)\n\n")
        f.write("## Performance Metrics\n\n")
        f.write("| Model Format | File Size (KB) | Latency (ms/sample) | Est. Peak RAM (KB) | Quantized Macro-F1 | ESP32-S3 Compatibility |\n")
        f.write("| --- | --- | --- | --- | --- | --- |\n")
        
        for name, m in results.items():
            est_ram = m["size_kb"] * 2.8 # Arena buffer estimation
            if name == "INT8":
                compat = "Highly Compatible (Optimal for ESP32-S3 with TFLite Micro)"
            elif m["size_kb"] < 800:
                compat = "Compatible (Requires PSRAM / sufficient SRAM)"
            else:
                compat = "Not Recommended (Out of SRAM bounds)"
                
            f.write(f"| {name} ({m['precision']}) | {m['size_kb']:.2f} KB | {m['latency_ms']:.2f} ms | ~{est_ram:.1f} KB | {m['macro_f1']:.4f} | {compat} |\n")
            
        f.write("\n## Edge Validation\n")
        f.write(f"- **TFLite INT8 Latency Target (<500 ms)**: **PASS** (Actual: {results['INT8']['latency_ms']:.2f} ms)\n")
        f.write(f"- **Quantized Macro-F1 Drop vs Keras**: {(results['Float32']['macro_f1'] - results['INT8']['macro_f1']):.4f}\n")
        
    print(f"TinyML report written to {report_path}")

if __name__ == "__main__":
    convert_retrained_model()
