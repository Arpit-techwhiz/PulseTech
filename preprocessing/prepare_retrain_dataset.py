import os
import sys
import json
import requests
import numpy as np
import pandas as pd
import scipy.signal as signal
import wfdb
import matplotlib.pyplot as plt
import seaborn as sns

# Ensure parent directory is in sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Import from existing preprocessing pipeline
from preprocessing.preprocess import apply_filters, resample_signal
from preprocessing.features import extract_ecg_features

# Global configuration
fs_target = 100
ecg_window_len = 90
pre_samples_target = 36
post_samples_target = 54

# Split ratios
TRAIN_RATIO = 0.70
VAL_RATIO = 0.15
TEST_RATIO = 0.15

# Vitals normal defaults
NORMAL_VITALS = {
    'age': 50.0,
    'gender': 0.0,  # 0: Male, 1: Female
    'hr': 75.0,
    'spo2': 98.0,
    'temp': 36.8,
    'bp_sys': 120.0,
    'bp_dia': 80.0,
    'resp_rate': 15.0,
    'symptom': 0.0  # 0: None
}

def download_afdb_subset(target_dir="dataset/afdb", records=["04015", "04043", "04048", "04126"]):
    """Downloads subset of MIT-BIH AFDB from PhysioNet."""
    os.makedirs(target_dir, exist_ok=True)
    print(f"Downloading AFDB subset to {target_dir}...")
    try:
        wfdb.dl_database("afdb", dl_dir=target_dir, records=records)
        print("AFDB subset downloaded successfully!")
        return True
    except Exception as e:
        print(f"Error downloading AFDB via wfdb: {e}")
        # Try custom download
        try:
            for r in records:
                for ext in ["dat", "hea", "atr", "qrs"]:
                    url = f"https://physionet.org/files/afdb/1.0.0/{r}.{ext}"
                    r_req = requests.get(url, headers={"User-Agent": "Mozilla/5.0"})
                    if r_req.status_code == 200:
                        with open(os.path.join(target_dir, f"{r}.{ext}"), "wb") as f:
                            f.write(r_req.content)
            print("AFDB subset fallback download completed!")
            return True
        except Exception as ex:
            print(f"Fallback download failed: {ex}")
            return False

def download_bidmc_subset(target_dir="dataset/bidmc", records=["bidmc01", "bidmc02", "bidmc03", "bidmc04", "bidmc05"]):
    """Downloads subset of BIDMC database from PhysioNet."""
    os.makedirs(target_dir, exist_ok=True)
    print(f"Downloading BIDMC subset to {target_dir}...")
    try:
        for r in records:
            # Download WFDB files
            for ext in ["hea", "dat"]:
                url = f"https://physionet.org/files/bidmc/1.0.0/{r}.{ext}"
                r_req = requests.get(url, headers={"User-Agent": "Mozilla/5.0"})
                if r_req.status_code == 200:
                    with open(os.path.join(target_dir, f"{r}.{ext}"), "wb") as f:
                        f.write(r_req.content)
            
            # Download Numerics CSV
            url_num = f"https://physionet.org/files/bidmc/1.0.0/bidmc_csv/{r}_Numerics.csv"
            r_req = requests.get(url_num, headers={"User-Agent": "Mozilla/5.0"})
            if r_req.status_code == 200:
                with open(os.path.join(target_dir, f"{r}_Numerics.csv"), "w", encoding="utf-8") as f:
                    f.write(r_req.text)
        print("BIDMC subset downloaded successfully!")
        return True
    except Exception as e:
        print(f"Error downloading BIDMC: {e}")
        return False

def download_normtemp(target_file="dataset/normtemp.csv"):
    """Downloads OpenIntro body temperature dataset."""
    os.makedirs(os.path.dirname(target_file), exist_ok=True)
    print(f"Downloading OpenIntro normtemp dataset to {target_file}...")
    url = "https://raw.githubusercontent.com/zhichaoluo/DataAnalysis/master/data/NORMTEMP.csv"
    try:
        r = requests.get(url)
        if r.status_code == 200:
            with open(target_file, "w", encoding="utf-8") as f:
                f.write(r.text)
            print("normtemp downloaded successfully!")
            return True
        else:
            print(f"Failed to download normtemp: status code {r.status_code}")
            return False
    except Exception as e:
        print(f"Error downloading normtemp: {e}")
        return False

def parse_rhythm_episodes(ann):
    """Parses rhythm episodes from annotation."""
    episodes = []
    current_rhythm = "(N"
    for sample, symbol, aux in zip(ann.sample, ann.symbol, ann.aux_note):
        if symbol == '+':
            current_rhythm = aux.strip()
        elif aux and aux.startswith('('):
            current_rhythm = aux.strip()
        episodes.append((sample, current_rhythm))
    return episodes

def get_rhythm_at_sample(sample, episodes):
    """Determines the active rhythm at a given sample index."""
    active_rhythm = "(N"
    for ep_sample, rhythm in episodes:
        if ep_sample <= sample:
            active_rhythm = rhythm
        else:
            break
    return 1 if "AFIB" in active_rhythm else 0

def process_mitdb(src_dir="dataset/mitdb", num_beats_per_record=8):
    """Processes samples from the local MIT-BIH Arrhythmia Database."""
    print("Processing MIT-BIH Arrhythmia Database...")
    records = [
        100, 101, 102, 103, 104, 105, 106, 107, 108, 109,
        111, 112, 113, 114, 115, 116, 117, 118, 119, 121,
        122, 123, 124, 200, 201, 202, 203, 205, 207, 208,
        209, 210, 212, 213, 214, 215, 217, 219, 220, 221,
        222, 223, 228, 230, 231, 232, 233, 234
    ]
    
    samples = []
    
    for r in records:
        record_path = os.path.join(src_dir, str(r))
        if not os.path.exists(record_path + ".hea"):
            continue
            
        record = wfdb.rdrecord(record_path)
        annotation = wfdb.rdann(record_path, 'atr')
        
        sig = record.p_signal[:, 0]  # Lead II
        fs_orig = record.fs
        resample_factor = fs_target / fs_orig
        sig_filtered = apply_filters(sig, fs_orig)
        sig_resampled = resample_signal(sig_filtered, fs_orig, fs_target)
        
        # Get rhythm annotations
        episodes = parse_rhythm_episodes(annotation)
        
        # Select R-peaks (excluding boundary beats)
        valid_indices = []
        for idx in range(1, len(annotation.sample) - 1):
            symbol = annotation.symbol[idx]
            # Standard beats
            if symbol in ['N', 'L', 'R', 'V', 'A', 'a', 'S', 'J', 'F', 'e', 'j', 'E', 'x']:
                valid_indices.append(idx)
                
        # Sample beats evenly
        if len(valid_indices) > num_beats_per_record:
            step = len(valid_indices) // num_beats_per_record
            selected_indices = valid_indices[::step][:num_beats_per_record]
        else:
            selected_indices = valid_indices
            
        for idx in selected_indices:
            ann_sample = annotation.sample[idx]
            r_peak_resampled = int(round(ann_sample * resample_factor))
            
            start = r_peak_resampled - pre_samples_target
            end = r_peak_resampled + post_samples_target
            
            if start < 0 or end > len(sig_resampled):
                continue
                
            beat = sig_resampled[start:end]
            std_val = np.std(beat)
            if std_val == 0:
                continue
            beat_norm = (beat - np.mean(beat)) / std_val
            
            # RR intervals in seconds
            pre_rr = (annotation.sample[idx] - annotation.sample[idx-1]) / fs_orig
            post_rr = (annotation.sample[idx+1] - annotation.sample[idx]) / fs_orig
            hr = float(60.0 / pre_rr)
            hr = min(max(hr, 30.0), 200.0)  # clamp to clinical ranges
            
            # Handcrafted ECG features
            handcrafted = extract_ecg_features(beat_norm, pre_rr, post_rr, fs=fs_target)
            
            # Clinical vitals vector
            vitals = [np.nan] * 9
            vitals[2] = hr  # HR is known
            
            # Labels: AF, Tachycardia, Bradycardia, Hypoxemia, Fever
            af_label = get_rhythm_at_sample(ann_sample, episodes)
            tachy_label = 1 if hr > 100.0 else 0
            brady_label = 1 if hr < 60.0 else 0
            hypox_label = -1
            fever_label = -1
            
            labels = [af_label, tachy_label, brady_label, hypox_label, fever_label]
            
            samples.append({
                'patient_id': f"mitdb_{r}",
                'record_id': str(r),
                'dataset_source': 'mitdb',
                'ecg': beat_norm,
                'vitals': vitals,
                'handcrafted': handcrafted,
                'labels': labels
            })
            
    print(f"Extracted {len(samples)} samples from mitdb.")
    return samples

def process_afdb(src_dir="dataset/afdb", num_beats_per_record=60):
    """Processes samples from the MIT-BIH AF Database."""
    print("Processing MIT-BIH AFDB...")
    records = ["04015", "04043", "04048", "04126"]
    samples = []
    
    for r in records:
        record_path = os.path.join(src_dir, r)
        if not os.path.exists(record_path + ".hea"):
            continue
            
        record = wfdb.rdrecord(record_path)
        ann_atr = wfdb.rdann(record_path, 'atr')
        ann_qrs = wfdb.rdann(record_path, 'qrs')
        
        sig = record.p_signal[:, 0]  # Channel 1
        fs_orig = record.fs
        resample_factor = fs_target / fs_orig
        sig_filtered = apply_filters(sig, fs_orig)
        sig_resampled = resample_signal(sig_filtered, fs_orig, fs_target)
        
        # Get rhythm annotations
        episodes = parse_rhythm_episodes(ann_atr)
        
        # Select R-peaks (excluding boundary beats)
        valid_peaks = ann_qrs.sample[1:-1]
        
        if len(valid_peaks) > num_beats_per_record:
            step = len(valid_peaks) // num_beats_per_record
            selected_peaks = valid_peaks[::step][:num_beats_per_record]
        else:
            selected_peaks = valid_peaks
            
        for peak_sample in selected_peaks:
            r_peak_resampled = int(round(peak_sample * resample_factor))
            
            start = r_peak_resampled - pre_samples_target
            end = r_peak_resampled + post_samples_target
            
            if start < 0 or end > len(sig_resampled):
                continue
                
            beat = sig_resampled[start:end]
            std_val = np.std(beat)
            if std_val == 0:
                continue
            beat_norm = (beat - np.mean(beat)) / std_val
            
            # Find matching peak index in original annotations to compute RR
            qrs_idx = np.where(ann_qrs.sample == peak_sample)[0][0]
            pre_rr = (ann_qrs.sample[qrs_idx] - ann_qrs.sample[qrs_idx-1]) / fs_orig
            post_rr = (ann_qrs.sample[qrs_idx+1] - ann_qrs.sample[qrs_idx]) / fs_orig
            
            hr = float(60.0 / pre_rr)
            hr = min(max(hr, 30.0), 200.0)
            
            handcrafted = extract_ecg_features(beat_norm, pre_rr, post_rr, fs=fs_target)
            
            vitals = [np.nan] * 9
            vitals[2] = hr
            
            af_label = get_rhythm_at_sample(peak_sample, episodes)
            tachy_label = 1 if hr > 100.0 else 0
            brady_label = 1 if hr < 60.0 else 0
            hypox_label = -1
            fever_label = -1
            
            labels = [af_label, tachy_label, brady_label, hypox_label, fever_label]
            
            samples.append({
                'patient_id': f"afdb_{r}",
                'record_id': r,
                'dataset_source': 'afdb',
                'ecg': beat_norm,
                'vitals': vitals,
                'handcrafted': handcrafted,
                'labels': labels
            })
            
    print(f"Extracted {len(samples)} samples from afdb.")
    return samples

def process_bidmc(src_dir="dataset/bidmc", num_beats_per_record=70):
    """Processes samples from the BIDMC PPG and Respiration Dataset."""
    print("Processing BIDMC dataset...")
    records = ["bidmc01", "bidmc02", "bidmc03", "bidmc04", "bidmc05"]
    samples = []
    
    for r in records:
        record_path = os.path.join(src_dir, r)
        numerics_path = os.path.join(src_dir, f"{r}_Numerics.csv")
        if not os.path.exists(record_path + ".hea") or not os.path.exists(numerics_path):
            continue
            
        record = wfdb.rdrecord(record_path)
        # Parse demographics from header comments
        age = np.nan
        gender = np.nan
        for comment in record.comments:
            if "<age>:" in comment:
                parts = comment.split()
                try:
                    age_idx = parts.index("<age>:") + 1
                    age = float(parts[age_idx])
                except Exception:
                    pass
            if "<sex>:" in comment:
                parts = comment.split()
                try:
                    sex_idx = parts.index("<sex>:") + 1
                    sex_str = parts[sex_idx].strip()
                    gender = 0.0 if sex_str == 'M' else 1.0
                except Exception:
                    pass
                    
        # Load numerics
        df_num = pd.read_csv(numerics_path)
        df_num.columns = [c.strip() for c in df_num.columns]
        
        # Load Lead II ECG signal
        ii_idx = -1
        for i, name in enumerate(record.sig_name):
            if 'II' in name:
                ii_idx = i
                break
        if ii_idx == -1:
            continue
            
        sig = record.p_signal[:, ii_idx]
        fs_orig = record.fs
        
        # Detect R-peaks using custom detector
        # Apply filters
        sig_filtered = apply_filters(sig, fs_orig)
        min_dist = int(0.3 * fs_orig)
        thresh = 0.5 * np.percentile(np.abs(sig_filtered), 95)
        peaks, _ = signal.find_peaks(np.abs(sig_filtered), distance=min_dist, height=thresh)
        
        # Filter boundary peaks
        valid_peaks = [p for p in peaks if p > fs_orig and p < len(sig) - fs_orig]
        
        # Sample beats
        if len(valid_peaks) > num_beats_per_record:
            step = len(valid_peaks) // num_beats_per_record
            selected_peaks = valid_peaks[::step][:num_beats_per_record]
        else:
            selected_peaks = valid_peaks
            
        for peak_sample in selected_peaks:
            t = peak_sample / float(fs_orig)
            
            # Segment beat at fs_orig
            pre_samples = int(0.36 * fs_orig)
            post_samples = int(0.54 * fs_orig)
            start = peak_sample - pre_samples
            end = peak_sample + post_samples
            
            beat = sig_filtered[start:end]
            # Resample to 100 Hz
            beat_resampled = resample_signal(beat, fs_orig, fs_target)
            
            # Pad or truncate to exactly 90 samples
            if len(beat_resampled) < ecg_window_len:
                beat_resampled = np.pad(beat_resampled, (0, ecg_window_len - len(beat_resampled)), 'constant')
            elif len(beat_resampled) > ecg_window_len:
                beat_resampled = beat_resampled[:ecg_window_len]
                
            std_val = np.std(beat_resampled)
            if std_val == 0:
                continue
            beat_norm = (beat_resampled - np.mean(beat_resampled)) / std_val
            
            # Align with numerics (closest time)
            closest_idx = (df_num['Time [s]'] - t).abs().idxmin()
            row = df_num.iloc[closest_idx]
            
            # Read variables
            hr = float(row['HR']) if 'HR' in row and not pd.isna(row['HR']) else np.nan
            spo2 = float(row['SpO2']) if 'SpO2' in row and not pd.isna(row['SpO2']) else np.nan
            resp = float(row['RESP']) if 'RESP' in row and not pd.isna(row['RESP']) else np.nan
            
            # Compute RR intervals for feature extraction
            # Find index in detected peaks
            pk_idx = np.where(peaks == peak_sample)[0][0]
            pre_rr = (peaks[pk_idx] - peaks[pk_idx-1]) / float(fs_orig) if pk_idx > 0 else 1.0
            post_rr = (peaks[pk_idx+1] - peaks[pk_idx]) / float(fs_orig) if pk_idx < len(peaks)-1 else 1.0
            
            handcrafted = extract_ecg_features(beat_norm, pre_rr, post_rr, fs=fs_target)
            
            vitals = [np.nan] * 9
            vitals[0] = age
            vitals[1] = gender
            vitals[2] = hr if not pd.isna(hr) else (60.0 / pre_rr)
            vitals[3] = spo2
            vitals[7] = resp
            
            # Check labels
            af_label = -1
            
            # Determine Tachycardia / Bradycardia from numeric HR if available, else RR
            hr_val = vitals[2]
            tachy_label = 1 if hr_val > 100.0 else 0
            brady_label = 1 if hr_val < 60.0 else 0
            
            # Hypoxemia threshold
            if not pd.isna(spo2):
                hypox_label = 1 if spo2 < 95.0 else 0
            else:
                hypox_label = -1
                
            fever_label = -1
            
            labels = [af_label, tachy_label, brady_label, hypox_label, fever_label]
            
            samples.append({
                'patient_id': f"bidmc_{r}",
                'record_id': r,
                'dataset_source': 'bidmc',
                'ecg': beat_norm,
                'vitals': vitals,
                'handcrafted': handcrafted,
                'labels': labels
            })
            
    print(f"Extracted {len(samples)} samples from bidmc.")
    return samples

def process_normtemp(target_file="dataset/normtemp.csv"):
    """Processes the OpenIntro body temperature dataset."""
    print("Processing OpenIntro normtemp dataset...")
    if not os.path.exists(target_file):
        return []
        
    df = pd.read_csv(target_file)
    samples = []
    
    for idx, row in df.iterrows():
        # OpenIntro columns: ID, BodyTemp, Gender, HeartRate
        # Gender: Male/Female
        gender_val = 0.0 if row['Gender'].strip().lower() == 'male' else 1.0
        # Convert BodyTemp to Celsius
        temp_c = (row['BodyTemp'] - 32.0) * 5.0 / 9.0
        hr_val = float(row['HeartRate'])
        
        # ECG is missing
        beat_norm = np.zeros(ecg_window_len)
        handcrafted = np.zeros(24)
        
        vitals = [np.nan] * 9
        vitals[1] = gender_val
        vitals[2] = hr_val
        vitals[4] = temp_c
        
        af_label = -1
        tachy_label = 1 if hr_val > 100.0 else 0
        brady_label = 1 if hr_val < 60.0 else 0
        hypox_label = -1
        fever_label = 1 if temp_c > 37.8 else 0
        
        labels = [af_label, tachy_label, brady_label, hypox_label, fever_label]
        
        samples.append({
            'patient_id': f"normtemp_{row['ID']}",
            'record_id': str(row['ID']),
            'dataset_source': 'normtemp',
            'ecg': beat_norm,
            'vitals': vitals,
            'handcrafted': handcrafted,
            'labels': labels
        })
        
    print(f"Extracted {len(samples)} samples from normtemp.")
    return samples

def build_retrain_dataset():
    """Main function to download, parse, audit, split, and save the dataset."""
    # 1. Downloads (already completed manually)
    # download_afdb_subset()
    # download_bidmc_subset()
    # download_normtemp()
    
    # 2. Process datasets
    mitdb_samples = process_mitdb()
    afdb_samples = process_afdb()
    bidmc_samples = process_bidmc()
    normtemp_samples = process_normtemp()
    
    all_samples = mitdb_samples + afdb_samples + bidmc_samples + normtemp_samples
    print(f"Total unified samples: {len(all_samples)}")
    
    # 3. Patient-wise Split
    # Collect all unique patients per dataset source
    patients_per_source = {}
    for sample in all_samples:
        src = sample['dataset_source']
        p_id = sample['patient_id']
        if src not in patients_per_source:
            patients_per_source[src] = set()
        patients_per_source[src].add(p_id)
        
    # Split patients per source to ensure balanced distribution of patient splits
    train_patients = set()
    val_patients = set()
    test_patients = set()
    
    for src, patients in patients_per_source.items():
        patients_list = sorted(list(patients))
        np.random.seed(42)  # for reproducibility
        np.random.shuffle(patients_list)
        
        n_patients = len(patients_list)
        n_train = int(n_patients * TRAIN_RATIO)
        n_val = int(n_patients * VAL_RATIO)
        
        train_p = patients_list[:n_train]
        val_p = patients_list[n_train:n_train+n_val]
        test_p = patients_list[n_train+n_val:]
        
        train_patients.update(train_p)
        val_patients.update(val_p)
        test_patients.update(test_p)
        
    # Group samples into splits
    splits = {'train': [], 'val': [], 'test': []}
    for sample in all_samples:
        p_id = sample['patient_id']
        if p_id in train_patients:
            splits['train'].append(sample)
        elif p_id in val_patients:
            splits['val'].append(sample)
        elif p_id in test_patients:
            splits['test'].append(sample)
            
    # Compile into numpy arrays
    data_arrays = {}
    for split_name, split_samples in splits.items():
        ecg_list = []
        vit_list = []
        lab_list = []
        
        for sample in split_samples:
            ecg_list.append(np.expand_dims(sample['ecg'], axis=-1))
            # Vitals concatenation: 9 vitals + 20 handcrafted
            # We must impute NaNs with normal defaults in the model input
            v_input = []
            vital_keys = ['age', 'gender', 'hr', 'spo2', 'temp', 'bp_sys', 'bp_dia', 'resp_rate', 'symptom']
            for i, val in enumerate(sample['vitals']):
                if pd.isna(val) or np.isnan(val):
                    v_input.append(NORMAL_VITALS[vital_keys[i]])
                else:
                    v_input.append(val)
            combined_vit = np.concatenate([v_input, sample['handcrafted']])
            vit_list.append(combined_vit)
            lab_list.append(sample['labels'])
            
        data_arrays[f"X_{split_name}_ecg"] = np.array(ecg_list, dtype=np.float32)
        data_arrays[f"X_{split_name}_vit"] = np.array(vit_list, dtype=np.float32)
        data_arrays[f"y_{split_name}"] = np.array(lab_list, dtype=np.float32)
        
    # Save unified dataset
    out_path = "dataset/retrain_dataset.npz"
    np.savez(out_path, **data_arrays)
    print(f"Saved preprocessed retrain dataset to {out_path}")
    
    # Save split metadata info
    split_info = {
        'train_patients': sorted(list(train_patients)),
        'val_patients': sorted(list(val_patients)),
        'test_patients': sorted(list(test_patients)),
        'train_count': len(splits['train']),
        'val_count': len(splits['val']),
        'test_count': len(splits['test'])
    }
    with open("metadata/split_info.json", "w") as f:
        json.dump(split_info, f, indent=4)
    print("Saved split info to metadata/split_info.json")
    
    # 4. Audit Dataset
    audit_dataset(all_samples, splits, data_arrays)

def audit_dataset(all_samples, splits, data_arrays):
    """Audits the unified dataset and generates reports/plots."""
    print("Auditing retrained dataset...")
    
    total_samples = len(all_samples)
    
    # Unique patients and records count
    unique_patients = set(s['patient_id'] for s in all_samples)
    unique_records = set(s['record_id'] for s in all_samples)
    
    # Counts per source
    source_counts = {}
    for s in all_samples:
        src = s['dataset_source']
        source_counts[src] = source_counts.get(src, 0) + 1
        
    # Class-wise label statistics (excluding -1)
    class_names = ['AF', 'Tachycardia', 'Bradycardia', 'Hypoxemia', 'Fever']
    label_matrix = np.array([s['labels'] for s in all_samples])
    
    class_stats = {}
    for i, name in enumerate(class_names):
        col = label_matrix[:, i]
        pos = np.sum(col == 1)
        neg = np.sum(col == 0)
        unk = np.sum(col == -1)
        class_stats[name] = {'pos': int(pos), 'neg': int(neg), 'unk': int(unk)}
        
    # Missing signals check (conceptual)
    missing_ecg_count = sum(1 for s in all_samples if np.all(s['ecg'] == 0))
    missing_ppg_count = sum(1 for s in all_samples if s['dataset_source'] in ['mitdb', 'afdb', 'normtemp'])
    missing_hr_count = sum(1 for s in all_samples if np.isnan(s['vitals'][2]))
    missing_spo2_count = sum(1 for s in all_samples if np.isnan(s['vitals'][3]))
    missing_temp_count = sum(1 for s in all_samples if np.isnan(s['vitals'][4]))
    
    # Duplicate samples check (based on ECG windows for samples where ECG is available)
    ecg_windows = [s['ecg'] for s in all_samples if not np.all(s['ecg'] == 0)]
    flat_ecg = np.array(ecg_windows).reshape(len(ecg_windows), -1)
    _, idx_counts = np.unique(flat_ecg, axis=0, return_counts=True)
    dup_samples = int((idx_counts > 1).sum())
    
    # Write audit report
    os.makedirs("reports", exist_ok=True)
    report_path = "reports/dataset_report.md"
    with open(report_path, "w") as f:
        f.write("# Retraining Dataset Audit Report\n\n")
        f.write(f"- **Total Samples**: {total_samples}\n")
        f.write(f"- **Number of Patients**: {len(unique_patients)}\n")
        f.write(f"- **Number of Records**: {len(unique_records)}\n\n")
        
        f.write("## Samples per Dataset Source\n")
        for src, cnt in source_counts.items():
            f.write(f"- **{src}**: {cnt} samples\n")
            
        f.write("\n## Patient Split Info\n")
        for split, split_list in splits.items():
            f.write(f"- **{split.capitalize()} split**: {len(split_list)} samples\n")
            
        f.write("\n## Positive / Negative / Unknown Counts per Class\n\n")
        f.write("| Condition | Positive (1) | Negative (0) | Unknown (-1) |\n")
        f.write("| --- | --- | --- | --- |\n")
        for name in class_names:
            stats = class_stats[name]
            f.write(f"| {name} | {stats['pos']} | {stats['neg']} | {stats['unk']} |\n")
            
        f.write("\n## Missing Signal Count\n")
        f.write(f"- **Missing/All-Zero ECG**: {missing_ecg_count} samples (from normtemp)\n")
        f.write(f"- **Missing PPG**: {missing_ppg_count} samples (from mitdb, afdb, and normtemp)\n")
        f.write(f"- **Missing HR**: {missing_hr_count} samples\n")
        f.write(f"- **Missing SpO2**: {missing_spo2_count} samples\n")
        f.write(f"- **Missing Temperature**: {missing_temp_count} samples\n\n")
        
        f.write("## Duplicate Windows\n")
        f.write(f"- **Exact Duplicate ECG Windows**: {dup_samples}\n")
        
    print(f"Dataset audit report written to {report_path}")
    
    # Generate class distribution plot
    plt.figure(figsize=(10, 6))
    pos_counts = [class_stats[name]['pos'] for name in class_names]
    neg_counts = [class_stats[name]['neg'] for name in class_names]
    unk_counts = [class_stats[name]['unk'] for name in class_names]
    
    x = np.arange(len(class_names))
    width = 0.25
    
    plt.bar(x - width, pos_counts, width, label='Positive (1)', color='forestgreen')
    plt.bar(x, neg_counts, width, label='Negative (0)', color='royalblue')
    plt.bar(x + width, unk_counts, width, label='Unknown (-1)', color='gray', alpha=0.5)
    
    plt.ylabel('Count')
    plt.title('Class Distribution across Unified Dataset (Retraining)')
    plt.xticks(x, class_names)
    plt.legend()
    plt.grid(True, axis='y', linestyle='--', alpha=0.7)
    plt.tight_layout()
    plot_path = "reports/class_distribution_retrained.png"
    plt.savefig(plot_path, dpi=150)
    plt.close()
    print(f"Class distribution plot saved to {plot_path}")

if __name__ == "__main__":
    build_retrain_dataset()
