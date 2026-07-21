# CareerPilot one-command start: API + web, health-checked, browser opened.
# Usage:  .\start.ps1   (or double-click start.cmd)
$ErrorActionPreference = "Stop"
$root = $PSScriptRoot

function Test-Port($port) {
    return [bool](Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue)
}

function Wait-Url($url, $label, $tries = 45) {
    for ($i = 0; $i -lt $tries; $i++) {
        try {
            Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 4 | Out-Null
            Write-Host "  $label is up." -ForegroundColor Green
            return $true
        } catch { Start-Sleep -Seconds 2 }
    }
    Write-Host "  $label did NOT come up - check the '$label' window for errors." -ForegroundColor Red
    return $false
}

Write-Host "CareerPilot - starting everything from $root" -ForegroundColor Cyan

# ---- first-run self-setup ----
if (-not (Test-Path "$root\.venv\Scripts\python.exe")) {
    Write-Host "First run: creating Python venv + installing dependencies (a few minutes)..."
    python -m venv "$root\.venv"
    & "$root\.venv\Scripts\pip.exe" install -r "$root\requirements.txt"
}
if (-not (Test-Path "$root\apps\web\node_modules")) {
    Write-Host "First run: installing web dependencies (a few minutes)..."
    Push-Location "$root\apps\web"; npm install; Pop-Location
}

# ---- API (port 8000) ----
if (Test-Port 8000) {
    Write-Host "  API already running on 8000 - leaving it." -ForegroundColor Yellow
} else {
    Start-Process -FilePath "$root\.venv\Scripts\python.exe" `
        -ArgumentList "-m", "uvicorn", "main:app", "--app-dir", "apps/api", "--port", "8000" `
        -WorkingDirectory $root -WindowStyle Minimized
    Write-Host "  API starting (minimized window: python)..."
}

# ---- Web (port 3000) ----
if (Test-Port 3000) {
    Write-Host "  Web already running on 3000 - leaving it." -ForegroundColor Yellow
} else {
    Start-Process -FilePath "cmd.exe" -ArgumentList "/c", "npm run dev" `
        -WorkingDirectory "$root\apps\web" -WindowStyle Minimized
    Write-Host "  Web starting (minimized window: npm)..."
}

$apiOk = Wait-Url "http://127.0.0.1:8000/health" "API"
$webOk = Wait-Url "http://localhost:3000/login" "Web"

if ($apiOk -and $webOk) {
    Write-Host ""
    Write-Host "CareerPilot is ready: http://localhost:3000" -ForegroundColor Cyan
    Write-Host "Login: dhirenrao@gmail.com  (your password; TestPassword unless you changed it)"
    Write-Host "Stop everything later with stop.cmd"
    Start-Process "http://localhost:3000"
} else {
    Write-Host "Something did not start - the minimized server windows have the error details." -ForegroundColor Red
    exit 1
}
