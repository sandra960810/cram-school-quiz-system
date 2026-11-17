"""原創雅思聽力題庫：載入、渲染與批改。

題庫放在 listening/<測驗代號>/，每個 Part 一個 JSON，內容包含逐字稿、題組與
每題的答案與解析。音檔由 tools/make_listening_audio.py 依同一份逐字稿產生，
因此音檔內容與題目必定一致。
"""
import json
import os
import re
from markupsafe import Markup, escape

BASE = os.path.dirname(os.path.abspath(__file__))
BANK_DIR = os.path.join(BASE, 'listening')
AUDIO_DIR = os.path.join(BASE, 'static', 'audio', 'listening')

SECTION = 'listening'
GAP_RE = re.compile(r'\{(?:(\d+)|ex:([^}]*))\}')


# ---------------------------------------------------------------- 載入

def list_tests():
    """回傳題庫清單，含音檔是否已產生。"""
    path = os.path.join(BANK_DIR, 'tests.json')
    if not os.path.exists(path):
        return []
    with open(path, encoding='utf-8') as f:
        tests = json.load(f)
    for t in tests:
        parts = _part_files(t['key'])
        t['parts_ready'] = len(parts)
        t['audio_ready'] = all(
            os.path.exists(os.path.join(AUDIO_DIR, p['audio'])) for p in parts
        ) if parts else False
    return tests


def _part_files(key):
    d = os.path.join(BANK_DIR, key)
    if not os.path.isdir(d):
        return []
    parts = []
    for name in sorted(os.listdir(d)):
        if re.fullmatch(r'part\d+\.json', name):
            with open(os.path.join(d, name), encoding='utf-8') as f:
                parts.append(json.load(f))
    return sorted(parts, key=lambda p: p['no'])


def load_test(key):
    """載入一份測驗；找不到回傳 None。"""
    if not re.fullmatch(r'[A-Za-z0-9_-]+', key or ''):
        return None
    parts = _part_files(key)
    if not parts:
        return None
    meta_path = os.path.join(BANK_DIR, key, 'meta.json')
    meta = {}
    if os.path.exists(meta_path):
        with open(meta_path, encoding='utf-8') as f:
            meta = json.load(f)
    for p in parts:
        p['audio_exists'] = os.path.exists(os.path.join(AUDIO_DIR, p['audio']))
        p['rendered'] = [_render_group(g) for g in p['groups']]
    return {
        'key': key,
        'title': meta.get('title', key),
        'subtitle': meta.get('subtitle', ''),
        'parts': parts,
        'audio_ready': all(p['audio_exists'] for p in parts),
    }


def answer_key(key):
    """{題號: [可接受的答案, ...]}"""
    out = {}
    for p in _part_files(key):
        for q in p['questions']:
            out[q['no']] = q['answers']
    return out


def explanations(key):
    """{題號: {answers, explain, quote, part}}"""
    out = {}
    for p in _part_files(key):
        for q in p['questions']:
            out[q['no']] = {
                'answers': q['answers'],
                'explain': q.get('explain', ''),
                'quote': q.get('quote', ''),
                'part': p['no'],
            }
    return out


def transcript(key):
    """給檢討用的逐字稿，依 Part 分組。"""
    out = []
    for p in _part_files(key):
        lines = [c for c in p['cues'] if c['v'] != 'pause' and c['v'] != 'narrator']
        out.append({'no': p['no'], 'context': p['context'], 'lines': lines})
    return out


# ---------------------------------------------------------------- 渲染

def _input_for(qno):
    # 比照正式雅思：題號以粗體印在空格前，作答後題號仍看得到
    return (f'<span class="gap"><b class="gapno">{qno}</b>'
            f'<input type="text" class="fill" data-q="{qno}" name="q_{qno}" '
            f'aria-label="第 {qno} 題" autocomplete="off"></span>')


def _gap_html(text):
    """把 {3} 換成輸入框、{ex:Fraser} 換成範例答案。"""
    def sub(m):
        if m.group(1):
            return _input_for(int(m.group(1)))
        return f'<span class="example-ans">……{escape(m.group(2))}……</span>'
    return Markup(GAP_RE.sub(sub, escape(text)))


def note_text(ln):
    """筆記行可以是字串（項目符號行）或 {"text": ..., "sub": true}（接續上一行的縮排句子）。"""
    return ln['text'] if isinstance(ln, dict) else ln


def _note_line(ln):
    text = note_text(ln)
    return {'html': _gap_html(text),
            'sub': isinstance(ln, dict) and bool(ln.get('sub')),
            'example': '{ex:' in text}


def _render_group(g):
    """把題組轉成樣板直接可用的結構（HTML 片段已處理成 Markup）。"""
    out = dict(g)
    if g['type'] == 'gapfill':
        # example：範例列，樣板會在它上方印出 Example 小標，和正式考卷一樣
        out['rows'] = [{'label': r.get('label', ''), 'html': _gap_html(r['text']),
                        'example': '{ex:' in r['text']}
                       for r in g.get('rows', [])]
        out['sections'] = [{'heading': s.get('heading', ''),
                            'lines': [_note_line(ln) for ln in s['lines']]}
                           for s in g.get('sections', [])]
    elif g['type'] == 'matching':
        out['option_list'] = [(k, g['options'][k]) for k in sorted(g['options'])]
    return out


# ---------------------------------------------------------------- 批改

def normalize(text):
    """比對用：全部小寫、只留字母數字與空白、多個空白合併。"""
    s = str(text or '').strip().casefold()
    s = re.sub(r'[^0-9a-zÀ-ɏ ]+', ' ', s)
    return ' '.join(s.split())


# 填空題常見的可省略冠詞
_LEADING = ('the ', 'a ', 'an ')


def _variants(ans):
    n = normalize(ans)
    out = {n}
    for lead in _LEADING:
        if n.startswith(lead):
            out.add(n[len(lead):])
        out.add(lead + n)
    return out


def check_one(given, accepted):
    g = normalize(given)
    if not g:
        return False
    for a in accepted:
        if g in _variants(a):
            return True
    return False


def grade(key, given):
    """given 是 {題號(int): 學生作答}。回傳每題結果，依題號排序。"""
    keyed = answer_key(key)
    results = []
    for qno in sorted(keyed):
        ans = given.get(qno, '')
        results.append({
            'qno': qno,
            'given': str(ans or '').strip(),
            'is_correct': check_one(ans, keyed[qno]),
            'answer': ' / '.join(keyed[qno]),
        })
    return results
