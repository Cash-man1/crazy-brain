@echo off
setlocal
title Crazy Brain - Avvio

set "ROOT=%~dp0"
set "VENV_PY=%ROOT%.venv\Scripts\python.exe"

echo ==========================================
echo   CRAZY BRAIN AVVIO
echo ==========================================
echo.

echo [INFO] Chiudo eventuali processi su porta 8001...
powershell -NoProfile -Command "Get-NetTCPConnection -LocalPort 8001 -State Listen -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }" >nul 2>&1

if not exist "%VENV_PY%" (
  echo [INFO] Ambiente non trovato. Eseguo setup...
  call "%ROOT%setup.bat"
  if errorlevel 1 (
    echo [ERRORE] Setup fallito. Avvio annullato.
    pause
    exit /b 1
  )
)

echo [INFO] Verifico browser Chromium per Playwright...
"%VENV_PY%" -m playwright install chromium >nul 2>&1

echo [INFO] Avvio backend su http://localhost:8001 ...
start "Crazy Brain Backend" cmd /k "cd /d ""%ROOT%backend"" && call ""%ROOT%.venv\Scripts\activate.bat"" && python -m uvicorn main:app --host 127.0.0.1 --port 8001 --reload"

echo [INFO] Attendo 2 secondi...
timeout /t 2 /nobreak >nul

echo [INFO] Avvio frontend su http://localhost:5173 ...
start "Crazy Brain Frontend" cmd /k "cd /d ""%ROOT%frontend"" && npm run dev -- --host 127.0.0.1 --port 5173"

echo [INFO] Attendo 4 secondi...
timeout /t 4 /nobreak >nul

start "" "http://localhost:5173"
start "" "https://www.casino.org/casinoscores/it/crazy-time/"

echo.
echo [OK] App avviata.
echo Backend:  http://localhost:8001
echo Frontend: http://localhost:5173
echo.
exit /b 0
