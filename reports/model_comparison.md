# Model Comparison Report: Existing vs Retrained

| Metric | Existing Model | Retrained Model |
| --- | ---: | ---: |
| **Macro-F1** | 0.2454 | 0.1264 |
| **Micro-F1** | 0.2429 | 0.1325 |
| **Hamming Loss** | 0.1038 | 0.2566 |
| **AF F1** | 0.3333 | 0.1026 |
| **Tachycardia F1** | 0.5778 | 0.4561 |
| **Bradycardia F1** | 0.3158 | 0.0735 |
| **Hypoxemia F1** | 0.0000 | 0.0000 |
| **Fever F1** | 0.0000 | 0.0000 |

## Findings
- The retrained model has similar or lower performance, which might be due to the limited training sample size (1,000 samples) compared to the original dataset.
