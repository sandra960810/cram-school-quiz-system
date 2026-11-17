"""原創雅思閱讀題庫（學術組）：載入、渲染與批改。

題庫放在 reading/<測驗代號>/，每篇文章一個 JSON（passage1~3.json），內容包含
文章段落、題組與每題的答案、解析、原文引句。批改規則與聽力相同，直接沿用
listening_bank 的比對函式，兩邊的判分標準才會一致。
"""
import json
import os
import re
from markupsafe import Markup, escape

import listening_bank

BASE = os.path.dirname(os.path.abspath(__file__))
BANK_DIR = os.path.join(BASE, 'reading')

SECTION = 'reading'
GAP_RE = re.compile(r'\{(\d+)\}')

# 是非題與觀點題的固定選項
JUDGE_OPTIONS = {
    'tfng': ['TRUE', 'FALSE', 'NOT GIVEN'],
    'ynng': ['YES', 'NO', 'NOT GIVEN'],
}


# ---------------------------------------------------------------- 載入

def list_tests():
    path = os.path.join(BANK_DIR, 'tests.json')
    if not os.path.exists(path):
        return []
    with open(path, encoding='utf-8') as f:
        tests = json.load(f)
    for t in tests:
        t['passages_ready'] = len(_passage_files(t['key']))
    return [t for t in tests if t['passages_ready']]


def _passage_files(key):
    d = os.path.join(BANK_DIR, key)
    if not os.path.isdir(d):
        return []
    out = []
    for name in os.listdir(d):
        if re.fullmatch(r'passage\d+\.json', name):
            with open(os.path.join(d, name), encoding='utf-8') as f:
                out.append(json.load(f))
    return sorted(out, key=lambda p: p['no'])


def load_test(key):
    """載入一份測驗；找不到回傳 None。"""
    if not re.fullmatch(r'[A-Za-z0-9_-]+', key or ''):
        return None
    passages = _passage_files(key)
    if not passages:
        return None
    meta_path = os.path.join(BANK_DIR, key, 'meta.json')
    meta = {}
    if os.path.exists(meta_path):
        with open(meta_path, encoding='utf-8') as f:
            meta = json.load(f)
    for p in passages:
        p['rendered'] = [_render_group(g) for g in p['groups']]
        nos = [q['no'] for q in p['questions']]
        p['first'], p['last'] = min(nos), max(nos)
    return {
        'key': key,
        'title': meta.get('title', key),
        'subtitle': meta.get('subtitle', ''),
        'passages': passages,
        'total': sum(len(p['questions']) for p in passages),
    }


def answer_key(key):
    """{題號: [可接受的答案, ...]}"""
    return {q['no']: q['answers'] for p in _passage_files(key) for q in p['questions']}


def explanations(key):
    """{題號: {answers, explain, quote, part}}；part 是文章編號，和聽力共用欄位名稱。"""
    out = {}
    for p in _passage_files(key):
        for q in p['questions']:
            out[q['no']] = {
                'answers': q['answers'],
                'explain': q.get('explain', ''),
                'quote': q.get('quote', ''),
                'part': p['no'],
            }
    return out


# ---------------------------------------------------------------- 渲染

def _select_for(qno, letters):
    opts = ''.join(f'<option value="{escape(k)}">{escape(k)}</option>' for k in letters)
    return Markup(f'<b class="gapno">{qno}</b><select class="pick" name="q_{qno}" data-q="{qno}">'
                  f'<option value="">選擇</option>{opts}</select>')


def _input_for(qno):
    return Markup(f'<b class="gapno">{qno}</b><input type="text" class="fill" data-q="{qno}" '
                  f'name="q_{qno}" placeholder="{qno}" autocomplete="off">')


def _gap_html(text, letters=None):
    """把 {3} 換成輸入框；有選項方框（摘要選詞）時換成下拉選單。"""
    def sub(m):
        qno = int(m.group(1))
        return _select_for(qno, letters) if letters else _input_for(qno)
    return Markup(GAP_RE.sub(lambda m: str(sub(m)), str(escape(text))))


def _render_group(g):
    out = dict(g)
    # 選項保留 JSON 裡的順序（段落標題用 i, ii, iii…，不能照字母排序）
    if g.get('options'):
        out['option_list'] = list(g['options'].items())
    if g['type'] == 'gapfill':
        letters = list(g['options']) if g.get('options') else None
        out['rows'] = [{'html': _gap_html(r['text'], letters)} for r in g.get('rows', [])]
        out['sections'] = [{'heading': s['heading'],
                            'lines': [_gap_html(ln, letters) for ln in s['lines']]}
                           for s in g.get('sections', [])]
    elif g['type'] in JUDGE_OPTIONS:
        out['choices'] = JUDGE_OPTIONS[g['type']]
    return out


# ---------------------------------------------------------------- 批改

def grade(key, given):
    """given 是 {題號(int): 學生作答}。回傳每題結果，依題號排序。"""
    keyed = answer_key(key)
    results = []
    for qno in sorted(keyed):
        ans = given.get(qno, '')
        results.append({
            'qno': qno,
            'given': str(ans or '').strip(),
            'is_correct': listening_bank.check_one(ans, keyed[qno]),
            'answer': ' / '.join(keyed[qno]),
        })
    return results
