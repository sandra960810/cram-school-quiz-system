"""檢查雅思模擬考（聽說讀寫）各回之間有沒有重複的內容：出新的一回後必跑，必過才能上線。

比對範圍（同一回裡面重複不算，例如 Part 1 範例對話本來就會唸兩次）：
- 主題：tests.json 的 topics（聽力、閱讀、寫作、口說各自拆開比對，聽力和閱讀之間也互相比）
- 聽力：逐字稿句子、題幹、選項組、填空的句子、地圖題標的地點組
- 閱讀：文章標題、文章句子、題幹、選項組、填空的句子、段落標題清單
- 寫作：Task 1 題目與圖表標題、Task 2 題目（字詞重疊太高也算重複）
- 口說：Part 1 話題（第一個住所／工作學業話題除外）與每一題、Part 2 題卡、Part 3 議題與每一題
- 聽力與閱讀之間的句子也互相比，避免同一段文字出現在兩個技能

短句（例如 "Thank you."、考試固定指示語）不算。
用法：python tools/check_ielts_unique.py
"""
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
problems = []
seen = {}

# 考試固定句型：旁白、題型指示，各回本來就一樣
FIXED = re.compile(
    r'^(part \d|you will hear|first you have|now listen|before you hear|that is the end|'
    r'you will see that|you should answer|listen carefully|on this occasion only|'
    r'the customer s (sur)?name is)')


def norm(text):
    text = re.sub(r'<[^>]+>', ' ', str(text)).lower()
    text = re.sub(r'\{[^}]*\}', ' ', text)          # 填空格 {3}
    return re.sub(r'[^a-z0-9]+', ' ', text).strip()


def sentences(text):
    return [s for s in re.split(r'(?<=[.!?;:])\s+', str(text)) if s.strip()]


def remember(kind, text, where, min_words=0, test_key=None):
    """記下一段內容；若別回已經出現過一樣的就記為問題。"""
    key = norm(text)
    if not key or len(key.split()) < min_words or FIXED.match(key):
        return
    tk = test_key or where.split(' ')[0]
    first = seen.setdefault((kind, key), (tk, where))
    if first[0] != tk:
        problems.append(f'{where}：和 {first[1]} 重複（{kind}：{str(text)[:60]}）')


def words(text):
    stop = {'the', 'a', 'an', 'of', 'in', 'to', 'and', 'or', 'is', 'are', 'that', 'for', 'some',
            'people', 'this', 'what', 'do', 'you', 'your', 'one', 'below', 'shows', 'chart',
            'graph', 'country', 'between', 'by', 'on', 'with', 'than', 'their', 'more', 'many',
            'think', 'should', 'be', 'other', 'others', 'while', 'own', 'give', 'opinion'}
    return {w for w in norm(text).split() if w not in stop and len(w) > 2}


def load(path):
    return json.loads(path.read_text(encoding='utf-8'))


def catalog(section):
    return load(ROOT / section / 'tests.json')


def topics_of(entry):
    raw = re.sub(r'(Task \d|Part \d)\s*', '', entry.get('topics', ''))
    return [t.strip() for t in re.split(r'[・｜|、]', raw) if t.strip()]


# ---------- 主題 ----------
for section in ('listening', 'reading'):
    for e in catalog(section):
        for t in topics_of(e):
            remember('聽讀主題', t, f'{e["key"]} 主題')
for section in ('writing', 'speaking'):
    for e in catalog(section):
        for t in topics_of(e):
            remember(f'{section} 主題', t, f'{e["key"]} 主題')


def check_groups(key, where, groups):
    for g in groups:
        for it in g.get('items', []):
            if it.get('stem'):
                remember('題幹', it['stem'], f'{where} Q{it["no"]}', 4, key)
            text = it.get('text', '')
            if text and not re.match(r'^Paragraph [A-H]$', text):
                remember('題目敘述', text, f'{where} Q{it["no"]}', 5, key)
            if isinstance(it.get('options'), dict):
                opts = ' | '.join(sorted(norm(v) for v in it['options'].values()))
                remember('選項組', opts, f'{where} Q{it["no"]}', 0, key)
                for v in it['options'].values():
                    remember('選項', v, f'{where} Q{it["no"]}', 6, key)
        if g['type'] == 'map':
            places = ' | '.join(sorted(norm(it['text']) for it in g['items']))
            remember('地圖地點組', places, f'{where} 地圖', 0, key)
        if isinstance(g.get('options'), dict) and g['type'] != 'matching' or g['type'] == 'headings':
            for v in g['options'].values():
                remember('選項', v, f'{where} {g["range"]}', 5, key)
        if g['type'] == 'matching' and isinstance(g.get('options'), dict):
            vals = [v for v in g['options'].values() if not re.match(r'^Paragraph [A-H]$', v)]
            for v in vals:
                remember('選項', v, f'{where} {g["range"]}', 5, key)
        lines = [r.get('text', '') for r in g.get('rows', [])]
        for sec in g.get('sections', []):
            lines += sec.get('lines', [])
        for ln in lines:
            for s in sentences(ln):
                remember('填空句', s, f'{where} {g["range"]}', 5, key)
        if g.get('title'):
            remember('題組標題', g['title'], f'{where} {g["range"]}', 3, key)


# ---------- 聽力 ----------
for e in catalog('listening'):
    key = e['key']
    for pf in sorted((ROOT / 'listening' / key).glob('part*.json')):
        part = load(pf)
        where = f'{key} Part {part["no"]}'
        for c in part['cues']:
            if c['v'] in ('pause', 'narrator'):
                continue
            for s in sentences(c['t']):
                remember('句子', s, where, 7, key)
        check_groups(key, where, part['groups'])

# ---------- 閱讀 ----------
for e in catalog('reading'):
    key = e['key']
    for pf in sorted((ROOT / 'reading' / key).glob('passage*.json')):
        p = load(pf)
        where = f'{key} Passage {p["no"]}'
        remember('文章標題', p['title'], where, 0, key)
        for para in p['paragraphs']:
            for s in sentences(para['text']):
                remember('句子', s, where, 7, key)
        check_groups(key, where, p['groups'])

# ---------- 寫作 ----------
prompts = []
for e in catalog('writing'):
    key = e['key']
    for n in (1, 2):
        task = load(ROOT / 'writing' / key / f'task{n}.json')
        where = f'{key} Task {n}'
        remember('寫作題目', task['prompt'], where, 0, key)
        if task.get('chart'):
            remember('圖表標題', task['chart']['title'], where, 0, key)
        prompts.append((key, where, words(task['prompt'])))
for i, (k1, w1, s1) in enumerate(prompts):
    for k2, w2, s2 in prompts[i + 1:]:
        if k1 != k2 and s1 and s2:
            overlap = len(s1 & s2) / min(len(s1), len(s2))
            if overlap >= 0.6:
                problems.append(f'{w2}：和 {w1} 題目太像（關鍵字重疊 {overlap:.0%}）')

# ---------- 口說 ----------
for e in catalog('speaking'):
    key = e['key']
    t = load(ROOT / 'speaking' / key / 'test.json')
    for i, topic in enumerate(t['part1']):
        where = f'{key} Part 1「{topic["topic"]}」'
        if i > 0:
            remember('口說話題', topic['topic'], where, 0, key)
        for q in topic['questions']:
            remember('口說題目', q, where, 0, key)
    p2 = t['part2']
    remember('Part 2 題卡', p2['cue'], f'{key} Part 2', 0, key)
    remember('Part 2 話題', p2['topic'], f'{key} Part 2', 0, key)
    for q in p2.get('followups', []):
        remember('口說題目', q, f'{key} Part 2', 0, key)
    for th in t['part3']:
        where = f'{key} Part 3「{th["theme"]}」'
        remember('Part 3 議題', th['theme'], where, 0, key)
        for q in th['questions']:
            remember('口說題目', q, where, 0, key)

if problems:
    print(f'發現 {len(problems)} 個重複：')
    for p in problems:
        print('  ✗', p)
    sys.exit(1)
counts = {s: len(catalog(s)) for s in ('listening', 'reading', 'writing', 'speaking')}
print('✅ 各回內容沒有重複：聽力 {listening} 回、閱讀 {reading} 回、寫作 {writing} 回、口說 {speaking} 回'
      .format(**counts))
