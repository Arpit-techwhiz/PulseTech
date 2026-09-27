@echo off
title PulseTech - Live Website Public Tunnel
cd /d "%~dp0"
echo ================================================================
echo      PULSETECH PATIENT MONITORING - LIVE PUBLIC WEBSITE
echo ================================================================
echo.
echo Launching encrypted Cloudflare Tunnel to port 3001...
echo Look below for your public "https://*.trycloudflare.com" link!
echo.
.\cloudflared.exe tunnel --url http://localhost:3001
pause
