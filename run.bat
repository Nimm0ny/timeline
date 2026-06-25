@echo off
chcp 65001 >nul 2>&1
title TimeLine Project

echo.
echo   ====================================
echo     TimeLine Project
echo   ====================================
echo.

cd /d "%~dp0"

echo   [1/4] 安装 Python 依赖...
pip install -r backend\requirements.txt -q 2>nul

echo   [2/4] 安装前端依赖...
npm install

echo   [3/4] 构建 Vue 前端...
npm run build

echo   [4/4] 启动服务器...
echo.
echo   时间轴页面:  http://localhost:8000
echo   数据编辑器:  http://localhost:8000/editor
echo.

start "" cmd /c "timeout /t 2 /nobreak >nul && start http://localhost:8000"

python backend\server.py
