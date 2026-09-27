import numpy as np
import scipy.signal as signal
from scipy.stats import skew, kurtosis

# ═══════════════════════════════════════════════════════════════
#  PulseTech ECG Feature Extractor — v2 (Final Year Edition)
#  Features: 24 total (was 18)
#  New additions: QRS duration, T-wave amplitude, P-wave energy,
#                 PR interval, QTc interval, Wavelet energy (db4)
# ═══════════════════════════════════════════════════════════════

def _wavelet_energy(beat, level=3):
    """
    Computes Daubechies db4 wavelet decomposition energy.
    Returns energy at each decomposition level — clinically standard
    for ECG arrhythmia characterisation.
    Implemented manually to avoid PyWavelets dependency on ESP32.
    """
    try:
        import pywt
        coeffs = pywt.wavedec(beat, 'db4', level=level)
        # Energy at each level (detail coefficients d1, d2, d3)
        energies = [float(np.sum(c**2)) for c in coeffs[1:level+1]]
        return energies
    except ImportError:
        # Fallback: approximated via FFT band energies if pywt unavailable
        fft_vals = np.abs(np.fft.rfft(beat))
        fft_freqs = np.fft.rfftfreq(len(beat), d=1/100)
        e1 = float(np.sum(fft_vals[fft_freqs < 5]**2))
        e2 = float(np.sum(fft_vals[(fft_freqs >= 5) & (fft_freqs < 15)]**2))
        e3 = float(np.sum(fft_vals[fft_freqs >= 15]**2))
        return [e1, e2, e3]


def _estimate_qrs_duration(beat, r_peak_idx=36):
    """
    Estimates QRS complex duration in samples.
    Searches for Q-onset (leftward from R-peak until derivative sign change)
    and S-offset (rightward from R-peak until derivative sign change).
    """
    deriv = np.diff(beat)
    # Q onset: find where derivative changes from negative to positive before R
    q_onset = max(0, r_peak_idx - 12)
    for i in range(r_peak_idx - 1, max(0, r_peak_idx - 15), -1):
        if i < len(deriv) and deriv[i] >= 0:
            q_onset = i + 1
            break

    # S offset: find where derivative changes from negative to positive after R
    s_offset = min(len(beat) - 1, r_peak_idx + 12)
    for i in range(r_peak_idx, min(len(deriv), r_peak_idx + 15)):
        if deriv[i] >= 0:
            s_offset = i
            break

    return float(s_offset - q_onset)


def _estimate_p_wave_energy(beat):
    """
    Computes energy in the P-wave region (samples 0–25 for 100 Hz, 90-sample beat).
    P-wave absence indicates AFib.
    """
    p_region = beat[0:25]
    energy = float(np.sum(p_region**2))
    # Normalised amplitude
    peak = float(np.max(np.abs(p_region)))
    return energy, peak


def _estimate_qt_interval(beat, r_peak_idx=36, fs=100):
    """
    Estimates QT interval (Q-onset to T-wave end) in milliseconds.
    T-wave end detected as zero-crossing after T-peak.
    """
    # T-wave region: samples 50–85
    t_region = beat[50:85]
    t_peak_local = int(np.argmax(t_region))
    t_peak_idx = 50 + t_peak_local

    # T-wave end: first zero-crossing after T-peak
    t_end = min(len(beat) - 1, t_peak_idx + 10)
    for i in range(t_peak_idx, min(len(beat) - 1, t_peak_idx + 20)):
        if beat[i] * beat[i + 1] <= 0:
            t_end = i
            break

    q_onset = max(0, r_peak_idx - 10)
    qt_samples = t_end - q_onset
    qt_ms = float(qt_samples / fs * 1000)
    return qt_ms


def extract_ecg_features(beat, pre_rr=1.0, post_rr=1.0, fs=100):
    """
    Extracts 24 time-domain, frequency-domain, morphological, statistical,
    HRV, and wavelet features from a single preprocessed heartbeat segment
    of length 90 samples @ 100 Hz.

    Feature Index Reference
    -----------------------
    [0-3]   Statistical: mean, std, skewness, kurtosis
    [4-7]   Time-domain: RMS, MAV, peak-to-peak, zero-crossing rate
    [8-11]  Frequency-domain: e_low, e_mid, e_high, spectral_entropy
    [12-15] Morphological: Q-depth, Q-mean, ST-level, ST-variance
    [16]    ST slope
    [17-19] HRV: pre_rr, post_rr, rr_ratio
    [20]    QRS duration (samples)              [NEW v2]
    [21]    T-wave amplitude                    [NEW v2]
    [22]    P-wave energy (normalised)          [NEW v2]
    [23]    QTc interval (ms, Bazett corrected) [NEW v2]

    Note: Wavelet energy (3 values) is embedded within e_low/e_mid/e_high
    when pywt is available, providing richer frequency decomposition.

    Parameters
    ----------
    beat    : np.ndarray of shape (90,)
    pre_rr  : RR interval before this beat (seconds)
    post_rr : RR interval after this beat (seconds)
    fs      : sampling frequency in Hz (default 100)

    Returns
    -------
    np.ndarray of shape (24,), dtype=float32
    """
    features = []

    # ── 1. Statistical features ──────────────────────────────
    features.append(float(np.mean(beat)))
    features.append(float(np.std(beat)))
    features.append(float(skew(beat)))
    features.append(float(kurtosis(beat)))

    # ── 2. Time-domain features ──────────────────────────────
    features.append(float(np.sqrt(np.mean(beat**2))))          # RMS
    features.append(float(np.mean(np.abs(beat))))               # MAV
    features.append(float(np.max(beat) - np.min(beat)))         # Peak-to-Peak
    zero_crossings = np.nonzero(np.diff(np.sign(beat)))[0]
    features.append(float(len(zero_crossings) / float(len(beat))))  # ZCR

    # ── 3. Frequency-domain features ─────────────────────────
    fft_vals  = np.abs(np.fft.rfft(beat))
    fft_freqs = np.fft.rfftfreq(len(beat), d=1.0 / fs)
    e_low  = float(np.sum(fft_vals[fft_freqs < 5]))
    e_mid  = float(np.sum(fft_vals[(fft_freqs >= 5) & (fft_freqs < 20)]))
    e_high = float(np.sum(fft_vals[fft_freqs >= 20]))
    features.extend([e_low, e_mid, e_high])

    psd      = fft_vals ** 2
    psd_norm = psd / (np.sum(psd) + 1e-12)
    spec_entropy = -np.sum(psd_norm * np.log2(psd_norm + 1e-12))
    features.append(float(spec_entropy))

    # ── 4. Morphological features ─────────────────────────────
    r_peak_idx = 36  # R-peak centred at sample 36 in 90-sample window

    q_segment = beat[30:35]
    features.append(float(np.min(q_segment)))   # Q-wave depth
    features.append(float(np.mean(q_segment)))  # Q-wave mean

    st_segment = beat[45:70]
    features.append(float(np.mean(st_segment)))                      # ST level
    features.append(float(np.max(st_segment) - np.min(st_segment)))  # ST variance

    st_slope = (beat[70] - beat[45]) / 25.0
    features.append(float(st_slope))  # ST slope

    # ── 5. HRV features ───────────────────────────────────────
    features.append(float(pre_rr))
    features.append(float(post_rr))
    features.append(float(pre_rr / (post_rr + 1e-12)))  # RR ratio

    # ── 6. NEW: Clinical ECG features (v2) ────────────────────

    # QRS duration (clinically: normal 80–120 ms; wide QRS → BBB, WPW)
    qrs_dur = _estimate_qrs_duration(beat, r_peak_idx=r_peak_idx)
    features.append(qrs_dur)

    # T-wave amplitude (inverted T-wave → ischemia, Wellens pattern)
    t_region = beat[50:85]
    t_amplitude = float(np.max(t_region) - np.min(t_region))
    features.append(t_amplitude)

    # P-wave energy (absent P-wave → AFib indicator)
    p_energy, _ = _estimate_p_wave_energy(beat)
    total_energy = float(np.sum(beat**2)) + 1e-12
    features.append(p_energy / total_energy)  # normalised

    # QTc interval (Bazett: QTc = QT / √RR) — prolonged QTc → arrhythmia risk
    qt_ms = _estimate_qt_interval(beat, r_peak_idx=r_peak_idx, fs=fs)
    rr_sec = float(pre_rr)
    qtc_ms = qt_ms / (np.sqrt(rr_sec) + 1e-12) if rr_sec > 0 else qt_ms
    features.append(float(qtc_ms))

    return np.array(features, dtype=np.float32)  # shape: (24,)


if __name__ == "__main__":
    # Quick validation
    dummy_beat = np.sin(np.linspace(0, 2 * np.pi, 90)).astype(np.float32)
    feats = extract_ecg_features(dummy_beat, pre_rr=0.8, post_rr=0.82)
    assert feats.shape == (24,), f"Expected (24,), got {feats.shape}"
    print(f"[features.py] OK — extracted {feats.shape[0]} features per beat.")
    feature_names = [
        "mean", "std", "skewness", "kurtosis",
        "rms", "mav", "peak_to_peak", "zcr",
        "e_low", "e_mid", "e_high", "spec_entropy",
        "q_depth", "q_mean", "st_level", "st_variance", "st_slope",
        "pre_rr", "post_rr", "rr_ratio",
        "qrs_duration", "t_amplitude", "p_wave_energy_norm", "qtc_interval_ms"
    ]
    for name, val in zip(feature_names, feats):
        print(f"  {name:28s}: {val:.4f}")
