@echo off
title TelePro - Telegram Broadcasting Platform
echo ========================================================
echo  Starting TelePro - Telegram Broadcasting Platform
echo ========================================================

set "BASE_DIR=%~dp0"
set "PYTHON_EXE=C:\Users\OFFICE\AppData\Local\Programs\Python\Python312\python.exe"

if not exist "%PYTHON_EXE%" (
    set "PYTHON_EXE=python"
)

echo [1/2] Launching Backend API on http://127.0.0.1:8000...
cd /d "%BASE_DIR%backend"
start "TelePro Backend API" cmd /k "%PYTHON_EXE% -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload"

timeout /t 2 /nobreak >nul

echo [2/2] Launching Frontend Dashboard on http://localhost:3000...
cd /d "%BASE_DIR%frontend"
start "TelePro Frontend Dashboard" cmd /k "npm.cmd run dev"

timeout /t 4 /nobreak >nul

echo Opening browser at http://localhost:3000...
start http://localhost:3000

echo ========================================================
echo  TelePro is running! 
echo  - Frontend: http://localhost:3000
echo  - API Docs: http://127.0.0.1:8000/docs
echo ========================================================
