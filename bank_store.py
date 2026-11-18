"""題庫的存取層：原始題庫（進 git）加上管理員在後台的改動（只存在本機）。

為什麼分兩層：櫃台電腦每次 run.bat 都會 git pull，如果後台直接改 listening/、reading/
底下的檔案，git pull 會因為本機有改動而失敗，或把改動蓋掉。所以：

- 原始題庫維持唯讀；後台存檔一律寫到 instance/bank_edits/<技能>/<測驗>/<檔名>（不進 git）
- 讀取時本機改過的版本優先，沒改過的才讀原始檔
- 每次覆寫前把舊版本留一份到 _history/，改壞了還找得回來
- 新增、下架的測驗記在 _catalog.json，不動原始的 tests.json
"""
import hashlib
import json
import os
import re
import threading
import time

BASE = os.path.dirname(os.path.abspath(__file__))
EDIT_DIR = os.path.join(BASE, 'instance', 'bank_edits')
HISTORY_DIR = os.path.join(EDIT_DIR, '_history')
CATALOG_FILE = os.path.join(EDIT_DIR, '_catalog.json')
AUDIO_STATE_FILE = os.path.join(EDIT_DIR, '_audio_state.json')

SECTIONS = ('listening', 'reading', 'writing', 'speaking')
# 後台新增的測驗代號多一個 X，之後題庫更新加入 L03、R02 時才不會撞名
NEW_PREFIX = {'listening': 'LX', 'reading': 'RX', 'writing': 'WX', 'speaking': 'SX'}
KEEP_HISTORY = 20

KEY_RE = re.compile(r'[A-Za-z0-9_-]+')
NAME_RE = re.compile(r'(meta|test|part\d+|passage\d+|task\d+)\.json')

_lock = threading.Lock()


def _safe(section, key, name=None):
    if section not in SECTIONS or not KEY_RE.fullmatch(key or ''):
        return False
    return name is None or bool(NAME_RE.fullmatch(name or ''))


def _base_path(section, key, name):
    return os.path.join(BASE, section, key, name)


def _edit_path(section, key, name):
    return os.path.join(EDIT_DIR, section, key, name)


def _read_json(path, default=None):
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def _write_json(path, data):
    """先寫暫存檔再換名字，學生剛好在讀取時不會讀到寫一半的檔案。"""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f'{path}.{os.getpid()}.{threading.get_ident()}.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


# ---------------------------------------------------------------- 題庫檔案

def read(section, key, name, default=None):
    """讀一個題庫檔：本機改過的版本優先。"""
    if not _safe(section, key, name):
        return default
    data = _read_json(_edit_path(section, key, name))
    if data is not None:
        return data
    return _read_json(_base_path(section, key, name), default)


def read_original(section, key, name):
    """只讀原始題庫（沒有的話回傳 None）。"""
    return _read_json(_base_path(section, key, name)) if _safe(section, key, name) else None


def names(section, key):
    """這份測驗有哪些題庫檔（原始與本機合併）。"""
    if not _safe(section, key):
        return []
    found = set()
    for d in (os.path.join(BASE, section, key), os.path.join(EDIT_DIR, section, key)):
        if os.path.isdir(d):
            found.update(n for n in os.listdir(d) if NAME_RE.fullmatch(n))
    return sorted(found)


def is_edited(section, key, name):
    return _safe(section, key, name) and os.path.exists(_edit_path(section, key, name))


def _backup(section, key, name, data):
    folder = os.path.join(HISTORY_DIR, section, key)
    stem = name[:-5]
    _write_json(os.path.join(folder, f'{stem}.{time.strftime("%Y%m%d_%H%M%S")}.{time.time_ns() % 1000000}.json'), data)
    old = sorted(n for n in os.listdir(folder) if n.startswith(stem + '.'))
    for n in old[:-KEEP_HISTORY]:
        os.remove(os.path.join(folder, n))


def write(section, key, name, data):
    """存到本機改動區；內容沒變就不寫。回傳有沒有真的寫入。"""
    if not _safe(section, key, name):
        raise ValueError('題庫路徑不正確')
    with _lock:
        current = read(section, key, name)
        if current == data:
            return False
        if current is not None:
            _backup(section, key, name, current)
        _write_json(_edit_path(section, key, name), data)
    return True


def revert(section, key, name):
    """放棄本機改動，回到原始題庫（舊內容仍留在 _history）。"""
    if not (is_edited(section, key, name) and read_original(section, key, name) is not None):
        return False
    with _lock:
        _backup(section, key, name, read(section, key, name))
        os.remove(_edit_path(section, key, name))
    return True


# ---------------------------------------------------------------- 測驗清單

def _load_catalog():
    return _read_json(CATALOG_FILE, {}) or {}


def _section_catalog(cat, section):
    s = cat.setdefault(section, {})
    s.setdefault('added', [])
    s.setdefault('edited', {})
    s.setdefault('draft', [])
    s.setdefault('trash', [])
    return s


def all_tests(section):
    """全部測驗（含草稿與回收區），每筆多 draft、trash、added 三個旗標。"""
    cat = _section_catalog(_load_catalog(), section)
    base = _read_json(os.path.join(BASE, section, 'tests.json'), []) or []
    out = []
    for t in base + cat['added']:
        item = dict(t)
        item.update(cat['edited'].get(t['key'], {}))
        item['draft'] = t['key'] in cat['draft']
        item['trash'] = t['key'] in cat['trash']
        item['added'] = any(a['key'] == t['key'] for a in cat['added'])
        out.append(item)
    return out


def tests(section):
    """學生看得到的測驗（草稿與回收區不算）。"""
    return [t for t in all_tests(section) if not t['draft'] and not t['trash']]


def find_test(section, key):
    return next((t for t in all_tests(section) if t['key'] == key), None)


def is_draft(section, key):
    return key in _section_catalog(_load_catalog(), section)['draft']


def add_test(section, title, topics, files):
    """新增一份測驗（先是草稿，學生看不到），回傳代號。"""
    with _lock:
        cat = _load_catalog()
        s = _section_catalog(cat, section)
        used = {t['key'] for t in s['added']}
        n = 1
        while f'{NEW_PREFIX[section]}{n:02d}' in used:
            n += 1
        key = f'{NEW_PREFIX[section]}{n:02d}'
        for name, data in files(key).items():
            _write_json(_edit_path(section, key, name), data)
        s['added'].append({'key': key, 'title': title, 'topics': topics})
        s['draft'].append(key)
        _write_json(CATALOG_FILE, cat)
    return key


def set_info(section, key, title, topics):
    with _lock:
        cat = _load_catalog()
        _section_catalog(cat, section)['edited'][key] = {'title': title, 'topics': topics}
        _write_json(CATALOG_FILE, cat)


def _set_flag(section, key, flag, on):
    with _lock:
        cat = _load_catalog()
        items = _section_catalog(cat, section)[flag]
        if on and key not in items:
            items.append(key)
        elif not on and key in items:
            items.remove(key)
        _write_json(CATALOG_FILE, cat)


def set_draft(section, key, on):
    _set_flag(section, key, 'draft', on)


def set_trash(section, key, on):
    _set_flag(section, key, 'trash', on)


# ---------------------------------------------------------------- 聽力音檔是否過期

def cue_hash(cues):
    return hashlib.sha1(json.dumps(cues, ensure_ascii=False, sort_keys=True).encode('utf-8')).hexdigest()


def audio_stale(key, name, cues):
    """逐字稿和產生音檔時的內容不一樣，音檔就要重做。"""
    known = (_read_json(AUDIO_STATE_FILE, {}) or {}).get(f'{key}/{name}')
    if known is None:
        original = read_original('listening', key, name)
        known = cue_hash(original['cues']) if original else None
    return known != cue_hash(cues)


def mark_audio_made(key, name, cues):
    with _lock:
        state = _read_json(AUDIO_STATE_FILE, {}) or {}
        state[f'{key}/{name}'] = cue_hash(cues)
        _write_json(AUDIO_STATE_FILE, state)
