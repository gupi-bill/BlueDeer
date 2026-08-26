@echo off
chcp 65001 >nul
cd /d "%~dp0"
set PY=C:\Users\a\AppData\Local\hermes\hermes-agent\venv\Scripts\python.exe
if not exist "%PY%" set PY=python
"%PY%" -m bluedeer
echo.
pause

