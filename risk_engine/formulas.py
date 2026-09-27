import numpy as np

# Label mapping indices
# 0: Normal, 1: PVC, 2: PAC, 3: AFib, 4: Bradycardia, 5: Tachycardia, 6: HeartBlock, 7: BBB, 8: Ischemia, 9: Infarction

def compute_arrhythmia_risk(probs):
    """
    Computes Arrhythmia Risk (%) by aggregating probabilities of PVC, PAC, AFib, Heart Block, and BBB.
    """
    # Max probability of any arrhythmia class
    p_arr = float(np.max([probs[1], probs[2], probs[3], probs[6], probs[7]]))
    score = p_arr * 100.0
    
    if score < 30:
        desc = "Low Arrhythmia Risk: Stable cardiac morphology."
    elif score < 60:
        desc = f"Moderate Arrhythmia Risk: Early morphological variations detected (Probability {score:.1f}%)."
    else:
        desc = f"High Arrhythmia Risk: Critical ectopic beats or blocks detected (Probability {score:.1f}%)."
        
    return round(score, 1), desc

def compute_bradycardia_risk(hr, probs):
    """
    Computes Bradycardia Risk (%) based on heart rate and model prediction.
    """
    p_brady = float(probs[4])
    if hr < 60:
        score = (60.0 - hr) * 5.0 + p_brady * 50.0
    else:
        score = p_brady * 30.0
        
    score = min(100.0, max(0.0, score))
    
    if score < 30:
        desc = "No/Low Bradycardia Risk: Heart rate is within normal limits."
    elif score < 60:
        desc = f"Moderate Bradycardia Risk: Low heart rate ({hr} BPM) with probability {p_brady*100:.1f}%."
    else:
        desc = f"High Bradycardia Risk: Critical bradycardia detected ({hr} BPM). Risk of poor tissue perfusion."
        
    return round(score, 1), desc

def compute_tachycardia_risk(hr, probs):
    """
    Computes Tachycardia Risk (%) based on heart rate and model prediction.
    """
    p_tachy = float(probs[5])
    if hr > 100:
        score = (hr - 100.0) * 3.0 + p_tachy * 50.0
    else:
        score = p_tachy * 30.0
        
    score = min(100.0, max(0.0, score))
    
    if score < 30:
        desc = "No/Low Tachycardia Risk: Heart rate is within normal limits."
    elif score < 60:
        desc = f"Moderate Tachycardia Risk: Elevated heart rate ({hr} BPM) with probability {p_tachy*100:.1f}%."
    else:
        desc = f"High Tachycardia Risk: Critical tachycardia detected ({hr} BPM). High cardiovascular workload."
        
    return round(score, 1), desc

def compute_hypoxemia_risk(spo2):
    """
    Computes Hypoxemia Risk (%) based on SpO2.
    """
    if spo2 < 95:
        score = (95.0 - spo2) * 12.0 + max(0.0, 90.0 - spo2) * 8.0
    else:
        score = 0.0
        
    score = min(100.0, max(0.0, score))
    
    if score == 0:
        desc = "No Hypoxemia Risk: Oxygen saturation is normal."
    elif score < 30:
        desc = f"Low Hypoxemia Risk: Borderline low saturation ({spo2}%)."
    elif score < 65:
        desc = f"Moderate Hypoxemia Risk: Patient showing signs of hypoxia ({spo2}%)."
    else:
        desc = f"High Hypoxemia Risk: Severe hypoxemia ({spo2}%). Immediate oxygenation required."
        
    return round(score, 1), desc

def compute_fever_risk(temp, hr):
    """
    Computes Fever / Sepsis Risk (%) based on body temperature and heart rate.
    """
    if temp > 37.8:
        hr_factor = max(0.0, hr - 90) * 0.4
        score = (temp - 37.8) * 25.0 + hr_factor
    else:
        score = 0.0
        
    score = min(100.0, max(0.0, score))
    
    if score == 0:
        desc = "No Fever Risk: Body temperature is normal."
    elif score < 30:
        desc = f"Low Fever Risk: Low-grade fever ({temp:.1f}°C)."
    elif score < 60:
        desc = f"Moderate Fever Risk: Moderate fever ({temp:.1f}°C). Monitor infection markers."
    else:
        desc = f"High Fever Risk: High fever ({temp:.1f}°C) with systemic response (HR {hr} BPM); risk of sepsis."
        
    return round(score, 1), desc

def compute_cardiovascular_stress(age, bp_sys, bp_dia, resp_rate, spo2):
    """
    Computes Cardiovascular Stress (%) incorporating age, blood pressure, respiratory rate, and oxygen level.
    """
    # Age factor
    age_factor = max(0.0, age - 50) * 0.4
    
    # Blood pressure stress
    if bp_sys > 130 or bp_dia > 80: # Hypertension
        bp_stress = (bp_sys - 130) * 1.2 + (bp_dia - 80) * 1.8
    elif bp_sys < 90: # Hypotension
        bp_stress = (90 - bp_sys) * 3.0
    else:
        bp_stress = 0.0
        
    # Respiration stress
    resp_stress = max(0.0, resp_rate - 16) * 3.5
    
    # Oxygen deficit stress
    hypoxia_stress = max(0.0, 95.0 - spo2) * 2.5
    
    score = age_factor + bp_stress + resp_stress + hypoxia_stress
    score = min(100.0, max(0.0, score))
    
    if score < 30:
        desc = "Low Cardiovascular Stress: Stable hemodynamics."
    elif score < 60:
        desc = f"Moderate Cardiovascular Stress: Increased workload (BP: {int(bp_sys)}/{int(bp_dia)}, Resp: {int(resp_rate)}/min)."
    else:
        desc = f"High Cardiovascular Stress: Critical cardiovascular strain. High risk of myocardial fatigue."
        
    return round(score, 1), desc

def compute_overall_health_risk(arr, brady, tachy, hypox, fever, stress, p_ischemia, p_infarction):
    """
    Computes Overall Health Risk (%) using priority clinical weights.
    Critical conditions like Ischemia and Myocardial Infarction strongly override mean calculations.
    """
    # Ischemia and Infarction scores
    ischemia_score = p_ischemia * 100.0
    infarction_score = p_infarction * 100.0
    
    individual_risks = [arr, brady, tachy, hypox, fever, stress, ischemia_score, infarction_score]
    max_risk = max(individual_risks)
    mean_risk = sum(individual_risks) / len(individual_risks)
    
    # Priority weighting: 85% on the most severe condition, 15% on average
    score = (max_risk * 0.85) + (mean_risk * 0.15)
    
    # Hard override: If Myocardial Infarction prob is > 40%, overall risk must be at least 85%
    if infarction_score > 40.0:
        score = max(85.0, score)
        
    score = min(100.0, max(0.0, score))
    return round(score, 1)

def compute_confidence_score(probs):
    """
    Computes prediction confidence based on multi-label entropy:
    1.0 - 2.0 * mean(|p - round(p)|)
    Binds confidence between 0% and 100%.
    """
    probs_arr = np.array(probs)
    deviation = np.mean(np.abs(probs_arr - np.round(probs_arr)))
    confidence = 100.0 * (1.0 - 2.0 * deviation)
    return round(max(0.0, min(100.0, confidence)), 1)
