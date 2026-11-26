@echo off
chcp 65001 >nul
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"
title 設定官網諮詢通知信

set PY=python
where python >nul 2>nul || set PY=py
if exist venv\Scripts\python.exe set PY=venv\Scripts\python.exe

echo ============================================
echo   設定官網諮詢通知信的寄件帳號
echo ============================================
echo.
echo 官網有人填「免費諮詢」或迷你模考表單時，會自動寄信通知。
echo 需要一個用來「寄信」的 Gmail／Google 信箱，以及它的「應用程式密碼」。
echo 帳號密碼只存在這台電腦（instance\mail.json），不會上傳到 GitHub。
echo.
%PY% tools\set_mail.py
echo.
pause
