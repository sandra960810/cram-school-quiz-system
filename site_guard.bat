@echo off
chcp 65001 >nul
cd /d "%~dp0"
title 網站守護程式
rem 網站守護程式：每 2 分鐘檢查一次「網站（5000 埠）」和「官網通道 site-tunnel.exe」，
rem 掛掉就自動重新啟動，並把自己加進開機自動執行。紀錄寫在 site_guard_log.txt。
rem 只要雙擊一次就好；之後開機會自動跑。不會動 run.bat、share.bat、site_tunnel.bat。
echo 網站守護程式啟動中（這個視窗請最小化、不要關；紀錄在 site_guard_log.txt）...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\site_guard.ps1"
echo 守護程式已結束（可能已經有另一份在跑）。
pause
