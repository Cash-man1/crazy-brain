@echo off
setlocal
title Crazy Brain - Setup

set "ROOT=%~dp0"
set "VENV=%ROOT%.venv"

echo ==========================================
echo   CRAZY BRAIN SETUP
echo ==========================================
echo.

where python >nul 2>&1
if errorlevel 1 (
  echo [ERRORE] Python non trovato nel PATH.
  echo Installa Python 3.10+ e riprova.
  pause
  exit /b 1
)

where node >nul 2>&1
if errorlevel 1 (
  echo [ERRORE] Node.js non trovato nel PATH.
  echo Installa Node.js LTS e riprova.
  pause
  exit /b 1
)

if not exist "%VENV%\Scripts\python.exe" (
  echo [INFO] Creo virtualenv...
  python -m venv "%VENV%"
  if errorlevel 1 (
    echo [ERRORE] Impossibile creare virtualenv.
    pause
    exit /b 1
  )
)

echo [INFO] Aggiorno pip...
call "%VENV%\Scripts\activate.bat"
python -m pip install --upgrade pip
if errorlevel 1 (
  echo [ERRORE] Aggiornamento pip fallito.
  pause
  exit /b 1
)

echo [INFO] Installo dipendenze backend...
pip install -r "%ROOT%backend\requirements.txt"
if errorlevel 1 (
  echo [ERRORE] Installazione dipendenze backend fallita.
  pause
  exit /b 1
)

echo [INFO] Installo browser per scraping (Chromium)...
python -m playwright install chromium
if errorlevel 1 (
  echo [ERRORE] Installazione Chromium Playwright fallita.
  pause
  exit /b 1
)

echo [INFO] Installo dipendenze frontend...
pushd "%ROOT%frontend"
call npm install
if errorlevel 1 (
  popd
  echo [ERRORE] Installazione dipendenze frontend fallita.
  pause
  exit /b 1
)
popd

if not exist "%ROOT%backend\.env" if exist "%ROOT%backend\.env.example" (
  echo [INFO] Creo backend\.env da example...
  copy /Y "%ROOT%backend\.env.example" "%ROOT%backend\.env" >nul
)

if not exist "%ROOT%frontend\.env" if exist "%ROOT%frontend\.env.example" (
  echo [INFO] Creo frontend\.env da example...
  copy /Y "%ROOT%frontend\.env.example" "%ROOT%frontend\.env" >nul
)

echo.
echo [OK] Setup completato.
echo Ora avvia con: avvio.bat
echo.
pause
exit /b 0
