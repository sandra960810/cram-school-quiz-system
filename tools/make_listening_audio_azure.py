"""用 Azure 語音服務，把聽力逐字稿轉成 mp3。

音檔直接由題庫裡的逐字稿產生，所以音檔內容與題目必定一致。

準備：在專案資料夾放一個 azure_tts.txt，兩行
    第一行：Azure 語音服務的 KEY 1
    第二行：區域代碼，例如 southeastasia

用法：
    python tools/make_listening_audio.py            產生所有缺少的音檔
    python tools/make_listening_audio.py L01        只產生第 1 回
    python tools/make_listening_audio.py L01 2      只產生第 1 回的 Part 2
    python tools/make_listening_audio.py --force    已存在的也重新產生
"""
import json
import pathlib
import sys
import urllib.error
import urllib.request
import xml.sax.saxutils as sax

ROOT = pathlib.Path(__file__).resolve().parent.parent
BANK = ROOT / 'listening'
OUT = ROOT / 'static' / 'audio' / 'listening'
KEY_FILE = ROOT / 'azure_tts.txt'

# 說話者對應的語音。全部用英式，符合雅思聽力的主要口音。
VOICES = {
    'narrator': 'en-GB-RyanNeural',     # 考試指令旁白
    'f1': 'en-GB-SoniaNeural',
    'f2': 'en-GB-LibbyNeural',
    'f3': 'en-GB-AbbiNeural',
    'm1': 'en-GB-ThomasNeural',
    'm2': 'en-GB-NoahNeural',
    'm3': 'en-GB-OliverNeural',
}
# 旁白唸得稍慢，對話用自然語速
RATES = {'narrator': '-8%'}
OUTPUT_FORMAT = 'audio-24khz-48kbitrate-mono-mp3'


def load_key():
    if not KEY_FILE.exists():
        sys.exit(f'找不到 {KEY_FILE.name}。請先建立該檔案，第一行放金鑰、第二行放區域代碼。')
    lines = [ln.strip() for ln in KEY_FILE.read_text(encoding='utf-8-sig').splitlines() if ln.strip()]
    if len(lines) < 2:
        sys.exit(f'{KEY_FILE.name} 需要兩行：第一行金鑰，第二行區域代碼（例如 southeastasia）。')
    return lines[0], lines[1]


def build_ssml(cues):
    """把逐字稿組成 SSML。停頓用 <break>，不同說話者用不同 <voice>。"""
    body = []
    for cue in cues:
        if cue['v'] == 'pause':
            body.append(f'<break time="{int(float(cue["t"]) * 1000)}ms"/>')
            continue
        voice = VOICES.get(cue['v'])
        if not voice:
            sys.exit(f'逐字稿裡出現未定義的說話者代號：{cue["v"]}')
        text = sax.escape(cue['t'])
        rate = RATES.get(cue['v'])
        inner = f'<prosody rate="{rate}">{text}</prosody>' if rate else text
        # 每句之間留一點自然的間隔
        body.append(f'<voice name="{voice}">{inner}<break time="500ms"/></voice>')
    return ('<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" '
            'xml:lang="en-GB">' + ''.join(body) + '</speak>')


def synthesise(ssml, key, region):
    url = f'https://{region}.tts.speech.microsoft.com/cognitiveservices/v1'
    req = urllib.request.Request(url, data=ssml.encode('utf-8'), method='POST', headers={
        'Ocp-Apim-Subscription-Key': key,
        'Content-Type': 'application/ssml+xml',
        'X-Microsoft-OutputFormat': OUTPUT_FORMAT,
        'User-Agent': 'cram-school-quiz-system',
    })
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            return resp.read()
    except urllib.error.HTTPError as e:
        detail = e.read().decode('utf-8', 'replace')[:400]
        if e.code == 401:
            sys.exit('金鑰或區域不正確（401）。請確認 azure_tts.txt 的內容與 Azure 入口網站一致。')
        if e.code == 429:
            sys.exit('超出免費額度或請求太頻繁（429）。稍後再試，或檢查本月用量。')
        sys.exit(f'Azure 回傳錯誤 {e.code}：{detail}')
    except urllib.error.URLError as e:
        sys.exit(f'連線失敗：{e.reason}')


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    force = '--force' in sys.argv
    only_test = args[0] if args else None
    only_part = int(args[1]) if len(args) > 1 else None

    key, region = load_key()
    OUT.mkdir(parents=True, exist_ok=True)

    files = []
    for d in sorted(p for p in BANK.iterdir() if p.is_dir()):
        if only_test and d.name != only_test:
            continue
        for pf in sorted(d.glob('part*.json')):
            part = json.loads(pf.read_text(encoding='utf-8'))
            if only_part and part['no'] != only_part:
                continue
            files.append((d.name, part))

    if not files:
        sys.exit('沒有找到符合條件的題庫檔案。')

    total_chars = 0
    made = 0
    for test_key, part in files:
        target = OUT / part['audio']
        label = f'{test_key} Part {part["no"]}'
        if target.exists() and not force:
            print(f'  略過 {label}（{target.name} 已存在）')
            continue
        ssml = build_ssml(part['cues'])
        chars = sum(len(c['t']) for c in part['cues'] if c['v'] != 'pause')
        total_chars += chars
        print(f'  產生 {label}：約 {chars} 字元 …', flush=True)
        audio = synthesise(ssml, key, region)
        target.write_bytes(audio)
        made += 1
        print(f'     完成 {target.name}（{len(audio) // 1024} KB）')

    print(f'\n完成 {made} 個音檔，本次用掉約 {total_chars} 字元'
          f'（Azure 免費方案每月 50 萬字元）。')


if __name__ == '__main__':
    main()
