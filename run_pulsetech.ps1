# PulseTech Multi-Service Automated Launcher
$Host.UI.RawUI.WindowTitle = "PulseTech Launcher"
Clear-Host

Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host "             PULSETECH MULTIMODAL EDGE AI PLATFORM LAUNCHER          " -ForegroundColor Cyan
Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host ""

$rootDir = $PSScriptRoot
$cloudflaredPath = Join-Path $rootDir "cloudflared.exe"
if (-not (Test-Path $cloudflaredPath)) {
    $cloudflaredPath = "C:\Program Files (x86)\cloudflared\cloudflared.exe"
}

# 1. Start Python Flask AI Service (Port 5000)
$pyPort = Get-NetTCPConnection -LocalPort 5000 -State Listen -ErrorAction SilentlyContinue
if ($pyPort) {
    Write-Host "[1/3] Python AI Service is ALREADY RUNNING on port 5000." -ForegroundColor Green
} else {
    Write-Host "[1/3] Starting Python TinyML Arrhythmia Service (Port 5000)..." -ForegroundColor Yellow
    Start-Process -FilePath "cmd.exe" -ArgumentList "/k", "cd /d `"$rootDir`" && py -3.11 risk_engine/ai_service.py"
    Start-Sleep -Seconds 2
}

# 2. Start Node.js Backend Server (Port 3001)
$nodePort = Get-NetTCPConnection -LocalPort 3001 -State Listen -ErrorAction SilentlyContinue
if ($nodePort) {
    Write-Host "[2/3] Node.js Platform Server is ALREADY RUNNING on port 3001." -ForegroundColor Green
} else {
    Write-Host "[2/3] Starting Node.js Backend & Telemetry Server (Port 3001)..." -ForegroundColor Yellow
    Start-Process -FilePath "cmd.exe" -ArgumentList "/k", "cd /d `"$rootDir\backend`" && npm start"
    Start-Sleep -Seconds 2
}

# 3. Start Cloudflare Tunnel
$cfProc = Get-Process -Name "cloudflared" -ErrorAction SilentlyContinue
if ($cfProc) {
    Write-Host "[3/3] Cloudflare Tunnel is ALREADY RUNNING (PID: $($cfProc.Id[0]))." -ForegroundColor Green
} else {
    Write-Host "[3/3] Starting Cloudflare Live Public Tunnel..." -ForegroundColor Yellow
    Start-Process -FilePath "cmd.exe" -ArgumentList "/k", "cd /d `"$rootDir`" && `"$cloudflaredPath`" tunnel --url http://localhost:3001"
    Start-Sleep -Seconds 4
}

# Retrieve Tunnel URL from Cloudflare metrics
$tunnelUrl = ""
try {
    $metrics = (Invoke-WebRequest -Uri "http://127.0.0.1:20241/metrics" -UseBasicParsing -TimeoutSec 3).Content
    if ($metrics -match 'userHostname="https://([^"]+)"') {
        $tunnelUrl = "https://" + $matches[1]
        $tunnelHost = $matches[1]
    }
} catch {}

Write-Host ""
Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host "  PULSETECH IS FULLY ACTIVE AND OPERATIONAL!" -ForegroundColor Green
Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Local Bedside Dashboard : http://localhost:3001" -ForegroundColor White

if ($tunnelUrl) {
    Write-Host "  Public Live Cloud Link  : $tunnelUrl" -ForegroundColor Yellow
    Set-Clipboard -Value $tunnelUrl -ErrorAction SilentlyContinue
    Write-Host "  (Public link copied to clipboard!)" -ForegroundColor Gray
} else {
    Write-Host "  Public Live Cloud Link  : Initializing... Check the Tunnel window." -ForegroundColor Yellow
}
Write-Host ""
Write-Host "Opening local dashboard in default browser..." -ForegroundColor Cyan
Start-Process "http://localhost:3001"
Write-Host ""
Write-Host "Press any key to exit this launcher window (services keep running)..." -ForegroundColor Gray
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
