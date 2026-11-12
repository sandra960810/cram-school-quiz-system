# 安裝 AI 真人語音（sherpa-onnx + Kokoro 模型），並產生試聽樣本
# 用法：雙擊專案資料夾裡的 setup_voice.bat
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$tts = Join-Path $root 'tts'
New-Item -ItemType Directory -Force $tts | Out-Null
$logFile = Join-Path $tts 'setup_log.txt'
Set-Content -Encoding UTF8 $logFile ''
function Log($m) {
    Write-Host $m
    # 記錄檔可能剛好被其他程式讀取，寫不進去就稍等重試，不要讓整個安裝中斷
    for ($i = 0; $i -lt 10; $i++) {
        try { Add-Content -Encoding UTF8 $logFile $m -ErrorAction Stop; return } catch { Start-Sleep -Milliseconds 300 }
    }
}
trap { Log "錯誤：$_"; exit 1 }

function Get-Archive($url, $name) {
    $file = Join-Path $tts $name
    if (-not (Test-Path $file)) {
        Log "下載 $name ..."
        Invoke-WebRequest -Uri $url -OutFile "$file.part" -UseBasicParsing
        Move-Item "$file.part" $file -Force
    }
    Log "解壓縮 $name ..."
    tar -xf $file -C $tts
    Remove-Item $file
}

# 1. sherpa-onnx Windows 程式（官方 GitHub 最新版）
$exe = Get-ChildItem $tts -Recurse -Filter 'sherpa-onnx-offline-tts.exe' -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $exe) {
    # releases/latest 有時是模型包，所以從最近的正式版裡找 Windows 程式
    $releases = Invoke-RestMethod 'https://api.github.com/repos/k2-fsa/sherpa-onnx/releases?per_page=40' -Headers @{ 'User-Agent' = 'quiz-system' }
    $asset = $null; $rel = $null
    foreach ($r in $releases) {
        if ($r.prerelease -or $r.tag_name -notmatch '^v\d') { continue }
        $asset = $r.assets | Where-Object { $_.name -match '^sherpa-onnx-v[\d\.]+-win-x64-shared-MT-Release\.tar\.bz2$' } | Select-Object -First 1
        if ($asset) { $rel = $r; break }
    }
    if (-not $asset) { throw "在 sherpa-onnx 最近的版本裡找不到 Windows 程式" }
    Log "sherpa-onnx 版本：$($rel.tag_name)  檔案：$($asset.name)  大小：$([math]::Round($asset.size/1MB,1)) MB"
    Get-Archive $asset.browser_download_url $asset.name
    $exe = Get-ChildItem $tts -Recurse -Filter 'sherpa-onnx-offline-tts.exe' | Select-Object -First 1
}
Log "程式：$($exe.FullName)"

# 2. Kokoro 語音模型（int8，約 130 MB）
$model = Join-Path $tts 'kokoro-int8-multi-lang-v1_0'
if (-not (Test-Path (Join-Path $model 'voices.bin'))) {
    Get-Archive 'https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/kokoro-int8-multi-lang-v1_0.tar.bz2' 'kokoro-int8-multi-lang-v1_0.tar.bz2'
}
Get-ChildItem $model | ForEach-Object { Log "  模型檔：$($_.Name)" }

# 3. 寫設定檔給網站使用
$onnx = Get-ChildItem $model -Filter '*.onnx' | Select-Object -First 1
$config = @{
    exe = $exe.FullName
    model = $onnx.FullName
    voices = (Join-Path $model 'voices.bin')
    tokens = (Join-Path $model 'tokens.txt')
    data_dir = (Join-Path $model 'espeak-ng-data')
    lexicon = (Join-Path $model 'lexicon-us-en.txt')
}
$config | ConvertTo-Json | Set-Content -Encoding UTF8 (Join-Path $tts 'config.json')

# 4. 產生試聽樣本
$samples = Join-Path $tts 'samples'
New-Item -ItemType Directory -Force $samples | Out-Null
$text = 'Climate change is one of the most serious problems facing the world today. Contaminate. Curriculum.'
foreach ($v in @(@{sid=21; name='uk_female_emma'}, @{sid=26; name='uk_male_george'}, @{sid=3; name='us_female_heart'})) {
    $out = Join-Path $samples "$($v.name).wav"
    $argv = @("--kokoro-model=$($config.model)", "--kokoro-voices=$($config.voices)", "--kokoro-tokens=$($config.tokens)",
              "--kokoro-data-dir=$($config.data_dir)", "--kokoro-lexicon=$($config.lexicon)",
              "--num-threads=4", "--sid=$($v.sid)", "--output-filename=$out", $text)
    $sw = [Diagnostics.Stopwatch]::StartNew()
    $ErrorActionPreference = 'Continue'
    & $exe.FullName @argv 2>&1 | Select-Object -Last 3 | ForEach-Object { Log "    $_" }
    Log "樣本 $($v.name)：$(if (Test-Path $out) { [math]::Round((Get-Item $out).Length/1KB) } else { 0 }) KB，花 $([math]::Round($sw.Elapsed.TotalSeconds,1)) 秒"
}
Log '完成'
