@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo ============================================
echo  Crazy Brain - setup desktop (Windows)
echo ============================================
echo.

where python >nul 2>nul
if errorlevel 1 (
  echo ERRORE: Python non trovato nel PATH. Installa Python 3.10+ e riprova.
  pause
  exit /b 1
)

where node >nul 2>nul
if errorlevel 1 (
  echo ERRORE: Node.js non trovato nel PATH. Serve per il frontend ^(npm^).
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo Creazione ambiente virtuale .venv nella cartella progetto...
  python -m venv .venv
  if errorlevel 1 (
    echo Creazione venv fallita.
    pause
    exit /b 1
  )
)

call ".venv\Scripts\activate.bat"
python -m pip install --upgrade pip
if errorlevel 1 goto :err

echo Installazione dipendenze backend...
pip install -r "backend\requirements.txt"
if errorlevel 1 goto :err

echo Installazione Chromium per Playwright ^(lettura pagina casino.org in fallback^)...
pushd backend
playwright install chromium
if errorlevel 1 (
  popd
  echo ATTENZIONE: playwright install fallito. Lo scrape HTML potrebbe non funzionare.
) else (
  popd
)

echo Installazione dipendenze frontend...
pushd frontend
if not exist "node_modules\" (
  call npm ci
  if errorlevel 1 (
    popd
    echo npm ci fallito. Prova: npm install
    pause
    exit /b 1
  )
) else (
  echo node_modules gia presente, salto npm ci.
)
popd

if not exist "backend\.env" (
  echo Creo backend\.env da .env.example ^(modifica SECRET_KEY ecc.^)
  copy /Y "backend\.env.example" "backend\.env" >nul
)

if not exist "frontend\.env" (
  echo Creo frontend\.env per API locale...
  > "frontend\.env" echo VITE_API_URL=http://127.0.0.1:8000
)

echo.
echo ============================================
echo  Setup completato.
echo  Avvia con: avvio.bat
echo ============================================
pause
exit /b 0

:err
echo.
echo ERRORE durante installazione.
pause
exit /b 1
