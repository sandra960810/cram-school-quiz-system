@echo off
chcp 65001 >nul
cd /d "%~dp0"
title 分享網站連結

set PY=python
where python >nul 2>nul || set PY=py
if exist venv\Scripts\python.exe set PY=venv\Scripts\python.exe

echo [1/3] 檢查 cloudflared...
if not exist cloudflared.exe (
    echo     下載 cloudflared.exe（Cloudflare 官方，約 65 MB）...
    powershell -NoProfile -Command "$ProgressPreference='SilentlyContinue'; Invoke-WebRequest -Uri 'https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe' -OutFile 'cloudflared.exe'"
    if not exist cloudflared.exe ( echo     下載失敗，請檢查網路 & pause & exit /b 1 )
)

echo [2/3] 確認網站有在跑...
netstat -ano | findstr ":5000 " | findstr LISTENING >nul
if errorlevel 1 (
    echo     網站沒有在跑，幫你啟動...
    start "補習班網站（關掉這個視窗網站就會停止）" cmd /k "set PYTHONUTF8=1 && %PY% app.py"
    timeout /t 4 /nobreak >nul
)

echo [3/3] 建立公開連結...
taskkill /F /IM cloudflared.exe >nul 2>nul
if exist share_log.txt del share_log.txt
if exist share_link.txt del share_link.txt
start "Cloudflare 通道（關掉這個視窗，連結就會失效）" /min cmd /c "cloudflared.exe tunnel --url http://127.0.0.1:5000 --no-autoupdate > share_log.txt 2>&1"

powershell -NoProfile -Command ^
  "$url=$null; for($i=0; $i -lt 60 -and -not $url; $i++){ Start-Sleep 1; if(Test-Path share_log.txt){ $m=Select-String -Path share_log.txt -Pattern 'https://[a-z0-9-]+\.trycloudflare\.com' | Select-Object -First 1; if($m){ $url=$m.Matches[0].Value } } };" ^
  "if($url){ $link=$url+'/dashboard/1'; Set-Content -Path share_link.txt -Value $link -Encoding UTF8; Set-Clipboard -Value $link; Write-Host ''; Write-Host '給主管的連結（已複製到剪貼簿）：' -ForegroundColor Green; Write-Host $link -ForegroundColor Yellow; Write-Host ''; Write-Host '注意：電腦要開著、網站和 Cloudflare 通道視窗都不能關，連結才有效。每次重新執行網址都會不一樣。' } else { Write-Host '沒有拿到連結，請看 share_log.txt' -ForegroundColor Red }"
echo.
pause
