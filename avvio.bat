@echo off
setlocal EnableExtensions
cd /d "%~dp0"
set "ROOT=%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo Esegui prima setup.bat dalla stessa cartella del progetto.
  pause
  exit /b 1
)
if not exist "frontend\node_modules\" (
  echo Manca frontend\node_modules. Esegui prima setup.bat
  pause
  exit /b 1
)

:: --- Desktop locale: API + dashboard (dati live come in produzione, senza Render) ---
set ENVIRONMENT=development
set FRONTEND_URL=http://localhost:5173
set CORS_EXTRA_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
set PUBLIC_INGESTION_ENABLED=1
set LIVE_ROWS_FROM_REDIS=0
set REDIS_URL=

:: 1 = API JSON Evolution (stessi ultimi esiti/orari, leggero). 0 = solo Playwright sulla pagina HTML casino.org
set SCRAPER_USE_EVOLUTION_API=1
:: Se Evolution fallisce, usa Playwright ^(richiede chromium da setup.bat^)
set SCRAPER_PLAYWRIGHT_FALLBACK=1

if not exist "frontend\.env" (
  > "frontend\.env" echo VITE_API_URL=http://127.0.0.1:8000
)

echo Avvio backend su http://127.0.0.1:8000 ...
start "Crazy Brain API" cmd /k cd /d "%ROOT%" ^& call "%ROOT%.venv\Scripts\activate.bat" ^& cd /d "%ROOT%backend" ^& uvicorn main:app --reload --host 127.0.0.1 --port 8000

timeout /t 4 /nobreak >nul

echo Avvio frontend Vite...
start "Crazy Brain Web" cmd /k cd /d "%ROOT%frontend" ^& npm run dev

echo.
echo Backend:  http://127.0.0.1:8000   (health: /health)
echo Frontend: apri la URL mostrata da Vite ^(di solito http://localhost:5173^)
echo Dashboard pubblica: /brain/... come da menu dell'app
echo.
echo Per forzare SOLO lettura pagina HTML ^(Playwright^): in questo file imposta SCRAPER_USE_EVOLUTION_API=0
echo.
pause
