@echo off
setlocal EnableExtensions
cd /d "%~dp0"
set "ROOT=%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo Esegui prima setup.bat dalla stessa cartella del progetto.
  pause
  exit /b 1
)
if not exist "frontend\node_modules\.bin\vite.cmd" (
  echo Frontend non pronto: vite mancante in frontend\node_modules\.bin
  echo Esegui setup.bat e attendi "Setup completato".
  pause
  exit /b 1
)
for %%P in (8000 5173) do (
  netstat -ano | findstr /R /C:":%%P .*LISTENING" >nul
  if not errorlevel 1 (
    echo Porta %%P gia in uso. Chiudi prima processi precedenti con chiudi.bat
    pause
    exit /b 1
  )
)

:: --- Desktop locale: API + dashboard (dati live come in produzione, senza Render) ---
set BACKEND_PORT=8000
set FRONTEND_PORT=5173
set ENVIRONMENT=development
set FRONTEND_URL=http://localhost:%FRONTEND_PORT%
set CORS_EXTRA_ORIGINS=http://localhost:%FRONTEND_PORT%,http://127.0.0.1:%FRONTEND_PORT%
set PUBLIC_INGESTION_ENABLED=1
set LIVE_ROWS_FROM_REDIS=0
set REDIS_URL=
set "DASHBOARD_URL=http://localhost:%FRONTEND_PORT%/dashboard"
set "SOURCE_READ_URL=https://www.casino.org/casinoscores/it/crazy-time/"

:: 1 = API JSON Evolution (stessi ultimi esiti/orari, leggero). 0 = solo Playwright sulla pagina HTML casino.org
set SCRAPER_USE_EVOLUTION_API=0
:: Se Evolution fallisce, usa Playwright ^(richiede chromium da setup.bat^)
set SCRAPER_PLAYWRIGHT_FALLBACK=1
:: Ore cronologia Playwright:
:: - bootstrap iniziale (prima lettura a caldo): 72h per dare base al cervello
:: - live normale dopo bootstrap: 72h (il cervello resta incrementale: aggiunge solo i nuovi esiti)
set SCRAPER_CRONOLOGIA_HOURS_BOOTSTRAP=72
set SCRAPER_CRONOLOGIA_HOURS_LIVE=72
set SCRAPER_CRONOLOGIA_HOURS=72
set PUBLIC_BOOTSTRAP_WORKER_LIMIT=5000
set PUBLIC_LIVE_WORKER_LIMIT=5000
:: Storico persistito su disco (max righe in public_history.json)
set PUBLIC_HISTORY_MAX_ITEMS=5000

> "frontend\.env" echo VITE_API_URL=http://127.0.0.1:%BACKEND_PORT%

echo Avvio backend su http://127.0.0.1:%BACKEND_PORT% ...
start "Crazy Brain API" cmd /k cd /d "%ROOT%" ^& call "%ROOT%.venv\Scripts\activate.bat" ^& cd /d "%ROOT%backend" ^& uvicorn main:app --reload --host 127.0.0.1 --port %BACKEND_PORT%

timeout /t 4 /nobreak >nul

echo Avvio frontend Vite...
start "Crazy Brain Web" cmd /k cd /d "%ROOT%frontend" ^& npm run dev -- --host 127.0.0.1 --port %FRONTEND_PORT% --strictPort

timeout /t 5 /nobreak >nul
echo Apro automaticamente dashboard e pagina sorgente...
start "" "%DASHBOARD_URL%"
start "" "%SOURCE_READ_URL%"

echo.
echo Backend:  http://127.0.0.1:%BACKEND_PORT%   (health: /health)
echo Frontend: %DASHBOARD_URL%
echo Sorgente lettura: %SOURCE_READ_URL%
echo Dashboard pubblica: /brain/... come da menu dell'app
echo.
echo Per forzare SOLO lettura pagina HTML ^(Playwright^): in questo file imposta SCRAPER_USE_EVOLUTION_API=0
echo.
pause
