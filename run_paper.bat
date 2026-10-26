@echo off
title Blackhorse - Paper Trading
cd /d "%~dp0"
echo Starting Blackhorse paper trading (no account, no money needed)...
echo Close this window or press Ctrl+C to stop.
echo.
"C:\Users\HP\AppData\Local\Programs\Python\Python312\python.exe" run.py paper
pause
