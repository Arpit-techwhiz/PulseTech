@echo off
title PulseTech Multi-Service Launcher
cd /d "%~dp0"

echo ======================================================================
echo           STARTING PULSETECH MULTIMODAL EDGE AI PLATFORM
echo ======================================================================
echo.

:: 1. Start Python Flask AI Service (Port 5000)
echo [1/3] Launching Flask TinyML Risk Engine (Port 5000)...
start "PulseTech AI Service" cmd /k "cd /d "%~dp0" && py -3.11 risk_engine/ai_service.py"

:: 2. Start Node.js Backend Server (Port 3001)
echo [2/3] Launching Node.js Backend & WebSocket Server (Port 3001)...
start "PulseTech Node Server" cmd /k "cd /d "%~dp0backend" && npm start"

:: 3. Start Cloudflare Public Live Tunnel
echo [3/3] Launching Encrypted Cloudflare Live Tunnel...
if exist "%~dp0cloudflared.exe" (
    start "PulseTech Cloudflare Tunnel" cmd /k "cd /d "%~dp0" && .\cloudflared.exe tunnel --url http://localhost:3001"
) else if exist "C:\Program Files (x86)\cloudflared\cloudflared.exe" (
    start "PulseTech Cloudflare Tunnel" cmd /k ""C:\Program Files (x86)\cloudflared\cloudflared.exe" tunnel --url http://localhost:3001"
) else (
    echo [Warning] cloudflared.exe not found. Running locally without public tunnel.
)

echo.
echo ======================================================================
echo  All 3 services are launching in separate windows:
echo    - Python AI Service       : http://localhost:5000
echo    - Local Dashboard Server  : http://localhost:3001
echo    - Cloudflare Live Tunnel  : Look at the Tunnel window for your public link!
echo ======================================================================
echo.
echo Opening local dashboard in your browser in 3 seconds...
timeout /t 3 >nul
start http://localhost:3001

echo Done! Keep the service windows open while using PulseTech.
pause