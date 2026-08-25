@echo off
chcp 65001 >nul
echo 启动前端开发服务器...
cd /d "%~dp0frontend"
call pnpm install
pnpm dev
pause
