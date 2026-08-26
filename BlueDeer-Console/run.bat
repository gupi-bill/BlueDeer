@echo off
REM BlueDeer Console 独立前端 — 双击启动（本地静态服务 + 自动开浏览器）
cd /d "%~dp0"
echo [BlueDeer Console] 启动本地服务 http://127.0.0.1:8081/ ...
start "" http://127.0.0.1:8081/
python -m http.server 8081
pause
