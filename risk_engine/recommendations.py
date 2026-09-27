def get_recommendation_and_reasoning(overall_risk, arr_desc, brady_desc, tachy_desc, hypox_desc, fever_desc, stress_desc, p_ischemia, p_infarction):
    """
    Determines clinical severity level, emergency response action, and detailed reasoning
    incorporating acute conditions (Ischemia, Infarction) and overall health risk.
    """
    vitals_logs = []
    if "High" in arr_desc or "Moderate" in arr_desc: vitals_logs.append("arrhythmia morphology")
    if "High" in brady_desc or "Moderate" in brady_desc: vitals_logs.append("bradycardia")
    if "High" in tachy_desc or "Moderate" in tachy_desc: vitals_logs.append("tachycardia")
    if "High" in hypox_desc or "Moderate" in hypox_desc: vitals_logs.append("hypoxemia")
    if "High" in fever_desc or "Moderate" in fever_desc: vitals_logs.append("elevated temperature/infection response")
    if "High" in stress_desc or "Moderate" in stress_desc: vitals_logs.append("cardiovascular stress")
    
    if p_infarction > 0.40:
         vitals_logs.append("potential acute Myocardial Infarction (heart attack)")
    if p_ischemia > 0.45:
         vitals_logs.append("myocardial ischemia (restricted blood flow)")
         
    drivers_str = ", ".join(vitals_logs) if vitals_logs else "all parameters within normal limits"

    # Emergency state overrides
    if p_infarction > 0.40:
        level = "CRITICAL / CODE BLUE"
        action = "ACUTE MYOCARDIAL INFARCTION SUSPECTED. Activate emergency code immediately. Administer chewable aspirin (162-325 mg), establish IV access, and begin continuous oxygenation."
        reasoning = f"Emergency clinical state (Risk: {overall_risk}%). Model detected strong morphology markers indicating ST-Elevation Myocardial Infarction (Probability {p_infarction*100:.1f}%). Immediate cardiac catheterization team notification is required."
        color = "red"
    elif p_ischemia > 0.45:
        level = "HIGH / EMERGENCY"
        action = "ACUTE MYOCARDIAL ISCHEMIA DETECTED. Place patient on bed rest, perform urgent 12-lead ECG, monitor cardiac enzymes, and consult cardiology immediately."
        reasoning = f"High alert clinical state (Risk: {overall_risk}%). ECG ST-depression morphology indicative of myocardial ischemia (Probability {p_ischemia*100:.1f}%). High risk of progression to infarction."
        color = "red"
    elif overall_risk <= 30:
        level = "LOW"
        action = "Continue routine patient telemetry and vitals logging. Patient is stable."
        reasoning = f"Low risk state (Overall score: {overall_risk}%). Vitals and ECG morphology show normal baseline physiological trends."
        color = "green"
    elif overall_risk <= 60:
        level = "MODERATE"
        action = "Schedule non-urgent clinical review. Consult attending physician to inspect ECG waveform details."
        reasoning = f"Moderate risk state (Overall score: {overall_risk}%). Flagged due to: {drivers_str}. Vitals indicate early signs of deviation that warrant diagnostic inspection."
        color = "amber"
    elif overall_risk <= 85:
        level = "HIGH"
        action = "Escalate telemetry frequency. Immediate medical evaluation recommended. Notify charge nurse and prepare bedside diagnostics."
        reasoning = f"High risk state (Overall score: {overall_risk}%). Critical physiological deviations detected in: {drivers_str}. require immediate diagnostic review."
        color = "red"
    else:
        level = "CRITICAL"
        action = "CRITICAL STATE. Activate emergency medical response / code team immediately."
        reasoning = f"Life-threatening clinical state (Overall score: {overall_risk}%). Multiple organ systems showing severe stress: {drivers_str}. Immediate clinical support required."
        color = "red"
        
    return {
        "level": level,
        "action": action,
        "reasoning": reasoning,
        "color": color
    }
