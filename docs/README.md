# PulseTech — Intelligent Patient Monitoring System
**Version 2.4.1 | ESP32-S3 + TinyML + Node.js + WebSocket**

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────┐
│                   EDGE LAYER                        │
│  ESP32-S3 + MAX30105 + DS18B20 + AD8232             │
│  ┌─────────────────────────────────────────────┐    │
│  │  TinyML On-Device Risk Scoring (INT8 LSTM)  │    │
│  │  ECG · HR · SpO2 · Temperature              │    │
│  └──────────────┬──────────────────────────────┘    │
└─────────────────┼───────────────────────────────────┘
                  │ WebSocket / MQTT / REST
┌─────────────────▼───────────────────────────────────┐
│                 LOCAL SERVER                         │
│  Node.js + Express + WebSocket + SQLite              │
│  ┌────────────┐ ┌────────────┐ ┌──────────────┐    │
│  │ JWT Auth   │ │ Risk Engine│ │ CDSS Engine  │    │
│  │ RBAC       │ │ TinyML v2  │ │ Predictions  │    │
│  └────────────┘ └────────────┘ └──────────────┘    │
└─────────────────┬───────────────────────────────────┘
                  │ WebSocket broadcast
┌─────────────────▼───────────────────────────────────┐
│                  FRONTEND                            │
│  Vanilla JS + Chart.js (React-ready architecture)   │
│  Dashboard · ECG · EHR · Appointments · AI Panel    │
└─────────────────────────────────────────────────────┘
```

---

## Project Structure

```
pulsetech/
├── frontend/
│   ├── index.html          # Single-page app shell (React-migratable)
│   ├── app.js              # Complete frontend engine (~400 LOC)
│   ├── manifest.json       # PWA manifest
│   └── sw.js               # Service worker (offline support)
│
├── backend/
│   ├── package.json
│   └── src/
│       └── server.js       # Express + WebSocket + SQLite + MQTT bridge
│
└── docs/
    ├── esp32_firmware.ino  # Complete Arduino sketch for ESP32-S3
    └── README.md           # This file
```

---

## Quick Start

### 1. Frontend Only (Demo Mode)
```bash
# Just open the HTML directly in a browser
open frontend/index.html
# Login with any credentials
# All data is simulated in-browser
```

### 2. Full Stack
```bash
# Backend
cd backend
npm install
npm run dev

# Open browser at:
http://localhost:3001
```

### 3. With Real ESP32
```bash
# 1. Flash firmware
# Open docs/esp32_firmware.ino in Arduino IDE
# Install libraries:
#   - WebSocketsClient (Markus Sattler)
#   - ArduinoJson
#   - PubSubClient
#   - MAX3010x (SparkFun)
#   - DallasTemperature
#   - OneWire

# 2. Configure firmware
# Edit: WIFI_SSID, WIFI_PASSWORD, WS_HOST

# 3. Get JWT token
curl -X POST http://localhost:3001/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"dr.arpit","password":"doctor123"}'

# 4. Set token in firmware: JWT_TOKEN = "your_token_here"
# 5. Flash and connect
```

---

## API Reference

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| POST | `/api/auth/login` | — | Get JWT token |
| GET | `/api/auth/me` | JWT | Current user |
| POST | `/api/sensor-data` | JWT | ESP32 data ingestion |
| GET | `/api/sensor-data/:id` | JWT | Patient sensor history |
| GET | `/api/patient-history/:id` | JWT | Full patient record |
| POST | `/api/risk-analysis` | JWT | Run TinyML risk analysis |
| POST | `/api/appointments` | JWT | Book appointment |
| GET | `/api/appointments` | JWT | List all appointments |
| GET | `/api/alerts/:id` | JWT | Patient alerts |
| GET | `/api/health` | — | System health |

### WebSocket Protocol
```
ws://localhost:3001/ws

Client → Server:
{ "type": "AUTH", "token": "<jwt>" }
{ "type": "SENSOR_DATA", "hr": 72, "spo2": 98, "temperature": 36.6, "ecg": 0.5 }

Server → Client:
{ "type": "CONNECTED", "clientId": "..." }
{ "type": "AUTH_OK", "user": {...} }
{ "type": "VITALS", "hr": 72, "spo2": 98, "risk_score": 12, "risk_level": "LOW", ... }
```

### Example: ESP32 REST Fallback
```bash
curl -X POST http://localhost:3001/api/sensor-data \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "patient_id": "PT-2024-0381",
    "hr": 88,
    "spo2": 93,
    "temperature": 38.8,
    "sys_bp": 140,
    "dia_bp": 90,
    "ecg_sample": 1.2,
    "device_id": "ESP32-S3-NODE01"
  }'
```

---

## TinyML Risk Engine

### Algorithm (v2.1)
```
Score = 0
if HR > 100: score += (HR - 100) × 0.8   → Tachycardia
if HR < 50:  score += (50 - HR)  × 1.2   → Bradycardia
if SpO2 < 95: score += (95-SpO2) × 3.5   → Hypoxia
if Temp > 38: score += (Temp-38) × 4.0   → Fever
if Temp < 36: score += (36-Temp) × 3.0   → Hypothermia
score += LSTM_trend_penalty × 0.5         → Deterioration trend
Score = clamp(score, 0, 100)

LOW:    0 – 30   (green)
MEDIUM: 31 – 60  (amber)
HIGH:   61 – 100 (red → emergency protocol)
```

### Appointment Priority Score
```
Priority = (Symptom_Severity × 10) + (Age_Factor × 5) + (Risk_Score × 0.08)
Age_Factor: >65 → 3 | >50 → 2 | >30 → 1 | else → 0
Symptom_Severity: Routine=1, Fever=3, Breathlessness=5, Chest Pain=7, Emergency=9
```

---

## Hardware BOM

| Component | Model | Purpose |
|-----------|-------|---------|
| MCU | ESP32-S3 DevKit | Main processor + WiFi/BT |
| HR + SpO2 | MAX30105 | Pulse oximetry |
| Temperature | DS18B20 | Body temperature |
| ECG | AD8232 | Electrocardiogram |
| OLED | SSD1306 128×64 | Local display |
| Power | Li-Po 3.7V 2500mAh | Battery |
| Enclosure | 3D printed | Wearable mount |

---

## Security

- JWT tokens expire in 8 hours
- Passwords hashed with bcrypt (salt rounds: 10)
- All endpoints protected with Bearer token auth
- RBAC: Doctor, Patient, Admin roles
- AES-256 data encryption (configure in `.env`)
- HTTPS/WSS in production (use nginx reverse proxy)

### Production `.env`
```env
PORT=3001
JWT_SECRET=your_super_secret_key_min_32_chars
DB_PATH=/var/data/pulsetech.db
NODE_ENV=production
```

---

## Cloud Deployment (Optional)

```bash
# Docker
docker build -t pulsetech .
docker run -p 3001:3001 -e JWT_SECRET=secret pulsetech

# Or deploy to Railway / Render / Fly.io
# ESP32 just needs to point to the cloud URL
```

---

## Demo Credentials

| User | Password | Role |
|------|----------|------|
| dr.arpit | doctor123 | Doctor |
| patient01 | patient123 | Patient |
| admin | admin123 | Admin |

---

*Built with ❤️ by Arpit Chaudhary — MMMUT Gorakhpur IoT Lab*
