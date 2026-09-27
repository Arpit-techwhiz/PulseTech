import os
import json
import yaml
import numpy as np
from datetime import datetime

# Paths (adjust if workspace root changes)
PROJECT_ROOT = r"C:\Users\arpit\OneDrive\Desktop\pulsetech"
NPZ_PATH = os.path.join(PROJECT_ROOT, "dataset", "preprocessed_data.npz")
METADATA_DIR = os.path.join(PROJECT_ROOT, "metadata")
REPORTS_DIR = os.path.join(PROJECT_ROOT, "reports")

os.makedirs(METADATA_DIR, exist_ok=True)
os.makedirs(REPORTS_DIR, exist_ok=True)

# Load NPZ file
npz = np.load(NPZ_PATH, allow_pickle=True)

# Helper to safely get array size
def get_len(key):
    arr = npz.get(key)
    return int(arr.shape[0]) if arr is not None else 0

# Basic reconstruction of provenance
metadata = {
    "generated_at": datetime.utcnow().isoformat() + "Z",
    "preprocess_keys": list(npz.files),
    "split_counts": {
        "train": sum(get_len(k) for k in npz.files if k.startswith("X_train")),
        "val": sum(get_len(k) for k in npz.files if k.startswith("X_val")),
        "test": sum(get_len(k) for k in npz.files if k.startswith("X_test")),
    },
    "label_counts": {},
    "source_contributions": {},
    "sampling_frequency_hz": None,
    "ecg_length_seconds": None,
    "patient_ids_available": False,
    "random_seed": None,
    "split_ratios": None,
}

# Infer label counts per split if label arrays exist
for split in ["train", "val", "test"]:
    y_key = f"y_{split}"
    if y_key in npz:
        labels = npz[y_key]
        # assuming multi‑label one‑hot matrix
        counts = labels.sum(axis=0).astype(int).tolist()
        metadata["label_counts"][split] = counts

# Heuristic source contribution – look for keys like "source_*"
source_keys = [k for k in npz.files if k.startswith("source_")]
if source_keys:
    for sk in source_keys:
        src_name = sk.split("_")[1]
        metadata["source_contributions"][src_name] = int(npz[sk].shape[0])
else:
    total_samples = metadata["split_counts"]["train"] + metadata["split_counts"]["val"] + metadata["split_counts"]["test"]
    metadata["source_contributions"]["unknown"] = total_samples

# Attempt to read sampling info from a possible "sampling_rate" array
if "sampling_rate" in npz:
    metadata["sampling_frequency_hz"] = float(npz["sampling_rate"].item())

# ECG length – if ECG array shape is (samples, channels, timesteps)
if "X_train_ecg" in npz:
    timesteps = npz["X_train_ecg"].shape[-1]
    if metadata["sampling_frequency_hz"]:
        metadata["ecg_length_seconds"] = timesteps / metadata["sampling_frequency_hz"]

# Write JSON metadata
json_path = os.path.join(METADATA_DIR, "dataset_provenance.json")
with open(json_path, "w", encoding="utf-8") as f:
    json.dump(metadata, f, indent=2)

# Write human‑readable markdown report
md_lines = ["# Dataset Provenance Report", "", f"**Generated:** {metadata['generated_at']}", "", "## Summary of Recovered Information", ""]
md_lines.append("| Field | Value |")
md_lines.append("|-------|-------|")
for k, v in metadata.items():
    if isinstance(v, (dict, list)):
        continue
    md_lines.append(f"| {k} | {v} |")

md_lines.append("\n## Label Counts per Split")
for split, counts in metadata.get("label_counts", {}).items():
    md_lines.append(f"- **{split}**: {counts}")

md_lines.append("\n## Source Contributions")
for src, cnt in metadata["source_contributions"].items():
    md_lines.append(f"- {src}: {cnt} samples")

md_lines.append("\n## Missing / Unrecoverable Information")
md_lines.append("- Original patient identifiers – **unavailable**")
md_lines.append("- PTB‑XL to 10‑class label mapping – **unavailable**")
md_lines.append("- MIMIC‑IV alignment methodology – **unavailable**")
md_lines.append("- Random seed used during preprocessing – **unavailable**")

md_path = os.path.join(REPORTS_DIR, "dataset_provenance.md")
with open(md_path, "w", encoding="utf-8") as f:
    f.write("\n".join(md_lines))

print(f"Metadata JSON written to {json_path}")
print(f"Provenance markdown written to {md_path}")
