@echo off
chcp 65001 >nul
cd /d "%~dp0"
title 安裝 AI 真人語音
echo 正在安裝 AI 真人語音（約 160 MB，第一次需要幾分鐘）...
powershell -NoProfile -ExecutionPolicy Bypass -File tools\setup_voice.ps1
echo.
pause
