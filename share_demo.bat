@echo off
chcp 65001 >nul
cd /d "%~dp0"
title 給主管看的展示版連結

rem 展示版：假學生、範例批改，不碰學生資料（quiz.db）也不用 AI 金鑰
rem 跑在 5001 埠，和平常的網站（5000 埠）互不影響

set PY=python
where python >nul 2>nul || set PY=py
if exist venv\Scripts\python.exe set PY=venv\Scripts\python.exe

echo [1/4] 檢查 cloudflared...
if not exist cloudflared.exe (
    echo     下載 cloudflared.exe（Cloudflare 官方，約 65 MB）...
    powershell -NoProfile -Command "$ProgressPreference='SilentlyContinue'; Invoke-WebRequest -Uri 'https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe' -OutFile 'cloudflared.exe'"
    if not exist cloudflared.exe ( echo     下載失敗，請檢查網路 & pause & exit /b 1 )
)

echo [2/4] 準備展示版資料（只有單字和假學生）...
set DEMO_MODE=1
set PORT=5001
set PYTHONUTF8=1
%PY% import_sheet.py > share_demo_log.txt 2>&1
if errorlevel 1 ( echo     匯入單字失敗，請看 share_demo_log.txt & pause & exit /b 1 )

echo [3/4] 啟動展示版網站...
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":5001 " ^| findstr LISTENING') do taskkill /F /PID %%p >nul 2>nul
start "展示版網站（關掉這個視窗展示版就會停止）" cmd /k "set DEMO_MODE=1&& set PORT=5001&& set PYTHONUTF8=1&& %PY% app.py"
timeout /t 5 /nobreak >nul

echo [4/4] 建立公開連結...
if exist share_demo_link.txt del share_demo_link.txt
if exist share_demo_tunnel.txt del share_demo_tunnel.txt
start "展示版通道（關掉這個視窗，連結就會失效）" /min cmd /c "cloudflared.exe tunnel --url http://127.0.0.1:5001 --no-autoupdate > share_demo_tunnel.txt 2>&1"

powershell -NoProfile -Command ^
  "$url=$null; for($i=0; $i -lt 60 -and -not $url; $i++){ Start-Sleep 1; if(Test-Path share_demo_tunnel.txt){ $m=Select-String -Path share_demo_tunnel.txt -Pattern 'https://[a-z0-9-]+\.trycloudflare\.com' | Select-Object -First 1; if($m){ $url=$m.Matches[0].Value } } };" ^
  "if($url){ $link=$url+'/dashboard/1'; Set-Content -Path share_demo_link.txt -Value $link -Encoding UTF8; Set-Clipboard -Value $link; Write-Host ''; Write-Host '給主管的展示版連結（已複製到剪貼簿）：' -ForegroundColor Green; Write-Host $link -ForegroundColor Yellow; Write-Host ''; Write-Host '展示版只有假資料，不會露出學生資料。電腦要開著、兩個視窗都不能關，連結才有效。每次重新執行網址都會不一樣。' } else { Write-Host '沒有拿到連結，請看 share_demo_tunnel.txt' -ForegroundColor Red }"
echo.
pause
