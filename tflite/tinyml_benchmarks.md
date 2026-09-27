# PulseTech TinyML Benchmarking & ESP32-S3 Compatibility Report

## Performance Metrics

| Model Format | File Size (KB) | Latency (ms/sample) | Est. Peak RAM (KB) | ESP32-S3 Compatibility |
| --- | --- | --- | --- | --- |
| Float32 (Float32) | 767.30 KB | 0.59 ms | ~2148.4 KB | Compatible (Requires PSRAM / sufficient SRAM) |
| INT8 (INT8 (Quantized)) | 327.47 KB | 0.20 ms | ~916.9 KB | Highly Compatible (Optimal for ESP32-S3 with TFLite Micro) |

## ESP32-S3 Hardware Deployment Guide

1. **Convert Binary model to C array**:
   ```bash
   xxd -i tflite/model_int8.tflite > docs/model_int8_data.h
   ```
2. **Configure Tensor Arena Size**:
   Include the array and set allocating boundaries:
   ```cpp
   constexpr int kTensorArenaSize = 962560;
   uint8_t tensor_arena[kTensorArenaSize];
   ```
3. **Inference Execution**:
   - Fetch ECG data and preprocess.
   - Gather demographic details and compute handcrafted features.
   - Feed both inputs, invoke, and parse the resulting 10-label sigmoid classification.
