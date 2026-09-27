@echo off
title PulseTech Launcher
echo ==================================================
echo STARTING PULSETECH MULTIMODAL EDGE AI PLATFORM
echo ==================================================

:: 1. Start Python Flask AI Service in a separate cmd window
echo Launching Flask AI Service (Port 5000)...
start "PulseTech AI Service" cmd /k "py -3.11 risk_engine/ai_service.py"

:: 2. Start Node.js Backend in a separate cmd window
echo Launching Node.js Backend (Port 3001)...
cd backend
start "PulseTech Node Server" cmd /k "npm start"

echo ==================================================
echo Both services are starting up in separate windows!
echo Open http://localhost:3001 in your browser.
echo ==================================================
pause