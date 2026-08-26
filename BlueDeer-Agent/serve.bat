@echo off
chcp 65001 >nul
cd /d "%~dp0"
set PY=C:\Users\a\AppData\Local\hermes\hermes-agent\venv\Scripts\python.exe
if not exist "%PY%" set PY=python
echo BlueDeer API server: http://127.0.0.1:8000
echo Console: open BlueDeer-Console/index.html in browser
"%PY%" -m bluedeer.server
echo.
echo Server exited.
pause

