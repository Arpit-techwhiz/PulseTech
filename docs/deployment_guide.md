# PulseTech Deployment & Integration Guide

This guide outlines how to configure, run, and deploy the PulseTech Intelligent Patient Monitoring System with the integrated deep learning ECG classifier and Health Risk Assessment Engine.

---

## System Requirements

- **Python**: 3.11.x
- **Node.js**: >= 18.0.0
- **Docker & Docker Compose** (Optional, for containerized deployments)

---

## 1. Local Development Setup

### Step 1: Install Python Dependencies
Ensure Python 3.11 is active, and install the required machine learning packages:
```bash
# From workspace root
py -3.11 -m pip install -r requirements.txt
```

### Step 2: Install Node.js Dependencies
Navigate to the `backend` folder and install dependencies:
```bash
cd backend
npm install
```

---

## 2. Running the System Locally

### Step 1: Start the Python AI Service
The Flask AI service serves the morphology classifier and risk engine on port 5000:
```bash
# From workspace root
py -3.11 risk_engine/ai_service.py
```
*Note: The AI service will check for the presence of the trained Keras model (`models/best_ecg_model.keras`). If it does not exist, it will log a warning and run in simulated/fallback mode until training completes.*

### Step 2: Start the Node.js Server
Open a separate terminal window, navigate to the `backend` folder, and start the backend:
```bash
cd backend
npm run dev
```
The server will boot on port `3001` and expose the REST endpoints and the WebSocket route (`ws://localhost:3001/ws`).

### Step 3: Open the Dashboard
Open `dashboard/index.html` (or `frontend/index.html`) directly in a web browser, or access it through the server:
- Open a browser and visit: `http://localhost:3001`
- Login using demo credentials:
  - **Username**: `dr.arpit`
  - **Password**: `doctor123`

---

## 3. Training and Evaluation

If you need to retrain the models or run evaluation:
```bash
# 1. Download database
py -3.11 preprocessing/download.py

# 2. Preprocess, resample, and segment beats
py -3.11 preprocessing/preprocess.py

# 3. Train all 3 architectures and select the best
py -3.11 training/train.py

# 4. Run clinical evaluation and generate plots
py -3.11 evaluation/evaluate.py

# 5. Convert model to Float32 & INT8 TFLite arrays
py -3.11 tflite/convert_tflite.py
```

---

## 4. Docker Container Deployment

To launch the complete Node.js + Flask AI + SQLite system inside Docker:

```bash
# From workspace root, start the multi-container stack
cd deployment
docker-compose up --build -d
```

This starts:
- **`ai_service`**: Exposed at port `5000` (runs the Python risk model).
- **`backend`**: Exposed at port `3001` (runs Node.js Express/WS and SQLite database, serving frontend assets).
- **`pulsetech-data`**: Persistent volume mounting for the SQLite database.

To stop the services:
```bash
docker-compose down
```
