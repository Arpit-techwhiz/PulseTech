# Ablation Study: Multimodal Fusion Verification

| Experiment | Description | Test Macro-F1 |
| --- | --- | ---: |
| **A** | ECG Only (Clinical vitals masked) | 0.0639 |
| **B** | Vitals Only (ECG wave and features masked) | 0.0692 |
| **C** | ECG + HR + SpO₂ (Partial multimodal) | 0.0673 |
| **D** | ECG + PPG + HR + SpO₂ + Temp (Full Fusion) | 0.0676 |

## Ablation Discussion
- Multimodal fusion did not lead to a significant increase in Macro-F1 compared to unimodal inputs. This could be due to missing values and the imputation strategy.
