@echo off
setlocal EnableExtensions
cd /d "%~dp0"
set "ROOT=%~dp0"

echo.
echo ============================================
echo   Chiusura Crazy Brain / Crazy Time locale
echo ============================================
echo Root: %ROOT%
echo.

REM 1) Chiudi processi legati al progetto (python/node/powershell con command line del progetto)
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$root = [Regex]::Escape((Resolve-Path '.').Path); " ^
  "$k = @(); " ^
  "$procs = Get-CimInstance Win32_Process | Where-Object { " ^
  "  $cl = ($_.CommandLine + ''); " ^
  "  $nm = ($_.Name + '').ToLower(); " ^
  "  ($cl -match $root) -or " ^
  "  ($cl -match 'uvicorn\s+main:app') -or " ^
  "  ($cl -match 'tools\\avvio-serve-nascosto\.ps1') -or " ^
  "  (($nm -eq 'python.exe' -or $nm -eq 'node.exe' -or $nm -eq 'powershell.exe') -and $cl -match 'crazy-brain') " ^
  "}; " ^
  "foreach ($p in $procs) { " ^
  "  try { Stop-Process -Id $p.ProcessId -Force -ErrorAction Stop; $k += ('PID ' + $p.ProcessId + ' [' + $p.Name + ']'); } catch {} " ^
  "}; " ^
  "if ($k.Count -eq 0) { Write-Host 'Nessun processo progetto trovato.' } else { Write-Host 'Terminati processi:'; $k | ForEach-Object { Write-Host (' - ' + $_) } }"

REM 2) Chiudi eventuali processi rimasti sulle porte locali del progetto
for %%P in (8000 5173) do (
  for /f "tokens=5" %%I in ('netstat -ano ^| findstr /R /C:":%%P .*LISTENING"') do (
    echo Provo a chiudere PID %%I su porta %%P...
    taskkill /PID %%I /F >nul 2>&1
  )
)

echo.
echo Chiusura completata.
echo Se qualcosa resta aperto, riesegui questo file come Amministratore.
echo.
pause

