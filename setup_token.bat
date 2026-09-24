@echo off
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" setup_token.py
) else (
    python setup_token.py
)
echo.
pause
