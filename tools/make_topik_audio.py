"""把韓檢模擬考的聽力台詞轉成 mp3（edge-tts 的韓語神經語音，免註冊、免金鑰）。

音檔直接由題庫（topik_mock/TOPIK1.txt、TOPIK1-2.txt…）裡的台詞產生，所以音檔內容與題目必定一致。
一回一個檔：static/audio/topik_mock/TOPIK1.mp3、TOPIK1-2.mp3…（不進 git）。題庫改過（台詞不一樣）會自動重新產生。
比照正式考試：TOPIK I 每題播兩次；TOPIK II 1～20 題播一次、21～50 題播兩次（topik_mock.repeats）。

用法：
    python tools/make_topik_audio.py          產生缺少或題庫改過的音檔
    python tools/make_topik_audio.py TOPIK1-2 只產生 TOPIK I 第 2 回
    python tools/make_topik_audio.py --force  全部重新產生
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
import topik_mock  # noqa: E402

OUT = ROOT / 'static' / 'audio' / 'topik_mock'
CACHE = ROOT / 'tools' / '.tts_cache'
SILENCE = (ROOT / 'tools' / 'assets' / 'silence_1s.mp3').read_bytes()
PROXY = os.environ.get('HTTPS_PROXY') or os.environ.get('https_proxy') or None

# 微軟的韓語神經語音（edge-tts 免費可用）只有 SunHi（女）、InJoon（男）、Hyunsu（男）三個，
# 所以旁白和第二個女生用 SunHi 調音高、語速區分。(語音, 語速, 音高)
VOICES = {
    'n': ('ko-KR-SunHiNeural', '-6%', '-14Hz'),     # 旁白：低一點、慢一點
    'f1': ('ko-KR-SunHiNeural', '+0%', '+6Hz'),
    'f2': ('ko-KR-SunHiNeural', '+4%', '+28Hz'),
    'm1': ('ko-KR-InJoonNeural', '+0%', '+0Hz'),
    'm2': ('ko-KR-HyunsuMultilingualNeural', '+0%', '+0Hz'),
}
# TOPIK I 唸慢一點（正式考試初級的語速也比較慢）
LEVEL_RATE = {1: -8, 2: 0}
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


async def check_voices():
    """合成前先確認語音都還在（微軟偶爾會下架或改名）。"""
    names = {v['ShortName'] for v in await edge_tts.list_voices(proxy=PROXY)}
    missing = sorted({v for v, _, _ in VOICES.values()} - names)
    if missing:
        sys.exit('找不到這些韓語語音：' + '、'.join(missing) + '。請把這份 log 給 Claude 看。')


async def build(level, test):
    out = bytearray()
    cues = topik_mock.listening_cues(test)
    delta = LEVEL_RATE[level]
    for i, cue in enumerate(cues):
        if cue['v'] == 'pause':
            out += SILENCE * int(cue['t'])
            continue
        if cue['v'] not in VOICES:
            sys.exit(f'{test["id"]}：台詞裡有沒定義的說話者代號 {cue["v"]}')
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
    checked = False
    jobs = [(no, rnd) for no in topik_mock.TESTS for rnd in topik_mock.rounds(no)]
    for no, rnd in jobs:
        key = topik_mock.tid(no, rnd)
        if args and key not in args:
            continue
        test = topik_mock.load(no, rnd)
        if not test:
            continue
        label = f'TOPIK {topik_mock.ROMAN[no]} 第 {rnd} 回'
        cues = topik_mock.listening_cues(test)
        stamp = hashlib.sha1(json.dumps([cues, VOICES, LEVEL_RATE[no]], ensure_ascii=False).encode()).hexdigest()
        mp3, mark = OUT / f'{key}.mp3', OUT / f'{key}.sha'
        if mp3.exists() and mark.exists() and mark.read_text() == stamp and not force:
            print(f'{label}：音檔已經是最新的，略過')
            continue
        if not checked:
            await check_voices()
            checked = True
        print(f'{label}：產生聽力音檔（{sum(1 for c in cues if c["v"] != "pause")} 句）…', flush=True)
        data = await build(no, test)
        mp3.write_bytes(data)
        mark.write_text(stamp)
        print(f'{label}：完成，{len(data) / 1e6:.1f} MB')


if __name__ == '__main__':
    asyncio.run(main())
