@echo off
title Darkhorse - Telegram notify test
cd /d "%~dp0"
"C:\Users\HP\AppData\Local\Programs\Python\Python312\python.exe" run.py notify-test
echo.
pause
