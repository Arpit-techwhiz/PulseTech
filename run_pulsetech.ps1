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
    for ($i = 0; $i -lt 20; $i++) {
        if (Get-NetTCPConnection -LocalPort 5000 -State Listen -ErrorAction SilentlyContinue) { break }
        Start-Sleep -Milliseconds 100
    }
}

# 2. Start Node.js Backend Server (Port 3001)
$nodePort = Get-NetTCPConnection -LocalPort 3001 -State Listen -ErrorAction SilentlyContinue
if ($nodePort) {
    Write-Host "[2/3] Node.js Platform Server is ALREADY RUNNING on port 3001." -ForegroundColor Green
} else {
    Write-Host "[2/3] Starting Node.js Backend & Telemetry Server (Port 3001)..." -ForegroundColor Yellow
    Start-Process -FilePath "cmd.exe" -ArgumentList "/k", "cd /d `"$rootDir\backend`" && npm start"
    for ($i = 0; $i -lt 20; $i++) {
        if (Get-NetTCPConnection -LocalPort 3001 -State Listen -ErrorAction SilentlyContinue) { break }
        Start-Sleep -Milliseconds 100
    }
}

# 3. Start Cloudflare Tunnel
$cfProc = Get-Process -Name "cloudflared" -ErrorAction SilentlyContinue
if ($cfProc) {
    Write-Host "[3/3] Cloudflare Tunnel is ALREADY RUNNING (PID: $($cfProc.Id[0]))." -ForegroundColor Green
} else {
    Write-Host "[3/3] Starting Cloudflare Live Public Tunnel..." -ForegroundColor Yellow
    Start-Process -FilePath "cmd.exe" -ArgumentList "/k", "cd /d `"$rootDir`" && `"$cloudflaredPath`" tunnel --url http://localhost:3001"
}

# Retrieve Tunnel URL from Cloudflare metrics with high-speed polling
$tunnelUrl = ""
$tunnelHost = ""
for ($i = 0; $i -lt 30; $i++) {
    try {
        $metrics = (Invoke-WebRequest -Uri "http://127.0.0.1:20241/metrics" -UseBasicParsing -TimeoutSec 1).Content
        if ($metrics -match 'userHostname="https://([^"]+)"') {
            $tunnelUrl = "https://" + $matches[1]
            $tunnelHost = $matches[1]
            break
        }
    } catch {}
    Start-Sleep -Milliseconds 200
}

$ghUrl = "https://arpit-techwhiz.github.io/PulseTech/frontend/"
if ($tunnelHost) {
    $ghUrl = "https://arpit-techwhiz.github.io/PulseTech/frontend/?bridge=$tunnelHost"
}

Write-Host ""
Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host "  PULSETECH IS FULLY ACTIVE AND OPERATIONAL!" -ForegroundColor Green
Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Official GitHub Pages Live  : $ghUrl" -ForegroundColor Yellow
Write-Host "  Local Bedside Dashboard     : http://localhost:3001" -ForegroundColor White
if ($tunnelUrl) {
    Write-Host "  Direct Cloudflare Stream    : $tunnelUrl" -ForegroundColor Cyan
    Set-Clipboard -Value $ghUrl -ErrorAction SilentlyContinue
    Write-Host "  (GitHub Pages live link copied to clipboard!)" -ForegroundColor Gray
}

# Launch browser IMMEDIATELY (Zero-Wait — instant live connection!)
Write-Host ""
Write-Host "Opening live GitHub Pages dashboard IMMEDIATELY in browser..." -ForegroundColor Cyan
Start-Process $ghUrl

# Auto-sync tunnel URL to GitHub in the background (Non-blocking!)
if ($tunnelHost) {
    $liveJsonPath = Join-Path $rootDir "tunnel_live.json"
    $needsUpdate = $true
    if (Test-Path $liveJsonPath) {
        try {
            $existing = Get-Content $liveJsonPath -Raw | ConvertFrom-Json
            if ($existing.url -eq $tunnelHost) {
                $needsUpdate = $false
            }
        } catch {}
    }

    if ($needsUpdate) {
        Write-Host "Syncing tunnel metadata with GitHub in background..." -ForegroundColor Gray
        $jsonObj = [PSCustomObject]@{
            url = $tunnelHost
            updated_at = (Get-Date -Format "o")
            status = "online"
        }
        $jsonObj | ConvertTo-Json | Set-Content -Path $liveJsonPath -Force
        Start-Process -FilePath "powershell.exe" -ArgumentList "-NoProfile", "-Command", "cd /d `"$rootDir`"; git add tunnel_live.json; git commit -m 'Auto-update tunnel_live.json: $tunnelHost'; git push origin main" -WindowStyle Hidden
    }
}

Write-Host ""
Write-Host "Press any key to exit this launcher window (services keep running)..." -ForegroundColor Gray
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
