@echo off
echo Adding Windows Firewall rule for PulseTech port 3001...
netsh advfirewall firewall delete rule name="PulseTech Backend 3001" >nul 2>&1
netsh advfirewall firewall add rule name="PulseTech Backend 3001" dir=in action=allow protocol=TCP localport=3001
echo.
echo Done! ESP32 can now reach the backend.
pause
