"""把聽力逐字稿轉成 mp3（使用 edge-tts，免註冊、免金鑰）。

edge-tts 使用的就是 Microsoft Edge 內建的那套神經語音（Sonia、Ryan、Libby…），
不需要申請任何帳號或金鑰，只要電腦能上網即可。

音檔直接由題庫裡的逐字稿產生，所以音檔內容與題目必定一致。

第一次使用前先安裝：
    venv\\Scripts\\python.exe -m pip install edge-tts

用法：
    python tools/make_listening_audio.py            產生所有缺少的音檔
    python tools/make_listening_audio.py L01        只產生第 1 回
    python tools/make_listening_audio.py L01 2      只產生第 1 回的 Part 2
    python tools/make_listening_audio.py --force    已存在的也重新產生
    python tools/make_listening_audio.py --voices   列出可用的英式語音
"""
import asyncio
import hashlib
import json
import pathlib
import sys

try:
    import edge_tts
except ImportError:
    sys.exit('找不到 edge-tts。請先執行：\n'
             '    venv\\Scripts\\python.exe -m pip install edge-tts')

ROOT = pathlib.Path(__file__).resolve().parent.parent
BANK = ROOT / 'listening'
OUT = ROOT / 'static' / 'audio' / 'listening'
CACHE = ROOT / 'tools' / '.tts_cache'
SILENCE = (ROOT / 'tools' / 'assets' / 'silence_1s.mp3').read_bytes()

# 說話者代號對應的語音，全部英式，符合雅思聽力的主要口音。
VOICES = {
    'narrator': ('en-GB-RyanNeural', '-8%'),    # 考試指令旁白，唸慢一點
    'f1': ('en-GB-SoniaNeural', '+0%'),
    'f2': ('en-GB-LibbyNeural', '+0%'),
    'f3': ('en-GB-MaisieNeural', '+0%'),
    'm1': ('en-GB-ThomasNeural', '+0%'),
    'm2': ('en-GB-NoahNeural', '+0%'),
    'm3': ('en-GB-OliverNeural', '+0%'),
}
RETRIES = 3


async def list_voices():
    voices = await edge_tts.list_voices()
    for v in sorted(voices, key=lambda x: x['ShortName']):
        if v['Locale'].startswith('en-GB'):
            print(f"  {v['ShortName']:<28} {v['Gender']}")


async def say(text, voice, rate):
    """合成一句話，回傳 mp3 bytes；相同內容會用快取，重跑很快。"""
    tag = hashlib.sha1(f'{voice}|{rate}|{text}'.encode('utf-8')).hexdigest()[:20]
    cached = CACHE / f'{tag}.mp3'
    if cached.exists():
        return cached.read_bytes()

    last = None
    for attempt in range(1, RETRIES + 1):
        try:
            buf = bytearray()
            async for chunk in edge_tts.Communicate(text, voice, rate=rate).stream():
                if chunk['type'] == 'audio':
                    buf += chunk['data']
            if not buf:
                raise RuntimeError('語音服務回傳空內容')
            CACHE.mkdir(parents=True, exist_ok=True)
            cached.write_bytes(bytes(buf))
            return bytes(buf)
        except Exception as e:                      # 網路偶爾會斷，重試
            last = e
            if attempt < RETRIES:
                await asyncio.sleep(2 * attempt)
    raise RuntimeError(f'合成失敗（已重試 {RETRIES} 次）：{last}')


async def build_part(part):
    """依逐字稿組成整個 Part 的 mp3。停頓直接接靜音片段。"""
    out = bytearray()
    spoken = 0
    for cue in part['cues']:
        if cue['v'] == 'pause':
            out += SILENCE * int(round(float(cue['t'])))
            continue
        if cue['v'] not in VOICES:
            sys.exit(f'逐字稿裡出現未定義的說話者代號：{cue["v"]}')
        voice, rate = VOICES[cue['v']]
        out += await say(cue['t'], voice, rate)
        out += SILENCE[:len(SILENCE) // 2]          # 句與句之間留半秒
        spoken += len(cue['t'])
    return bytes(out), spoken


def collect(only_test, only_part):
    files = []
    for d in sorted(p for p in BANK.iterdir() if p.is_dir()):
        if only_test and d.name != only_test:
            continue
        for pf in sorted(d.glob('part*.json')):
            part = json.loads(pf.read_text(encoding='utf-8'))
            if only_part and part['no'] != only_part:
                continue
            files.append((d.name, part))
    return files


async def main():
    if '--voices' in sys.argv:
        await list_voices()
        return
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    force = '--force' in sys.argv
    files = collect(args[0] if args else None, int(args[1]) if len(args) > 1 else None)
    if not files:
        sys.exit('沒有找到符合條件的題庫檔案。')

    OUT.mkdir(parents=True, exist_ok=True)
    made = 0
    for test_key, part in files:
        target = OUT / part['audio']
        label = f'{test_key} Part {part["no"]}'
        if target.exists() and not force:
            print(f'  略過 {label}（{target.name} 已存在）')
            continue
        print(f'  產生 {label} …', flush=True)
        audio, spoken = await build_part(part)
        target.write_bytes(audio)
        made += 1
        print(f'     完成 {target.name}（{len(audio) // 1024} KB，約 {spoken} 字元）')

    print(f'\n完成 {made} 個音檔，存放在 static/audio/listening/。')
    if made:
        print('重新整理聽力測驗頁面就能播放了。')


if __name__ == '__main__':
    asyncio.run(main())
