@echo off
chcp 65001 >nul
cd /d "%~dp0"
title 官網固定通道 www.trinity413.com

rem 官網的固定網址通道（Cloudflare 具名通道 trinity-site）。
rem 用另一個檔名 site-tunnel.exe 執行，share.bat 關掉 cloudflared.exe 時才不會連官網一起關掉。
rem 開機會自動執行（啟動資料夾裡有捷徑）；也可以手動雙擊。結果寫在 site_tunnel_log.txt。

set PY=python
where python >nul 2>nul || set PY=py
if exist venv\Scripts\python.exe set PY=venv\Scripts\python.exe

echo [1/3] 檢查通道程式...
if not exist site-tunnel.exe (
    if exist cloudflared.exe (
        copy /y cloudflared.exe site-tunnel.exe >nul
    ) else (
        powershell -NoProfile -Command "$ProgressPreference='SilentlyContinue'; Invoke-WebRequest -Uri 'https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe' -OutFile 'site-tunnel.exe'"
    )
)
if not exist site-tunnel.exe ( echo     找不到通道程式，請檢查網路 & echo %date% %time% 找不到 site-tunnel.exe>> site_tunnel_log.txt & pause & exit /b 1 )

echo [2/3] 確認網站有在跑...
netstat -ano | findstr ":5000 " | findstr LISTENING >nul
if errorlevel 1 (
    echo     網站沒有在跑，幫你啟動...
    start "補習班網站（關掉這個視窗網站就會停止）" /min cmd /k "set PYTHONUTF8=1 && %PY% app.py"
    timeout /t 6 /nobreak >nul
)

echo [3/3] 連上官網通道...
tasklist /FI "IMAGENAME eq site-tunnel.exe" | findstr /I site-tunnel.exe >nul
if not errorlevel 1 (
    echo     官網通道已經在跑，不用再開。
    timeout /t 3 /nobreak >nul
    exit /b 0
)
echo %date% %time% 啟動官網通道>> site_tunnel_log.txt
start "官網通道 www.trinity413.com（關掉這個視窗，官網就打不開）" /min cmd /c "site-tunnel.exe tunnel --no-autoupdate run trinity-site >> site_tunnel_log.txt 2>&1"
echo.
echo 官網 https://www.trinity413.com 已連線。這個視窗可以關掉，最小化的「官網通道」視窗不要關。
timeout /t 5 /nobreak >nul
