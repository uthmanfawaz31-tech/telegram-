# TelePro Launcher Script
Write-Host "========================================================" -ForegroundColor Cyan
Write-Host " Starting TelePro - Telegram Broadcasting Platform" -ForegroundColor Green
Write-Host "========================================================" -ForegroundColor Cyan

$baseDir = Split-Path -Parent $MyInvocation.MyCommand.Path

$pythonExe = "C:\Users\OFFICE\AppData\Local\Programs\Python\Python312\python.exe"
if (-not (Test-Path $pythonExe)) {
    $pythonExe = "python"
}

# 1. Start Backend
Write-Host "[1/2] Launching Backend on http://127.0.0.1:8000..." -ForegroundColor Yellow
Start-Process -FilePath "cmd.exe" -ArgumentList "/k cd /d `"$baseDir\backend`" && `"$pythonExe`" -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload"

Start-Sleep -Seconds 2

# 2. Start Frontend
Write-Host "[2/2] Launching Frontend on http://localhost:3000..." -ForegroundColor Yellow
Start-Process -FilePath "cmd.exe" -ArgumentList "/k cd /d `"$baseDir\frontend`" && npm.cmd run dev"

Start-Sleep -Seconds 3

# Open browser
Start-Process "http://localhost:3000"

Write-Host "TelePro is running!" -ForegroundColor Green
Write-Host "Frontend: http://localhost:3000" -ForegroundColor Cyan
Write-Host "API Docs: http://127.0.0.1:8000/docs" -ForegroundColor Cyan
