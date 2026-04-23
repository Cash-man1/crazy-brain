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
python -c "import sys; raise SystemExit(0 if sys.version_info >= (3,10) else 1)" >nul 2>nul
if errorlevel 1 (
  echo ERRORE: versione Python non supportata. Serve Python 3.10 o superiore.
  python --version
  pause
  exit /b 1
)

where node >nul 2>nul
if errorlevel 1 (
  echo ERRORE: Node.js non trovato nel PATH. Serve per il frontend ^(npm^).
  pause
  exit /b 1
)
for /f "tokens=1 delims=." %%V in ('node -p "process.versions.node" 2^>nul') do set NODE_MAJOR=%%V
if not defined NODE_MAJOR (
  echo ERRORE: impossibile leggere la versione di Node.js.
  pause
  exit /b 1
)
if %NODE_MAJOR% LSS 18 (
  echo ERRORE: Node.js troppo vecchio. Installa Node.js LTS ^(18+^).
  node -v
  pause
  exit /b 1
)
where npm >nul 2>nul
if errorlevel 1 (
  echo ERRORE: npm non trovato nel PATH. Reinstalla Node.js LTS.
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
    echo npm ci fallito, provo fallback con npm install...
    call npm install
    if errorlevel 1 (
      popd
      echo npm install fallito. Controlla connessione e versione Node.js.
      pause
      exit /b 1
    )
  )
) else (
  echo node_modules gia presente, salto npm ci.
)
if not exist "node_modules\.bin\vite.cmd" (
  echo vite non trovato in node_modules. Provo npm install per ripristinare pacchetti...
  call npm install
  if errorlevel 1 (
    popd
    echo Ripristino frontend fallito. Apri frontend e lancia: npm install
    pause
    exit /b 1
  )
)
if not exist "node_modules\.bin\vite.cmd" (
  popd
  echo ERRORE: vite resta non disponibile dopo installazione frontend.
  echo Verifica Node.js LTS e riprova setup.bat.
  pause
  exit /b 1
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
