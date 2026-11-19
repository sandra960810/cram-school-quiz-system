"""檢查韓檢模擬考題庫（topik_mock/TOPIK1.txt、TOPIK1-2.txt…、TOPIK2.txt…）：改完題目必跑，必過才能上線。

檢查：格式讀得進來、題數與配分比照正式 TOPIK（每一節 100 分）、每題四個選項而且剛好一個正解、
有中文解析、解析裡寫的「→ 2」和正解一致（「2 錯」不能是正解）、聽力每題有台詞、
寫作四題都有參考答案；每回之間題目不能重複（同一段文章、台詞、題幹或寫作題目出現在兩回就擋下）。
"""
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import topik_mock  # noqa: E402

# 正式 TOPIK 的科目、題數、滿分
SPEC = {1: [('listening', 30, 100), ('reading', 40, 100)],
        2: [('listening', 50, 100), ('writing', 4, 100), ('reading', 50, 100)]}
VOICES = ('n', 'f1', 'f2', 'm1', 'm2')

# 每回之間不能重複：文章與台詞的句子、題幹、選項組、寫作題目。指示語這類固定句型不算
seen = {}


def norm(text):
    text = re.sub(r'<[^>]+>', '', str(text))
    return re.sub(r'[\s.,!?、。…·"“”‘’()（）\[\]~]+', '', text)


def remember(kind, text, where, min_len):
    key = norm(text)
    if len(key) < min_len:
        return
    first = seen.setdefault((kind, key), where)
    if first.split(' ')[0] != where.split(' ')[0]:
        problems.append(f'{where}：和 {first} 重複（{kind}：{str(text)[:30]}）')


problems = []
jobs = [(no, rnd) for no in topik_mock.TESTS for rnd in topik_mock.rounds(no)]
for no in topik_mock.TESTS:
    if not topik_mock.rounds(no):
        problems.append(f'TOPIK {no}：沒有題庫')
for no, rnd in jobs:
    name = topik_mock.tid(no, rnd)
    try:
        test = topik_mock.load(no, rnd)
    except Exception as e:
        problems.append(f'{name}：讀不進來：{e}')
        continue
    if test.get('no') != no:
        problems.append(f'{name}：@test 的編號寫錯')
    if f'제{rnd}회' not in test.get('title', ''):
        problems.append(f'{name}：@test 的標題要寫「제{rnd}회」')
    got = [(s['key'], s['total'], s['full']) for s in test['sections']]
    if got != SPEC[no]:
        problems.append(f'{name}：科目／題數／配分是 {got}，正式考試是 {SPEC[no]}')
    answers = []
    for s in test['sections']:
        for g in s['groups']:
            for it in g['items']:
                if it['type'] == 'passage':
                    for line in it['lines']:
                        if isinstance(line, str):
                            for sent in re.split(r'(?<=[.?!])\s+|<br>', line):
                                remember('文章', sent, f"{name} {s['key']} {g['title'][:12]}", 14)
            for q in [it for it in g['items'] if it['type'] in ('q', 'w')]:
                where = f"{name} {s['key']} {q['n']} 번"
                if q['type'] == 'w':
                    for p in q['prompt']:
                        if isinstance(p, str):
                            remember('寫作題目', p, where, 14)
                    if not q['models']:
                        problems.append(f'{where}：寫作題沒有參考答案（A 行）')
                    if q['wtype'] == 'blanks' and not all(any(m.startswith(mark) for m in q['models'])
                                                          for mark in ('㉠', '㉡')):
                        problems.append(f'{where}：㉠、㉡ 都要有參考答案')
                    if not q['explain']:
                        problems.append(f'{where}：沒有中文說明')
                    continue
                answers.append(q['answer'])
                # 題幹是固定問法（…고르십시오）的不算；排列題、插入句題的選項本來就一樣，也不算
                if not (q['stem'].rstrip().endswith('고르십시오.') and '<br>' not in q['stem']):
                    remember('題幹', q['stem'], where, 22)
                if not all(re.fullmatch(r'[()가나다라\-㉠㉡㉢㉣\s]+', str(o)) for o in q['options']):
                    remember('選項', '|'.join(sorted(str(o) for o in q['options'])), where, 8)
                for c in q['cues']:
                    remember('台詞', c['t'], where, 14)
                if len(q['options']) != 4:
                    problems.append(f"{where}：選項要 4 個（現在 {len(q['options'])} 個）")
                if not 1 <= q['answer'] <= len(q['options']):
                    problems.append(f'{where}：沒有標正解（選項後面加 *）')
                if len({str(o) for o in q['options']}) != len(q['options']):
                    problems.append(f'{where}：選項重複')
                if not q['explain']:
                    problems.append(f'{where}：沒有中文解析')
                text = ' '.join(q['explain'])
                for m in re.finditer(r'→\s*([1-4])(?![0-9])', text):
                    if int(m.group(1)) != q['answer']:
                        problems.append(f"{where}：解析寫「→ {m.group(1)}」，但正解是 {q['answer']}")
                for m in re.finditer(r'（([1-4])(?:、([1-4]))?\s*(?:錯|是)', text):
                    for d in m.groups():
                        if d and int(d) == q['answer'] and '是對的' not in text[m.start():m.start() + 8]:
                            problems.append(f'{where}：解析說選項 {d} 錯，但它是正解')
                listen = g['kind'] == 'listen'
                needs_cues = listen and (not g['shared'] or q is g['items'][0] or
                                         q is next(it for it in g['items'] if it['type'] == 'q'))
                if needs_cues and not q['cues']:
                    problems.append(f'{where}：聽力題沒有台詞')
                if not listen and q['cues']:
                    problems.append(f'{where}：不是聽力題卻有台詞')
                for c in q['cues']:
                    if c['v'] not in VOICES:
                        problems.append(f"{where}：說話者代號 {c['v']} 不存在")
    spread = {i: answers.count(i) for i in (1, 2, 3, 4)}
    if answers and max(spread.values()) > len(answers) * 0.35:
        problems.append(f'{name}：正解位置太集中 {spread}')
    print(f"{name}：" + '、'.join(f"{s['name']} {s['total']} 題 {s['full']} 分" for s in test['sections'])
          + f"；正解分布 {spread}")

for p in problems:
    print('✗', p)
if problems:
    sys.exit(f'共 {len(problems)} 個問題')
print('✓ 韓檢模擬考題庫檢查通過')
