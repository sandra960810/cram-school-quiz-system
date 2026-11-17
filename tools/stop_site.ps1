# 關掉舊的網站（run.bat 啟動新網站前呼叫）
#
# 為什麼不能只看 netstat：app.py 用 debug 模式跑，會有「監看程式」和「實際網站」兩個 python。
# 5000 埠是監看程式開的、交給網站子程式用，所以 netstat 顯示的是監看程式的 PID。
# 只砍監看程式時，子程式會繼續佔著 5000 埠；之後 netstat 顯示的 PID 已經不存在，
# 舊網站就再也關不掉，新舊兩份網站會同時在跑。
#
# 做法：找出所有在跑 app.py 的 python（含子程式），連同整個程式樹一起關掉，
# 再補上任何還在聽 5000 埠的 python，最後等 5000 埠真的空出來。
# 不會動到 cloudflared（分享連結的通道），它不是 python。

$ErrorActionPreference = 'SilentlyContinue'
$port = 5000

function Get-SitePids {
    $pids = @()
    # 1. 命令列是「python … app.py」的程式（監看程式與網站子程式都是）
    $pids += Get-CimInstance Win32_Process |
        Where-Object { $_.Name -match '^pythonw?\.exe$|^py\.exe$' -and
                       $_.CommandLine -match '(^|[\s"\\/])app\.py("|\s|$)' } |
        ForEach-Object { $_.ProcessId }
    # 2. 還在聽 5000 埠、而且確實存在的 python
    $pids += Get-NetTCPConnection -LocalPort $port -State Listen |
        ForEach-Object { $_.OwningProcess } |
        Where-Object { (Get-Process -Id $_).ProcessName -match '^pythonw?$|^py$' }
    $pids | Sort-Object -Unique
}

$closed = @()
for ($round = 0; $round -lt 3; $round++) {
    $targets = @(Get-SitePids)
    if ($targets.Count -eq 0) { break }
    foreach ($p in $targets) {
        taskkill /F /T /PID $p *> $null
        $closed += $p
    }
    Start-Sleep -Milliseconds 800
}

# 等 5000 埠空出來（最多 10 秒）
for ($i = 0; $i -lt 20; $i++) {
    $busy = Get-NetTCPConnection -LocalPort $port -State Listen
    if (-not $busy) { break }
    Start-Sleep -Milliseconds 500
}

if ($closed.Count -gt 0) {
    Write-Host ("已關閉舊的網站（PID " + (($closed | Sort-Object -Unique) -join '、') + "）")
}
if (Get-NetTCPConnection -LocalPort $port -State Listen) {
    Write-Host "注意：5000 埠還被別的程式佔用，網站可能啟動失敗。請重新開機後再雙擊 run.bat。"
}
