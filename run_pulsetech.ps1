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
$tunnelHost = ""
for ($i = 0; $i -lt 5; $i++) {
    try {
        $metrics = (Invoke-WebRequest -Uri "http://127.0.0.1:20241/metrics" -UseBasicParsing -TimeoutSec 3).Content
        if ($metrics -match 'userHostname="https://([^"]+)"') {
            $tunnelUrl = "https://" + $matches[1]
            $tunnelHost = $matches[1]
            break
        }
    } catch {}
    Start-Sleep -Seconds 1
}

# Auto-sync tunnel URL to GitHub Pages if changed
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
        Write-Host "Syncing new tunnel with GitHub Pages repository..." -ForegroundColor Yellow
        $jsonObj = [PSCustomObject]@{
            url = $tunnelHost
            updated_at = (Get-Date -Format "o")
            status = "online"
        }
        $jsonObj | ConvertTo-Json | Set-Content -Path $liveJsonPath -Force
        Start-Process -FilePath "git" -ArgumentList "add", "tunnel_live.json" -WorkingDirectory $rootDir -Wait -WindowStyle Hidden
        Start-Process -FilePath "git" -ArgumentList "commit", "-m", "Auto-update tunnel_live.json: $tunnelHost" -WorkingDirectory $rootDir -Wait -WindowStyle Hidden
        Start-Process -FilePath "git" -ArgumentList "push", "origin", "main" -WorkingDirectory $rootDir -Wait -WindowStyle Hidden
        Write-Host "GitHub Pages metadata synced!" -ForegroundColor Green
    }
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
Write-Host ""
Write-Host "Opening live GitHub Pages dashboard in your browser..." -ForegroundColor Cyan
Start-Process $ghUrl
Write-Host ""
Write-Host "Press any key to exit this launcher window (services keep running)..." -ForegroundColor Gray
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
