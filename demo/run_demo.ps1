# ORION local demo (Windows PowerShell). Needs Python 3.10+ and Node.js 20+.
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot

function Need($cmd, $url) {
  if (-not (Get-Command $cmd -ErrorAction SilentlyContinue)) {
    Write-Host "`n$cmd was not found. Install it from $url, then run this again." -ForegroundColor Yellow
    Read-Host "Press Enter to exit"; exit 1
  }
}
Need python "https://www.python.org/downloads/ (tick 'Add python.exe to PATH')"
Need npm "https://nodejs.org/ (LTS)"

Write-Host "`n[1/4] Installing Python packages..." -ForegroundColor Cyan
python -m pip install --quiet -r "$root\engine\requirements.txt"

Write-Host "[2/4] Generating synthetic demo data..." -ForegroundColor Cyan
python "$root\demo\generate_demo_data.py"

Write-Host "[3/4] Starting mock Supabase in a new window..." -ForegroundColor Cyan
Start-Process python -ArgumentList "`"$root\demo\mock_supabase.py`""

Write-Host "[4/4] Starting the website (first run installs packages, ~1 min)..." -ForegroundColor Cyan
Set-Location "$root\web"
if (-not (Test-Path "node_modules")) { npm install --no-audit --no-fund }
$env:NEXT_PUBLIC_SUPABASE_URL = "http://127.0.0.1:54321"
$env:NEXT_PUBLIC_SUPABASE_ANON_KEY = "demo"
$env:NEXT_PUBLIC_DEMO_MODE = "1"
$env:NEXT_TELEMETRY_DISABLED = "1"
Start-Job { Start-Sleep 12; Start-Process "http://localhost:3000" } | Out-Null
Write-Host "`nOpen http://localhost:3000  (admin: http://localhost:3000/login, any email/password)" -ForegroundColor Green
npm run dev
