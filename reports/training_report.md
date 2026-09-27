# Model Retraining Report

- **Best Loss Function**: Weighted_BCE
- **Validation Macro-F1**: 0.2705
- **Optimizer**: AdamW (lr=2e-4, weight_decay=1e-4)
- **Saved Model Path**: `models/retrained_1000/best_retrained_model.keras`

## Validation Performance Breakdown per Class

| Condition | F1-Score (Val) |
| --- | --- |
| AF | 0.0000 |
| Tachycardia | 0.7692 |
| Bradycardia | 0.5833 |
| Hypoxemia | 0.0000 |
| Fever | 0.0000 |
