# TinyML Quantization and Edge Benchmarking (Retrained Model)

## Performance Metrics

| Model Format | File Size (KB) | Latency (ms/sample) | Est. Peak RAM (KB) | Quantized Macro-F1 | ESP32-S3 Compatibility |
| --- | --- | --- | --- | --- | --- |
| Float32 (Float32) | 768.69 KB | 0.73 ms | ~2152.3 KB | 0.2363 | Compatible (Requires PSRAM / sufficient SRAM) |
| INT8 (INT8 (Quantized)) | 329.62 KB | 0.30 ms | ~922.9 KB | 0.2226 | Highly Compatible (Optimal for ESP32-S3 with TFLite Micro) |

## Edge Validation
- **TFLite INT8 Latency Target (<500 ms)**: **PASS** (Actual: 0.30 ms)
- **Quantized Macro-F1 Drop vs Keras**: 0.0136
