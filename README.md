# PulseTech — AI-Powered Patient Monitoring System

PulseTech is an intelligent, edge-enabled healthcare monitoring platform that combines deep learning ECG waveform classification with a multi-vital risk engine to deliver real-time clinical decision support.

## Core Features

- **Stage 1: Deep Learning ECG Classifier**: A 1D CNN model trained on the MIT-BIH Arrhythmia Database to classify beats into the 5 standard AAMI classes (Normal, SVEB, VEB, Fusion, Unknown). Includes evaluations of ResNet1D, CNN + BiLSTM, and CNN + Attention architectures.
- **Stage 2: Health Risk Assessment Engine**: An explainable scoring engine that fuses ECG predictions with Heart Rate, SpO2, and Body Temperature to generate risk scores for clinical conditions (Cardiac Arrhythmia, Bradycardia, Tachycardia, Hypoxemia, Fever/Infection, Cardiovascular Stress).
- **Stage 3: TinyML Engine**: Quantizes and optimizes the trained Keras model into an INT8 TFLite model, offering benchmarking reports on model size, inference speed, RAM footprint, and ESP32-S3 compatibility.
- **Production Integration**: Async, throttled communication between the Node.js backend and a Flask AI service, ensuring 100Hz real-time ECG signal streaming while calling the AI model at 2Hz.

---

## Directory Structure

```
pulsetech/
├── dataset/             # Raw MIT-BIH recordings and preprocessed data
├── preprocessing/       # WFDB loading, noise removal, resampling (100Hz), segmenting
├── models/              # Candidate architectures and best saved models
├── training/            # Model training scripts (EarlyStopping, Checkpoint, TensorBoard)
├── evaluation/          # Confusion matrix, ROC, PR curve generation scripts
├── risk_engine/         # Medically explainable risk formulas and Flask AI API service
├── dashboard/           # Complete frontend SPA (WebSocket-enabled live monitoring)
├── deployment/          # Dockerfiles and Docker Compose configuration
├── tflite/              # Float32 and INT8 quantized TFLite models and benchmarks
├── docs/                # Firmware code, plots, and deployment guides
├── requirements.txt     # Python environment specifications
└── README.md            # Root documentation file
```

---

## Getting Started

### 1. Prerequisites
Ensure you have the following installed:
- Python 3.11
- Node.js >= 18.0.0
- Web browser (Chrome / Edge recommended)

### 2. Setup & Run
For detailed instructions, refer to the [docs/deployment_guide.md](file:///c:/Users/arpit/OneDrive/Desktop/pulsetech/docs/deployment_guide.md).

Quick start:
```bash
# 1. Install dependencies
pip install -r requirements.txt
cd backend && npm install && cd ..

# 2. Run Flask AI Service (starts on port 5000)
python risk_engine/ai_service.py

# 3. Run Node.js Server (starts on port 3001)
cd backend
npm run dev
```

Visit `http://localhost:3001` in your browser. Log in with:
- **Username**: `dr.arpit`
- **Password**: `doctor123`

---

*Developed by Arpit Chaudhary — MMMUT Gorakhpur IoT Lab*
