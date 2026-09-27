import os
import json
import numpy as np

PROJECT_ROOT = r"C:\Users\arpit\OneDrive\Desktop\pulsetech"
METADATA_PATH = os.path.join(PROJECT_ROOT, "metadata", "dataset_provenance.json")
REPORT_PATH = os.path.join(PROJECT_ROOT, "reports", "dataset_reconstruction.md")

# Load provenance metadata
with open(METADATA_PATH, "r", encoding="utf-8") as f:
    meta = json.load(f)

# Load auxiliary reports if they exist
audit_path = os.path.join(PROJECT_ROOT, "reports", "dataset_audit.md")
leakage_path = os.path.join(PROJECT_ROOT, "reports", "data_leakage_audit.md")

def read_file(p):
    if os.path.exists(p):
        with open(p, "r", encoding="utf-8") as f:
            return f.read()
    return None

audit_content = read_file(audit_path)
leakage_content = read_file(leakage_path)

lines = ["# Dataset Reconstruction Report", "", f"**Generated:** {meta.get('generated_at', 'unknown')}", "", "## What we know (verified)", ""]
for k, v in meta.items():
    if v not in [None, "", [], {}, False]:
        lines.append(f"- **{k}**: {v}")

lines.append("\n## What we do NOT know (missing)")
critical = ["patient_ids_available", "label_mapping", "alignment_method"]
for field in critical:
    if not meta.get(field, False):
        lines.append(f"- **{field}**: missing / not recorded")

lines.append("\n## What can be reconstructed?")
if meta.get('split_counts'):
    lines.append("- Split sizes (train/val/test) recovered from NPZ keys.")
if meta.get('source_contributions'):
    lines.append("- Approximate source contribution counts derived from any `source_*` arrays.")
if meta.get('sampling_frequency_hz'):
    lines.append("- Sampling frequency inferred from stored `sampling_rate` or ECG shape.")
if meta.get('ecg_length_seconds'):
    lines.append("- ECG signal duration computed from timesteps and sampling rate.")

lines.append("\n## Assumptions made")
lines.append("- Patient identifiers were not stored; we cannot verify patient‑level leakage.")
lines.append("- Label mapping between PTB‑XL and the 10‑class schema is unknown; existing one‑hot labels are taken as ground truth.")
lines.append("- Vital‑sign alignment with ECG windows is assumed correct based on the preprocessing pipeline, but no explicit alignment metadata is present.")

lines.append("\n## Related reports")
if audit_content:
    lines.append("- [Dataset Audit](dataset_audit.md)")
if leakage_content:
    lines.append("- [Leakage Audit](data_leakage_audit.md)")

os.makedirs(os.path.dirname(REPORT_PATH), exist_ok=True)
with open(REPORT_PATH, "w", encoding="utf-8") as f:
    f.write("\n".join(lines))
print(f"Dataset reconstruction report written to {REPORT_PATH}")
