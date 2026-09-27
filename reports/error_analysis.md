# Error Analysis Report

## Class: AF
- **False Positives**: 35 cases
- **False Negatives (Missed)**: 0 cases

### Example False Positive Cases (Vitals)
| Case | HR | SpO2 | Temp | Prob |
| --- | ---: | ---: | ---: | ---: |
| Sample 0 | 82.1 | 98.0 | 36.80 | 0.4996 |
| Sample 1 | 71.8 | 98.0 | 36.80 | 0.2744 |
| Sample 2 | 85.0 | 98.0 | 36.80 | 0.4493 |

---

## Class: Tachycardia
- **False Positives**: 31 cases
- **False Negatives (Missed)**: 0 cases

### Example False Positive Cases (Vitals)
| Case | HR | SpO2 | Temp | Prob |
| --- | ---: | ---: | ---: | ---: |
| Sample 0 | 82.1 | 98.0 | 36.80 | 0.9164 |
| Sample 2 | 85.0 | 98.0 | 36.80 | 0.8673 |
| Sample 3 | 84.4 | 98.0 | 36.80 | 0.8106 |

---

## Class: Bradycardia
- **False Positives**: 125 cases
- **False Negatives (Missed)**: 1 cases

### Example False Positive Cases (Vitals)
| Case | HR | SpO2 | Temp | Prob |
| --- | ---: | ---: | ---: | ---: |
| Sample 19 | 65.3 | 98.0 | 36.80 | 0.6465 |
| Sample 22 | 67.1 | 98.0 | 36.80 | 0.6437 |
| Sample 28 | 75.8 | 98.0 | 36.80 | 0.6182 |

### Example Missed Cases (Vitals)
| Case | HR | SpO2 | Temp | Prob |
| --- | ---: | ---: | ---: | ---: |
| Sample 37 | 59.3 | 98.0 | 36.80 | 0.6039 |

---

## Class: Hypoxemia
- **False Positives**: 0 cases
- **False Negatives (Missed)**: 70 cases

### Example Missed Cases (Vitals)
| Case | HR | SpO2 | Temp | Prob |
| --- | ---: | ---: | ---: | ---: |
| Sample 68 | 94.0 | 93.0 | 36.80 | 0.2098 |
| Sample 69 | 94.0 | 93.0 | 36.80 | 0.2099 |
| Sample 70 | 94.0 | 93.0 | 36.80 | 0.2576 |

---

## Class: Fever
- **False Positives**: 0 cases
- **False Negatives (Missed)**: 0 cases

---

