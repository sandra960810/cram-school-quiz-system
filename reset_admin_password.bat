@echo off
chcp 65001 >nul
cd /d "%~dp0"
title 重設管理員密碼

echo ============================================
echo   重設管理員後台的密碼
echo ============================================
echo.
echo 會清除目前的管理員密碼。清除後，請在這台電腦打開
echo   http://127.0.0.1:5000/admin
echo 重新設定一組新密碼（只有這台電腦能設定，公開連結不行）。
echo 學生資料、單字都不會受影響。
echo.
set "ANS="
set /p "ANS=確定要重設嗎？輸入 Y 後按 Enter："
if /i not "%ANS%"=="Y" ( echo 已取消。 & pause & exit /b 0 )
if exist instance\admin.json del instance\admin.json
echo.
echo 已清除。現在幫你打開設定頁...
start "" http://127.0.0.1:5000/admin
pause
