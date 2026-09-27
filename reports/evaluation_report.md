# Model Evaluation Report (Retrained on 1,000 Samples)

- **Overall Macro-F1**: 0.1264
- **Overall Micro-F1**: 0.1325
- **Hamming Loss**: 0.2566

## Per-Class Evaluation Metrics

| Condition | Precision | Recall | F1 | AUROC | AUPRC | Support |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| AF | 0.0541 | 1.0000 | 0.1026 | 0.8911 | 0.0451 | 2 |
| Tachycardia | 0.2955 | 1.0000 | 0.4561 | 0.9880 | 0.7894 | 13 |
| Bradycardia | 0.0385 | 0.8333 | 0.0735 | 0.8363 | 0.3049 | 6 |
| Hypoxemia | 0.0000 | 0.0000 | 0.0000 | 0.1397 | 0.3418 | 70 |
| Fever | 0.0000 | 0.0000 | 0.0000 | nan | 0.5000 | 0 |
| **Macro-F1** | | | 0.1264 | | | |
