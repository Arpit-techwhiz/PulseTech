# Dataset Reconstruction Report

**Generated:** 2026-07-12T04:41:15.356031Z

## What we know (verified)

- **generated_at**: 2026-07-12T04:41:15.356031Z
- **preprocess_keys**: ['X_train_ecg', 'X_train_vit', 'y_train', 'X_val_ecg', 'X_val_vit', 'y_val', 'X_test_ecg', 'X_test_vit', 'y_test']
- **split_counts**: {'train': 157536, 'val': 27380, 'test': 72708}
- **label_counts**: {'train': [6444, 7020, 4762, 6100, 13968, 20078, 116, 20250, 12736, 9226], 'val': [5788, 1956, 214, 3965, 0, 6892, 0, 0, 0, 0], 'test': [12218, 1769, 186, 2790, 1542, 5501, 135, 5201, 7126, 6108]}
- **source_contributions**: {'unknown': 257624}

## What we do NOT know (missing)
- **patient_ids_available**: missing / not recorded
- **label_mapping**: missing / not recorded
- **alignment_method**: missing / not recorded

## What can be reconstructed?
- Split sizes (train/val/test) recovered from NPZ keys.
- Approximate source contribution counts derived from any `source_*` arrays.

## Assumptions made
- Patient identifiers were not stored; we cannot verify patient‑level leakage.
- Label mapping between PTB‑XL and the 10‑class schema is unknown; existing one‑hot labels are taken as ground truth.
- Vital‑sign alignment with ECG windows is assumed correct based on the preprocessing pipeline, but no explicit alignment metadata is present.

## Related reports
- [Dataset Audit](dataset_audit.md)
- [Leakage Audit](data_leakage_audit.md)