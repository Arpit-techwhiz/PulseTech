import os
import json
import numpy as np

PROJECT_ROOT = r"C:\Users\arpit\OneDrive\Desktop\pulsetech"
NPZ_PATH = os.path.join(PROJECT_ROOT, "dataset", "preprocessed_data.npz")
METADATA_PATH = os.path.join(PROJECT_ROOT, "metadata", "dataset_provenance.json")
REPORT_PATH = os.path.join(PROJECT_ROOT, "reports", "dataset_audit.md")

# Load data
npz = np.load(NPZ_PATH, allow_pickle=True)
with open(METADATA_PATH, "r", encoding="utf-8") as f:
    meta = json.load(f)

# Gather label arrays per split
label_arrays = {}
for split in ["train", "val", "test"]:
    key = f"y_{split}"
    if key in npz:
        label_arrays[split] = npz[key]

# Sample counts per split
sample_counts = {split: arr.shape[0] for split, arr in label_arrays.items()}

total_samples = sum(sample_counts.values())

# Class prevalence (overall)
if label_arrays:
    all_labels = np.concatenate(list(label_arrays.values()))
    class_counts = all_labels.sum(axis=0).astype(int).tolist()
else:
    class_counts = []

# Multi‑label cardinality & density
if label_arrays:
    all_labels = np.concatenate(list(label_arrays.values()))
    cardinality = float(all_labels.sum()) / all_labels.shape[0]
    density = cardinality / all_labels.shape[1]
else:
    cardinality = density = 0.0

# Missing vital signs (NaNs)
missing_vitals = {}
for split in ["train", "val", "test"]:
    vit_key = f"X_{split}_vit"
    if vit_key in npz:
        vit = npz[vit_key]
        missing = np.isnan(vit).sum()
        total = vit.size
        missing_vitals[split] = f"{missing}/{total} ({missing/total:.2%})"
    else:
        missing_vitals[split] = "N/A"

# Duplicate ECG windows (exact matches)
duplicate_counts = {}
for split in ["train", "val", "test"]:
    ecg_key = f"X_{split}_ecg"
    if ecg_key in npz:
        ecg = npz[ecg_key]
        flat = ecg.reshape(ecg.shape[0], -1)
        # Find duplicates using numpy unique
        _, idx_counts = np.unique(flat, axis=0, return_counts=True)
        dup = int((idx_counts > 1).sum())
        duplicate_counts[split] = dup
    else:
        duplicate_counts[split] = 0

# Write markdown report
lines = ["# Dataset Audit Report", "", f"**Generated:** {meta.get('generated_at', 'unknown')}", "", "## Summary", ""]
lines.append(f"- Total samples (all splits): {total_samples}")
for split, cnt in sample_counts.items():
    lines.append(f"- {split.capitalize()} samples: {cnt}")
lines.append(f"- Number of classes: {len(class_counts)}")
lines.append(f"- Class counts (train+val+test): {class_counts}")
lines.append(f"- Multi‑label cardinality: {cardinality:.3f}")
lines.append(f"- Multi‑label density: {density:.3f}\n")
lines.append("## Missing Vital Signs (NaN entries)")
for split, info in missing_vitals.items():
    lines.append(f"- {split}: {info}")
lines.append("\n## Duplicate ECG Samples (exact matches)")
for split, dup in duplicate_counts.items():
    lines.append(f"- {split}: {dup} duplicate windows")

os.makedirs(os.path.dirname(REPORT_PATH), exist_ok=True)
with open(REPORT_PATH, "w", encoding="utf-8") as f:
    f.write("\n".join(lines))
print(f"Dataset audit report written to {REPORT_PATH}")
