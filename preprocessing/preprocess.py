import os
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import wfdb
import numpy as np
import scipy.signal as signal
import matplotlib.pyplot as plt
import logging
from preprocessing.features import extract_ecg_features

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Patient-wise splits to prevent data leakage
TEST_RECORDS = [100, 103, 105, 111, 113, 117, 121, 123, 200, 202, 210, 212, 213, 219, 221, 231]
VAL_RECORDS = [101, 106, 115, 119, 208, 222]

def apply_filters(sig, fs=360):
    """
    Applies Butterworth bandpass (0.5 - 45 Hz) and IIR notch (60 Hz) filters.
    Removes baseline wander and powerline interference.
    """
    nyq = 0.5 * fs
    low = 0.5 / nyq
    high = 45.0 / nyq
    b, a = signal.butter(3, [low, high], btype='band')
    filtered_sig = signal.filtfilt(b, a, sig)
    
    w0 = 60.0 / nyq
    Q = 30.0
    b_notch, a_notch = signal.iirnotch(w0, Q)
    filtered_sig = signal.filtfilt(b_notch, a_notch, filtered_sig)
    
    return filtered_sig

def resample_signal(sig, orig_fs=360, target_fs=100):
    """Resamples signal from orig_fs to target_fs."""
    num_samples = int(len(sig) * target_fs / orig_fs)
    resampled_sig = signal.resample(sig, num_samples)
    return resampled_sig

def detect_r_peaks(sig, fs=360):
    """
    Dynamically detects R-peaks using SciPy peak-finding with adaptive thresholds.
    """
    filtered = apply_filters(sig, fs)
    min_dist = int(0.3 * fs) # minimum 300ms between beats
    # Adaptive threshold: 50% of the 95th percentile
    thresh = 0.5 * np.percentile(np.abs(filtered), 95)
    peaks, _ = signal.find_peaks(np.abs(filtered), distance=min_dist, height=thresh)
    return peaks

def evaluate_r_peak_detector(true_peaks, pred_peaks, tolerance_ms=50, fs=360):
    """
    Evaluates R-peak detector performance metrics (Sensitivity, Precision).
    """
    tolerance_samples = int(tolerance_ms * fs / 1000.0)
    tp = 0
    fp = 0
    fn = 0
    
    matched_preds = set()
    for true_p in true_peaks:
        # Look for a predicted peak within tolerance
        matches = [p for p in pred_peaks if abs(p - true_p) <= tolerance_samples]
        if matches:
            tp += 1
            matched_preds.update(matches)
        else:
            fn += 1
            
    fp = len(pred_peaks) - len(matched_preds)
    
    sensitivity = tp / (tp + fn) if (tp + fn) > 0 else 0
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0
    return sensitivity, precision

def synthesize_clinical_vitals(record_id, symbol, beat_index):
    """
    Deterministic clinical scenario synthesizer mapping ECG beats to 9 vital parameters
    and a 10-class multi-label output vector.
    """
    np.random.seed(record_id * 100000 + beat_index)
    
    age = int(38 + (record_id % 6) * 7 + np.random.randint(-4, 4))
    gender = int(record_id % 2) # 0: Male, 1: Female
    
    # Base normal values
    hr = float(72.0 + np.random.normal(0, 3.5))
    spo2 = float(98.2 + np.random.uniform(-0.8, 1.2))
    temp = float(36.6 + np.random.normal(0, 0.15))
    bp_sys = float(118.0 + np.random.normal(0, 4.0))
    bp_dia = float(78.0 + np.random.normal(0, 2.5))
    resp_rate = float(14.0 + np.random.normal(0, 0.8))
    symptom = 0 # 0: None, 1: Chest Pain, 2: Palpitations, 3: Dyspnea, 4: Dizziness, 5: Fatigue
    
    # Multi-label list:
    # [Normal, PVC, PAC, AFib, Bradycardia, Tachycardia, HeartBlock, BBB, Ischemia, Infarction]
    labels = [0] * 10
    
    is_pvc = symbol in ['V', 'E']
    is_pac = symbol in ['A', 'a', 'S', 'J']
    is_bbb = symbol in ['L', 'R']
    is_block = symbol in ['x']
    
    # Deterministic scenario assignment based on record number
    scenario = record_id % 9
    
    if scenario == 0:  # Bradycardia
        hr = float(48.0 + np.random.uniform(-6, 8))
        bp_sys = float(94.0 + np.random.normal(0, 4.0))
        bp_dia = float(58.0 + np.random.normal(0, 2.5))
        symptom = 4 # Dizziness
    elif scenario == 1:  # Tachycardia
        hr = float(116.0 + np.random.uniform(-8, 12))
        symptom = 2 # Palpitations
    elif scenario == 2:  # AFib
        hr = float(112.0 + np.random.uniform(-15, 25))
        symptom = 2 # Palpitations
        labels[3] = 1 # AFib
    elif scenario == 3:  # Ischemia
        spo2 = float(91.5 + np.random.uniform(-3, 2))
        bp_sys = float(142.0 + np.random.normal(0, 6.0))
        bp_dia = float(90.0 + np.random.normal(0, 4.0))
        symptom = 1 # Chest Pain
        labels[8] = 1 # Ischemia
    elif scenario == 4:  # Infarction
        spo2 = float(88.5 + np.random.uniform(-4, 2))
        bp_sys = float(158.0 + np.random.normal(0, 8.0))
        bp_dia = float(98.0 + np.random.normal(0, 5.0))
        symptom = 1 # Chest Pain
        labels[9] = 1 # Infarction
    elif scenario == 5:  # Hypoxemia
        spo2 = float(88.0 + np.random.uniform(-3, 2))
        resp_rate = float(23.0 + np.random.normal(0, 1.5))
        symptom = 3 # Dyspnea
    elif scenario == 6:  # Fever/Infection
        temp = float(38.9 + np.random.normal(0, 0.3))
        hr = float(94.0 + np.random.normal(0, 4.0))
        symptom = 5 # Fatigue
        
    if is_pvc:
        labels[1] = 1
    if is_pac:
        labels[2] = 1
    if is_block:
        labels[6] = 1
    if is_bbb:
        labels[7] = 1
        
    if hr < 60:
        labels[4] = 1
    elif hr > 100:
        labels[5] = 1
        
    if sum(labels[1:]) == 0:
        labels[0] = 1 # Set Normal index
        
    vitals = [age, gender, hr, spo2, temp, bp_sys, bp_dia, resp_rate, symptom]
    return vitals, labels

def augment_ecg_morphology(beat, label_vector):
    """
    Augments ECG segment based on ischemia and infarction states.
    Injects ST elevation/depression and pathological Q-waves.
    """
    augmented = np.copy(beat)
    t = np.arange(len(beat))
    
    if label_vector[8] == 1:  # Ischemia: ST depression
        st_depression = -0.35 * np.exp(-((t - 58) ** 2) / 64.0)
        augmented += st_depression
        
    if label_vector[9] == 1:  # Infarction: ST elevation + pathological Q-wave
        st_elevation = 0.45 * np.exp(-((t - 55) ** 2) / 54.0)
        q_wave = -0.55 * np.exp(-((t - 32) ** 2) / 3.0)
        augmented += st_elevation + q_wave
        
    return augmented

def apply_data_augmentation(beat):
    """Applies high-frequency noise, scaling, and baseline drift augmentations."""
    augmented = np.copy(beat)
    noise = np.random.normal(0, 0.025, len(beat))
    augmented += noise
    
    scale = np.random.uniform(0.92, 1.08)
    augmented *= scale
    
    t = np.arange(len(beat))
    drift = np.random.uniform(-0.08, 0.08) * np.sin(2 * np.pi * 0.5 * t / 100.0)
    augmented += drift
    
    return augmented

def segment_beats(sig, ann_sample, ann_symbol, record_id, orig_fs=360, target_fs=100):
    """
    Segments beats, aligns them around peaks, applies morphological augmentation,
    synthesizes corresponding vitals, and returns lists of processed elements.
    """
    resample_factor = target_fs / orig_fs
    resampled_sig = resample_signal(sig, orig_fs, target_fs)
    
    beats = []
    vitals_list = []
    labels = []
    
    pre_samples = 36
    post_samples = 54
    
    for idx, (sample, symbol) in enumerate(zip(ann_sample, ann_symbol)):
        r_peak_resampled = int(round(sample * resample_factor))
        start = r_peak_resampled - pre_samples
        end = r_peak_resampled + post_samples
        
        if start < 0 or end > len(resampled_sig):
            continue
            
        beat = resampled_sig[start:end]
        std = np.std(beat)
        if std == 0:
            continue
        beat_norm = (beat - np.mean(beat)) / std
        
        # Synthesize Vitals and Labels
        vitals, label_vec = synthesize_clinical_vitals(record_id, symbol, idx)
        
        # Inject pathological morphology if applicable
        beat_augmented = augment_ecg_morphology(beat_norm, label_vec)
        
        # Compute local RR intervals (in seconds)
        pre_rr = (ann_sample[idx] - ann_sample[idx-1]) / orig_fs if idx > 0 else 1.0
        post_rr = (ann_sample[idx+1] - ann_sample[idx]) / orig_fs if idx < len(ann_sample) - 1 else 1.0
        
        # Extract Handcrafted Features from preprocessed ECG wave
        handcrafted = extract_ecg_features(beat_augmented, pre_rr, post_rr, fs=100)
        
        # Concatenate vitals (9) + handcrafted features (18) = 27 features
        combined_vitals = np.concatenate([vitals, handcrafted])
        
        beats.append(beat_augmented)
        vitals_list.append(combined_vitals)
        labels.append(label_vec)
        
    return beats, vitals_list, labels

def process_database(src_dir="dataset/mitdb", out_dir="dataset"):
    """
    Aggregates database records, performs class-balanced splitting, and saves preprocessed files.
    """
    os.makedirs(out_dir, exist_ok=True)
    
    records = [
        100, 101, 102, 103, 104, 105, 106, 107, 108, 109,
        111, 112, 113, 114, 115, 116, 117, 118, 119, 121,
        122, 123, 124, 200, 201, 202, 203, 205, 207, 208,
        209, 210, 212, 213, 214, 215, 217, 219, 220, 221,
        222, 223, 228, 230, 231, 232, 233, 234
    ]
    
    train_ecg, train_vit, train_lab = [], [], []
    val_ecg, val_vit, val_lab = [], [], []
    test_ecg, test_vit, test_lab = [], [], []
    
    r_peak_sensitivities = []
    r_peak_precisions = []
    
    vis_done = False
    
    for r in records:
        record_path = os.path.join(src_dir, str(r))
        logger.info(f"Processing Record {r}...")
        
        record = wfdb.rdrecord(record_path)
        annotation = wfdb.rdann(record_path, 'atr')
        
        sig = record.p_signal[:, 0]
        filtered_sig = apply_filters(sig, fs=360)
        
        # Benchmark dynamic R-peak detector
        pred_peaks = detect_r_peaks(sig, fs=360)
        sens, prec = evaluate_r_peak_detector(annotation.sample, pred_peaks, fs=360)
        r_peak_sensitivities.append(sens)
        r_peak_precisions.append(prec)
        
        beats, vitals, labels = segment_beats(sig, annotation.sample, annotation.symbol, r)
        
        # Partition data patient-wise
        for b, v, l in zip(beats, vitals, labels):
            if r in TEST_RECORDS:
                test_ecg.append(b)
                test_vit.append(v)
                test_lab.append(l)
            elif r in VAL_RECORDS:
                val_ecg.append(b)
                val_vit.append(v)
                val_lab.append(l)
            else:
                # Class balancing downsampling: keep only 25% of Normal beats in train to prevent dominance
                if l[0] == 1 and np.random.uniform() > 0.25:
                    continue
                
                # Data augmentation for minority classes
                if l[0] == 0: # Arrhythmia beat
                    # Add original
                    train_ecg.append(b)
                    train_vit.append(v)
                    train_lab.append(l)
                    # Add augmented copy
                    b_aug = apply_data_augmentation(b)
                    train_ecg.append(b_aug)
                    train_vit.append(v)
                    train_lab.append(l)
                else:
                    train_ecg.append(b)
                    train_vit.append(v)
                    train_lab.append(l)
                    
        if not vis_done and r == 100:
            generate_vis_plots(sig, filtered_sig, annotation.sample, beats, labels)
            vis_done = True
            
    # Convert to arrays
    X_train_ecg = np.expand_dims(np.array(train_ecg), axis=-1)
    X_train_vit = np.array(train_vit)
    y_train = np.array(train_lab)
    
    X_val_ecg = np.expand_dims(np.array(val_ecg), axis=-1)
    X_val_vit = np.array(val_vit)
    y_val = np.array(val_lab)
    
    X_test_ecg = np.expand_dims(np.array(test_ecg), axis=-1)
    X_test_vit = np.array(test_vit)
    y_test = np.array(test_lab)
    
    logger.info(f"R-Peak Detector Performance: Sensitivity={np.mean(r_peak_sensitivities):.4f}, Precision={np.mean(r_peak_precisions):.4f}")
    logger.info(f"Dataset summary:")
    logger.info(f"Train ECG: {X_train_ecg.shape}, Vitals: {X_train_vit.shape}, Labels: {y_train.shape}")
    logger.info(f"Val ECG:   {X_val_ecg.shape}, Vitals: {X_val_vit.shape}, Labels: {y_val.shape}")
    logger.info(f"Test ECG:  {X_test_ecg.shape}, Vitals: {X_test_vit.shape}, Labels: {y_test.shape}")
    
    # Save datasets
    np_path = os.path.join(out_dir, "preprocessed_data.npz")
    np.savez(np_path, 
             X_train_ecg=X_train_ecg, X_train_vit=X_train_vit, y_train=y_train,
             X_val_ecg=X_val_ecg, X_val_vit=X_val_vit, y_val=y_val,
             X_test_ecg=X_test_ecg, X_test_vit=X_test_vit, y_test=y_test)
    logger.info(f"Saved preprocessed data to {np_path}")

def generate_vis_plots(raw_sig, filtered_sig, R_peaks, beats, labels):
    """Saves plots for visual verification of preprocessing stages."""
    os.makedirs("docs/plots", exist_ok=True)
    
    # Plot 1: Raw vs Filtered ECG Signal (first 2000 samples)
    plt.figure(figsize=(12, 6))
    plt.subplot(2, 1, 1)
    plt.plot(raw_sig[:2000], color='gray', alpha=0.7, label='Raw ECG')
    plt.title("ECG Preprocessing Stage: Raw vs Filtered Signal (Record 100)")
    plt.ylabel("Amplitude")
    plt.legend()
    plt.grid(True)
    
    plt.subplot(2, 1, 2)
    plt.plot(filtered_sig[:2000], color='blue', label='Filtered ECG (0.5 - 45 Hz)')
    r_peaks_in_range = [p for p in R_peaks if p < 2000]
    plt.scatter(r_peaks_in_range, filtered_sig[r_peaks_in_range], color='red', marker='x', label='R-Peaks')
    plt.xlabel("Samples (@ 360 Hz)")
    plt.ylabel("Amplitude")
    plt.legend()
    plt.grid(True)
    plt.tight_layout()
    plt.savefig("docs/plots/filtering_stage.png", dpi=150)
    plt.close()

    # Plot 2: Resampled Signal (360 Hz vs 100 Hz)
    resampled_sig = resample_signal(filtered_sig, 360, 100)
    plt.figure(figsize=(12, 4))
    time_orig = np.arange(2000) / 360.0
    time_resamp = np.arange(int(2000 * 100 / 360)) / 100.0
    plt.plot(time_orig * 360, filtered_sig[:2000], color='blue', alpha=0.4, label='360 Hz')
    plt.plot(time_resamp * 360, resampled_sig[:int(2000 * 100 / 360)], color='darkgreen', marker='.', markersize=4, label='Resampled to 100 Hz')
    plt.title("ECG Resampling Stage (360 Hz vs 100 Hz)")
    plt.xlabel("Equivalent 360Hz Sample Indices")
    plt.ylabel("Amplitude")
    plt.legend()
    plt.grid(True)
    plt.tight_layout()
    plt.savefig("docs/plots/resampling_stage.png", dpi=150)
    plt.close()

    # Plot 3: Segmented Beat Examples
    plt.figure(figsize=(10, 8))
    plt.plot(beats[0], color='blue', label="Example Preprocessed beat")
    plt.title("Segmented & Normalized Heartbeat Windows (90 samples @ 100 Hz)")
    plt.xlabel("Window Samples")
    plt.ylabel("Normalized Amplitude (Z-score)")
    plt.legend()
    plt.grid(True)
    plt.tight_layout()
    plt.savefig("docs/plots/segmentation_stage.png", dpi=150)
    plt.close()
    
    logger.info("Visualization plots saved to docs/plots/")

if __name__ == "__main__":
    process_database()
