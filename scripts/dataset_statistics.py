import os
import json
import numpy as np

PROJECT_ROOT = r"C:\Users\arpit\OneDrive\Desktop\pulsetech"
NPZ_PATH = os.path.join(PROJECT_ROOT, "dataset", "preprocessed_data.npz")
METADATA_PATH = os.path.join(PROJECT_ROOT, "metadata", "dataset_provenance.json")
REPORT_PATH = os.path.join(PROJECT_ROOT, "reports", "dataset_statistics.md")

# Load data and metadata
npz = np.load(NPZ_PATH, allow_pickle=True)
with open(METADATA_PATH, "r", encoding="utf-8") as f:
    meta = json.load(f)

# Helper to get split counts
split_counts = meta.get("split_counts", {})

# ECG length and sampling rate (if available)
sampling_hz = meta.get("sampling_frequency_hz")
ecgs = []
for split in ["train", "val", "test"]:
    key = f"X_{split}_ecg"
    if key in npz:
        ecgs.append(npz[key])
if ecgs:
    timesteps = ecgs[0].shape[-1]
    ecg_len_sec = timesteps / sampling_hz if sampling_hz else None
else:
    ecg_len_sec = None

# Missing vitals statistics
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

# Duplicate ECG windows (exact) across entire dataset using hash method
hash_dict = {}
duplicate_total = 0
for split in ["train", "val", "test"]:
    key = f"X_{split}_ecg"
    if key not in npz:
        continue
    ecg = npz[key]
    flat = ecg.reshape(ecg.shape[0], -1)
    for vec in flat:
        h = vec.tobytes()
        if h in hash_dict:
            duplicate_total += 1
        else:
            hash_dict[h] = True

# Write markdown report
lines = ["# Dataset Statistics Report", "", f"**Generated:** {meta.get('generated_at', 'unknown')}", "", "## Sample Counts"]
lines.append(f"- Total samples (all splits): {sum(split_counts.values())}")
for split, cnt in split_counts.items():
    lines.append(f"- {split.capitalize()} samples: {cnt}")

lines.append("\n## Signal Characteristics")
if sampling_hz:
    lines.append(f"- Sampling frequency: {sampling_hz} Hz")
else:
    lines.append("- Sampling frequency: Unknown")
if ecg_len_sec:
    lines.append(f"- ECG window duration: {ecg_len_sec:.2f} seconds")
else:
    lines.append("- ECG window duration: Unknown")

lines.append("\n## Missing Vital Sign Data")
for split, info in missing_vitals.items():
    lines.append(f"- {split}: {info}")

lines.append("\n## Duplicate ECG Windows (Exact) Across Dataset")
lines.append(f"- Number of exact duplicate windows detected: {duplicate_total}")

os.makedirs(os.path.dirname(REPORT_PATH), exist_ok=True)
with open(REPORT_PATH, "w", encoding="utf-8") as f:
    f.write("\n".join(lines))

print(f"Dataset statistics report written to {REPORT_PATH}")
