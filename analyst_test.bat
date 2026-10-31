@echo off
title Darkhorse - Analyst test (Jev / Nebius key check)
cd /d "%~dp0"
"C:\Users\HP\AppData\Local\Programs\Python\Python312\python.exe" run.py analyst-test
echo.
pause
