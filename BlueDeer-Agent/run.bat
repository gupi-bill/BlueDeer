@echo off
chcp 65001 >nul
cd /d "%~dp0"
set "PY=%BLUEDEER_PYTHON%"
if not defined BLUEDEER_PYTHON set "PY=python"
"%PY%" -m bluedeer
echo.
pause

