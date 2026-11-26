@echo off
chcp 65001 >nul
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"
title 設定 AI 老師的備用付費金鑰

set PY=python
where python >nul 2>nul || set PY=py
if exist venv\Scripts\python.exe set PY=venv\Scripts\python.exe

echo ============================================
echo   設定 AI 老師的備用付費金鑰
echo ============================================
echo.
echo 平常用 set_ai_key.bat 設定的免費 Gemini 金鑰；
echo 免費額度用完時，網站會自動改用這把付費金鑰，學生不會看到「額度用完」。
echo.
echo 可以用：
echo   Anthropic Claude 金鑰（sk-ant- 開頭，用中階的 Claude Sonnet 5.5）
echo   或 Google Gemini 付費金鑰（另一個有開帳單的 Google 專案，AIza 或 AQ. 開頭）
echo 金鑰只存在這台電腦的 ai_key_paid.txt，不會上傳到 GitHub。
echo 每次改用付費金鑰都會記在 instance\ai_paid_log.txt，方便對帳。
echo.
echo 想停用付費備援：直接按 Enter（不輸入）就會刪掉備用金鑰。
echo （在這個黑色視窗按滑鼠右鍵就是貼上）
echo.
set "AIKEY="
set /p "AIKEY=備用付費金鑰："
if "%AIKEY%"=="" (
    if exist ai_key_paid.txt del ai_key_paid.txt
    echo 已停用付費備援：免費額度用完時會請學生稍後再試。
    pause
    exit /b 0
)
>ai_key_paid.txt echo %AIKEY%
set "AIKEY="
echo.
echo 已存檔，正在測試金鑰能不能用...（紀錄寫在 ai_key_log.txt）
%PY% -m pip install --disable-pip-version-check -q anthropic google-genai > ai_key_log.txt 2>&1
%PY% tools\check_ai_key.py --paid >> ai_key_log.txt 2>&1
type ai_key_log.txt
echo.
echo 如果上面顯示「AI 老師已就緒」，就設定好了，不用重開網站。
pause
