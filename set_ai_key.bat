@echo off
chcp 65001 >nul
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"
title 設定 AI 老師金鑰

set PY=python
where python >nul 2>nul || set PY=py
if exist venv\Scripts\python.exe set PY=venv\Scripts\python.exe

echo ============================================
echo   設定寫作 AI 老師的 Anthropic API 金鑰
echo ============================================
echo.
echo 金鑰只會存在這台電腦的 ai_key.txt，不會上傳到 GitHub。
echo 請把金鑰（sk-ant- 開頭）貼上後按 Enter。
echo （在這個黑色視窗按滑鼠右鍵就是貼上）
echo.
set "AIKEY="
set /p "AIKEY=金鑰："
if "%AIKEY%"=="" ( echo 沒有輸入金鑰，已取消。 & pause & exit /b 1 )
>ai_key.txt echo %AIKEY%
set "AIKEY="
echo.
echo 已存檔，正在測試金鑰能不能用...（紀錄寫在 ai_key_log.txt）
%PY% -m pip install --disable-pip-version-check -q anthropic > ai_key_log.txt 2>&1
%PY% tools\check_ai_key.py >> ai_key_log.txt 2>&1
type ai_key_log.txt
echo.
echo 如果上面顯示「AI 老師已就緒」，重新整理網頁就能使用批改。
pause
