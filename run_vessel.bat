@echo off
cd /d "%~dp0"
echo Starting Vessel...
echo Close this window to take the bot offline.
echo.
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" vessel.py
) else (
    python vessel.py
)
echo.
echo Vessel has stopped.
pause
