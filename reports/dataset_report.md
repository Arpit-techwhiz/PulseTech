# Retraining Dataset Audit Report

- **Total Samples**: 1085
- **Number of Patients**: 187
- **Number of Records**: 164

## Samples per Dataset Source
- **mitdb**: 365 samples
- **afdb**: 240 samples
- **bidmc**: 350 samples
- **normtemp**: 130 samples

## Patient Split Info
- **Train split**: 670 samples
- **Val split**: 74 samples
- **Test split**: 341 samples

## Positive / Negative / Unknown Counts per Class

| Condition | Positive (1) | Negative (0) | Unknown (-1) |
| --- | --- | --- | --- |
| AF | 60 | 545 | 480 |
| Tachycardia | 135 | 950 | 0 |
| Bradycardia | 73 | 1012 | 0 |
| Hypoxemia | 70 | 277 | 738 |
| Fever | 1 | 129 | 955 |

## Missing Signal Count
- **Missing/All-Zero ECG**: 130 samples (from normtemp)
- **Missing PPG**: 735 samples (from mitdb, afdb, and normtemp)
- **Missing HR**: 0 samples
- **Missing SpO2**: 738 samples
- **Missing Temperature**: 955 samples

## Duplicate Windows
- **Exact Duplicate ECG Windows**: 0
