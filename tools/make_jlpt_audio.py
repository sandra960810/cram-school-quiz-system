"""把日檢模擬考的聽解台詞轉成 mp3（edge-tts 的日語神經語音，免註冊、免金鑰）。

音檔直接由題庫（jlpt_mock/N5.txt…）裡的台詞產生，所以音檔內容與題目必定一致。
一級一個檔：static/audio/jlpt_mock/N5.mp3（不進 git）。題庫改過（台詞不一樣）會自動重新產生。

用法：
    python tools/make_jlpt_audio.py          產生缺少或題庫改過的音檔
    python tools/make_jlpt_audio.py N5       只產生 N5
    python tools/make_jlpt_audio.py --force  全部重新產生
"""
import asyncio
import hashlib
import json
import pathlib
import sys

try:
    import edge_tts
except ImportError:
    sys.exit('找不到 edge-tts。請先執行：python -m pip install edge-tts')

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import os  # noqa: E402
import jlpt_mock  # noqa: E402

OUT = ROOT / 'static' / 'audio' / 'jlpt_mock'
CACHE = ROOT / 'tools' / '.tts_cache'
SILENCE = (ROOT / 'tools' / 'assets' / 'silence_1s.mp3').read_bytes()
PROXY = os.environ.get('HTTPS_PROXY') or os.environ.get('https_proxy') or None

# 微軟的日語神經語音只有 Nanami（女）和 Keita（男）兩個，所以用音高、語速區分旁白與第二個角色。
# (語音, 語速, 音高)
VOICES = {
    'n': ('ja-JP-NanamiNeural', '-6%', '-12Hz'),    # 旁白：低一點、慢一點
    'f1': ('ja-JP-NanamiNeural', '+0%', '+8Hz'),
    'f2': ('ja-JP-NanamiNeural', '+4%', '+30Hz'),
    'm1': ('ja-JP-KeitaNeural', '+0%', '+0Hz'),
    'm2': ('ja-JP-KeitaNeural', '-3%', '-18Hz'),
}
# 低等級唸慢一點（正式考試 N5、N4 的語速也比較慢）
LEVEL_RATE = {5: -14, 4: -10, 3: -4, 2: 0, 1: 0}
RETRIES = 4


def shift(rate, delta):
    return f'{int(rate.rstrip("%")) + delta:+d}%'


async def say(text, voice, rate, pitch):
    tag = hashlib.sha1(f'{voice}|{rate}|{pitch}|{text}'.encode('utf-8')).hexdigest()[:20]
    cached = CACHE / f'{tag}.mp3'
    if cached.exists():
        return cached.read_bytes()
    last = None
    for attempt in range(1, RETRIES + 1):
        try:
            buf = bytearray()
            async for chunk in edge_tts.Communicate(text, voice, rate=rate, pitch=pitch, proxy=PROXY).stream():
                if chunk['type'] == 'audio':
                    buf += chunk['data']
            if not buf:
                raise RuntimeError('語音服務回傳空內容')
            CACHE.mkdir(parents=True, exist_ok=True)
            cached.write_bytes(bytes(buf))
            return bytes(buf)
        except Exception as e:      # 網路偶爾會斷，重試
            last = e
            await asyncio.sleep(2 * attempt)
    raise RuntimeError(f'合成失敗（{voice}，已重試 {RETRIES} 次）：{last}\n  問題句子：{text[:60]}')


async def build(level, test):
    out = bytearray()
    cues = jlpt_mock.listening_cues(test)
    delta = LEVEL_RATE[level]
    for i, cue in enumerate(cues):
        if cue['v'] == 'pause':
            out += SILENCE * int(cue['t'])
            continue
        if cue['v'] not in VOICES:
            sys.exit(f'N{level}：台詞裡有沒定義的說話者代號 {cue["v"]}')
        voice, rate, pitch = VOICES[cue['v']]
        out += await say(cue['t'], voice, shift(rate, delta), pitch)
        out += SILENCE[:len(SILENCE) // 2]
        if i % 40 == 0:
            print(f'    … {i}/{len(cues)}', flush=True)
    return bytes(out)


async def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    force = '--force' in sys.argv
    OUT.mkdir(parents=True, exist_ok=True)
    for level in jlpt_mock.LEVELS:
        if args and f'N{level}' not in args:
            continue
        test = jlpt_mock.load(level)
        if not test:
            continue
        cues = jlpt_mock.listening_cues(test)
        stamp = hashlib.sha1(json.dumps([cues, VOICES, LEVEL_RATE[level]], ensure_ascii=False).encode()).hexdigest()
        mp3, mark = OUT / f'N{level}.mp3', OUT / f'N{level}.sha'
        if mp3.exists() and mark.exists() and mark.read_text() == stamp and not force:
            print(f'N{level}：音檔已經是最新的，略過')
            continue
        print(f'N{level}：產生聽解音檔（{sum(1 for c in cues if c["v"] != "pause")} 句）…', flush=True)
        data = await build(level, test)
        mp3.write_bytes(data)
        mark.write_text(stamp)
        print(f'N{level}：完成，{len(data) / 1e6:.1f} MB')


if __name__ == '__main__':
    asyncio.run(main())
