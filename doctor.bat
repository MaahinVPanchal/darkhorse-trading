@echo off
title Blackhorse - Doctor (pre-flight checks)
cd /d "%~dp0"
"C:\Users\HP\AppData\Local\Programs\Python\Python312\python.exe" run.py doctor
echo.
pause
