@echo off
chcp 65001 >nul
rem 產生韓檢模擬考（TOPIK I、II 每一回）的聽力音檔：雙擊即可。題目沒改過的會略過。
rem 結果寫在 topik_audio_log.txt。
cd /d "%~dp0"
set PY=python
if exist venv\Scripts\python.exe set PY=venv\Scripts\python.exe
set LOG=topik_audio_log.txt
echo === 更新程式 === > %LOG%
git pull --ff-only origin main >> %LOG% 2>&1
echo === 安裝 edge-tts === >> %LOG%
%PY% -m pip install --disable-pip-version-check edge-tts >> %LOG% 2>&1
echo === 檢查題庫 === >> %LOG%
%PY% tools\check_topik_mock.py >> %LOG% 2>&1
if errorlevel 1 (
  echo 題庫檢查沒通過，先不產生音檔。請把這份 log 給 Claude 看。 >> %LOG%
  goto done
)
echo === 產生缺少的音檔（每回約需 5～10 分鐘，需要網路） === >> %LOG%
%PY% tools\make_topik_audio.py >> %LOG% 2>&1
:done
echo === 完成 === >> %LOG%
type %LOG%
echo.
pause
