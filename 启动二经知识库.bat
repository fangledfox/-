@echo off
chcp 65001 >nul
cd /d %~dp0
echo ========================================
echo   二经知识库 启动中...
echo ========================================
python tools\build_portal.py
python tools\server.py
pause
