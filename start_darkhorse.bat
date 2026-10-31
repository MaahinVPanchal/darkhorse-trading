@echo off
title Darkhorse - ONE-CLICK START (paper + dashboard)
cd /d "%~dp0"
echo Starting the full desk: paper trading (watchdog) + dashboard...
echo.
start "Darkhorse DASHBOARD - keep open" cmd /k ""C:\Users\HP\AppData\Local\Programs\Python\Python312\python.exe" run.py dashboard"
timeout /t 2 /nobreak >nul
start "Darkhorse PAPER WATCHDOG - keep open" cmd /k watchdog.bat
timeout /t 3 /nobreak >nul
echo.
echo   Both windows are running:
echo     - Dashboard:  http://127.0.0.1:8765  (opens automatically in your browser)
echo     - Paper bot:  trading every 60s, auto-restarts if it crashes
echo   Close those two windows to stop, or just close them at end of day.
start http://127.0.0.1:8765
pause
