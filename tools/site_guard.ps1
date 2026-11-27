# 網站守護程式（由 site_guard.bat 執行）
# 每 2 分鐘檢查：1) 網站有沒有在聽 5000 埠  2) 官網通道 site-tunnel.exe 有沒有在跑
# 掛掉就自動重啟，結果記在 site_guard_log.txt。第一次執行會把捷徑放進「啟動」資料夾，開機自動跑。
# run.bat 正在準備（git pull、匯入單字）時 5000 埠會暫時空著，這段時間不出手，避免跟 run.bat 打架。

$ErrorActionPreference = 'SilentlyContinue'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$log = Join-Path $root 'site_guard_log.txt'
function Log($m) { ('{0:yyyy-MM-dd HH:mm:ss} {1}' -f (Get-Date), $m) | Add-Content -Encoding UTF8 $log }

# 只跑一份：已經有別的 site_guard.ps1 在跑就結束
$others = Get-CimInstance Win32_Process |
    Where-Object { $_.CommandLine -match 'site_guard\.ps1' -and $_.ProcessId -ne $PID }
if ($others) { Log '已經有一份守護程式在跑，這份不重複啟動。' ; exit }

# 加進開機自動執行（啟動資料夾捷徑，最小化視窗）
$startup = [Environment]::GetFolderPath('Startup')
$lnkPath = Join-Path $startup '網站守護程式.lnk'
if (-not (Test-Path $lnkPath)) {
    $ws = New-Object -ComObject WScript.Shell
    $lnk = $ws.CreateShortcut($lnkPath)
    $lnk.TargetPath = Join-Path $root 'site_guard.bat'
    $lnk.WorkingDirectory = $root
    $lnk.WindowStyle = 7
    $lnk.Save()
    Log ('已加入開機自動執行：' + $lnkPath)
}

$py = Join-Path $root 'venv\Scripts\python.exe'
if (-not (Test-Path $py)) { $py = 'python' }

Log '守護程式啟動，每 2 分鐘檢查一次網站與官網通道。'
# 開機時啟動資料夾的 site_tunnel.bat 也會同時跑，先等它一分鐘，避免兩邊同時開通道
Start-Sleep 60
while ($true) {
    # 1) 網站（5000 埠）
    if (-not (Get-NetTCPConnection -LocalPort 5000 -State Listen)) {
        $busy = Get-CimInstance Win32_Process |
            Where-Object { $_.CommandLine -match 'run\.bat|import_sheet\.py|dedupe_vocab\.py|stop_site\.ps1' }
        if ($busy) {
            Log '5000 埠暫時沒開，但 run.bat 正在準備，先等它跑完。'
        } else {
            Start-Sleep 20
            if (-not (Get-NetTCPConnection -LocalPort 5000 -State Listen)) {
                Log '網站沒有在跑，自動重新啟動。'
                $cmd = 'set PYTHONUTF8=1 && "{0}" app.py' -f $py
                Start-Process cmd -ArgumentList '/k', $cmd -WorkingDirectory $root -WindowStyle Minimized
            }
        }
    }
    # 2) 官網通道
    if (-not (Get-Process 'site-tunnel')) {
        if (Test-Path (Join-Path $root 'site-tunnel.exe')) {
            Log '官網通道沒有在跑，自動重新啟動。'
            Start-Process cmd -ArgumentList '/c', 'site-tunnel.exe tunnel --no-autoupdate run trinity-site >> site_tunnel_log.txt 2>&1' -WorkingDirectory $root -WindowStyle Minimized
        } else {
            Log '找不到 site-tunnel.exe，無法啟動官網通道（雙擊 site_tunnel.bat 可以重新下載）。'
        }
    }
    # 紀錄檔太大就只留最後 500 行
    $f = Get-Item $log
    if ($f -and $f.Length -gt 200KB) { (Get-Content $log -Tail 500) | Set-Content -Encoding UTF8 $log }
    Start-Sleep 120
}
