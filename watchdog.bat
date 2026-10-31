@echo off
title Blackhorse WATCHDOG - paper mode auto-restart
cd /d "%~dp0"
echo Watchdog started: paper mode will auto-restart if it crashes or halts-exit.
echo Logs append to watchdog.log and paper.log. Close this window to stop.
:loop
echo [%date% %time%] paper session start >> watchdog.log
"C:\Users\HP\AppData\Local\Programs\Python\Python312\python.exe" run.py paper >> paper.log 2>&1
echo [%date% %time%] paper exited (code %errorlevel%), restarting in 60s >> watchdog.log
timeout /t 60 /nobreak >nul
goto loop
