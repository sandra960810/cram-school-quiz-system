@echo off
chcp 65001 >nul
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"
title 補習班測驗系統

set PY=python
where python >nul 2>nul || set PY=py
if exist venv\Scripts\python.exe set PY=venv\Scripts\python.exe

echo 準備中，請稍候（紀錄寫在 run_log.txt）...
call :setup > run_log.txt 2>&1
set RC=%errorlevel%
type run_log.txt
if not "%RC%"=="0" ( echo. & echo 準備步驟失敗，請看上面的訊息 & pause & exit /b 1 )

echo.
rem 如果舊的網站還開著（佔用 5000 埠的 python），先把它關掉
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":5000 " ^| findstr LISTENING') do (
    taskkill /F /PID %%p /FI "IMAGENAME eq python.exe" >nul 2>nul && echo 已關閉舊的網站（PID %%p）
)
echo [5/5] 啟動網站：http://127.0.0.1:5000/dashboard/1
echo     （要關閉網站，直接關掉這個視窗）
start "" powershell -NoProfile -WindowStyle Hidden -Command "Start-Sleep 3; Start-Process 'http://127.0.0.1:5000/dashboard/1'"
%PY% app.py
pause
exit /b 0

:setup
echo 使用的 Python：%PY%
%PY% --version
echo [1/5] 備份資料庫...
if not exist backups mkdir backups
for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd_HHmmss"') do set TS=%%i
copy /y instance\quiz.db backups\quiz_%TS%.db >nul && echo     已備份到 backups\quiz_%TS%.db

for /f %%b in ('git rev-parse --abbrev-ref HEAD') do set BR=%%b
echo [2/5] 從 GitHub 取得最新程式 (%BR%)...
git pull --ff-only origin %BR%

echo [3/5] 安裝套件 (flask, flask_sqlalchemy, openpyxl)...
%PY% -m pip install --disable-pip-version-check flask flask_sqlalchemy openpyxl
if errorlevel 1 ( echo     套件安裝失敗 & exit /b 1 )

echo [4/5] 匯入單字總表 vocab_master.xlsx...
%PY% import_sheet.py
if errorlevel 1 ( echo     匯入失敗，資料庫備份在 backups 資料夾 & exit /b 1 )
exit /b 0
