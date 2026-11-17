"""單字與例句的發音音檔：由櫃台電腦用 edge-tts（Edge 的微軟神經語音）產生 mp3。

為什麼需要：瀏覽器內建的語音合成在不同裝置上品質差很多，Android 手機的 Chrome
還有已知問題（連續按下一個字，唸出來的卻一直是同一個字）。改成由伺服器產生音檔，
不管學生或主管用什麼裝置，聽到的都是正確的字，而且是同一個自然的聲音。

- 網址 /tts?text=...&accent=GB|US，同一段文字只產生一次，存在 instance/tts_cache/
- 產生失敗（例如沒裝 edge-tts 或沒網路）回 503，前端（static/ui.js）會改用瀏覽器語音
"""
import asyncio
import hashlib
import os
import threading

from flask import Blueprint, abort, request, send_file

bp = Blueprint('word_audio', __name__)

VOICES = {'GB': 'en-GB-SoniaNeural', 'US': 'en-US-AriaNeural'}
MAX_CHARS = 400
CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'instance', 'tts_cache')
_locks = {}
_locks_guard = threading.Lock()


def cache_path(text, voice):
    key = hashlib.sha1(f'{voice}\n{text}'.encode('utf-8')).hexdigest()
    return os.path.join(CACHE_DIR, f'{key}.mp3')


async def _synth(text, voice, path):
    import edge_tts
    tmp = path + '.part'
    proxy = os.environ.get('HTTPS_PROXY') or os.environ.get('https_proxy') or None
    try:
        with open(tmp, 'wb') as f:
            async for chunk in edge_tts.Communicate(text, voice, proxy=proxy).stream():
                if chunk['type'] == 'audio':
                    f.write(chunk['data'])
        if os.path.getsize(tmp) == 0:
            raise RuntimeError('沒有收到音訊')
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def ensure_audio(text, voice):
    """回傳音檔路徑；還沒產生過就現在產生（同一段文字同時只產生一次）。"""
    path = cache_path(text, voice)
    if os.path.exists(path):
        return path
    os.makedirs(CACHE_DIR, exist_ok=True)
    with _locks_guard:
        lock = _locks.setdefault(path, threading.Lock())
    with lock:
        if not os.path.exists(path):
            asyncio.run(asyncio.wait_for(_synth(text, voice, path), timeout=15))
    return path


@bp.route('/tts')
def tts():
    text = ' '.join((request.args.get('text') or '').split())
    if not text or len(text) > MAX_CHARS:
        abort(400)
    voice = VOICES.get((request.args.get('accent') or 'GB').upper(), VOICES['GB'])
    try:
        path = ensure_audio(text, voice)
    except Exception as e:   # 沒裝 edge-tts、沒網路、逾時：讓前端改用瀏覽器語音
        print(f'[發音] 產生音檔失敗：{e!r}')
        return ('', 503)
    # 網址裡已經帶著文字，同一個網址永遠是同一段聲音，可以放心讓瀏覽器快取
    return send_file(path, mimetype='audio/mpeg', conditional=True, max_age=30 * 24 * 3600)
