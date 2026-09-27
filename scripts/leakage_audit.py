import os
import json
import numpy as np
from scipy.spatial.distance import cosine, correlation
from scipy.stats import pearsonr
# Attempt to import fastdtw; if unavailable, skip DTW calculation
try:
    from fastdtw import fastdtw
except ImportError:
    fastdtw = None

PROJECT_ROOT = r"C:\Users\arpit\OneDrive\Desktop\pulsetech"
NPZ_PATH = os.path.join(PROJECT_ROOT, "dataset", "preprocessed_data.npz")
METADATA_PATH = os.path.join(PROJECT_ROOT, "metadata", "dataset_provenance.json")
REPORT_PATH = os.path.join(PROJECT_ROOT, "reports", "data_leakage_audit.md")

npz = np.load(NPZ_PATH, allow_pickle=True)
with open(METADATA_PATH, "r", encoding="utf-8") as f:
    meta = json.load(f)

def get_ecg(split):
    key = f"X_{split}_ecg"
    return npz[key] if key in npz else None

splits = ["train", "val", "test"]
# Gather all ECG windows together with a simple identifier
windows = []
for split in splits:
    ecg = get_ecg(split)
    if ecg is None:
        continue
    for idx in range(ecg.shape[0]):
        windows.append((f"{split}_{idx}", ecg[idx].reshape(-1)))

# Function to compute similarity metrics between two vectors

def similarity_metrics(a, b):
    # Cosine similarity (1 - cosine distance)
    cos_sim = 1 - cosine(a, b)
    # Pearson correlation
    try:
        pearson_corr, _ = pearsonr(a, b)
    except Exception:
        pearson_corr = float('nan')
    # Correlation distance (1 - correlation)
    corr_dist = 1 - correlation(a, b) if a.size > 1 else float('nan')
    # DTW distance (if fastdtw available)
    if fastdtw:
        dtw_dist, _ = fastdtw(a, b)
    else:
        dtw_dist = None
    return cos_sim, pearson_corr, corr_dist, dtw_dist

# Identify potential leakage pairs: exact duplicates + high similarity (>0.99 cosine)
duplicate_pairs = []
high_sim_pairs = []
# Simple O(N^2) for demonstration; limit to first 200 windows to keep runtime reasonable
max_windows = min(200, len(windows))
for i in range(max_windows):
    id_i, vec_i = windows[i]
    for j in range(i+1, max_windows):
        id_j, vec_j = windows[j]
        if np.array_equal(vec_i, vec_j):
            duplicate_pairs.append((id_i, id_j))
            continue
        cos, pear, corr, dtw = similarity_metrics(vec_i, vec_j)
        if cos > 0.99:
            high_sim_pairs.append((id_i, id_j, cos, pear, corr, dtw))

# Write markdown report
lines = ["# Data Leakage Audit Report", "", f"**Generated:** {meta.get('generated_at', 'unknown')}", "", "## Exact Duplicate ECG Windows", ""]
if duplicate_pairs:
    for a, b in duplicate_pairs:
        lines.append(f"- {a} ↔ {b}")
else:
    lines.append("- No exact duplicate windows found among the sampled subset.")

lines.append("\n## Highly Similar Windows (Cosine > 0.99)")
if high_sim_pairs:
    lines.append("| Window A | Window B | Cosine | Pearson | CorrDist | DTW (if available) |")
    lines.append("|----------|----------|--------|---------|----------|--------------------|")
    for a, b, cos, pear, corr, dtw in high_sim_pairs:
        dtw_str = f"{dtw:.2f}" if dtw is not None else "N/A"
        lines.append(f"| {a} | {b} | {cos:.4f} | {pear:.4f} | {corr:.4f} | {dtw_str} |")
else:
    lines.append("- No highly similar windows detected in the sampled subset.")

lines.append("\n## Remarks")
lines.append("- This audit samples up to 200 windows for tractability. If the dataset is larger, consider increasing the sample size or using approximate nearest‑neighbor search.")
lines.append("- Missing patient identifiers limit the ability to detect cross‑split leakage via patient ID matching.")

os.makedirs(os.path.dirname(REPORT_PATH), exist_ok=True)
with open(REPORT_PATH, "w", encoding="utf-8") as f:
    f.write("\n".join(lines))
print(f"Data leakage audit report written to {REPORT_PATH}")
