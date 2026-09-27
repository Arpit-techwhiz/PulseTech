fetch("http://localhost:3001/api/sensor-data", {
  method: "POST",
  headers: {
    "X-Device-Key": "PULSETECH-ESP32-SECRET-2024",
    "Content-Type": "application/json"
  },
  body: JSON.stringify({
    patient_id: "PT-2024-0381",
    hr: 75, spo2: 98, temperature: 36.6, sys_bp: 120, dia_bp: 80, ecg_sample: 0.5, device_id: "TEST"
  })
}).then(r => r.text()).then(console.log).catch(console.error);
