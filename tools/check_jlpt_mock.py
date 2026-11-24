"""檢查日檢模擬考題庫（jlpt_mock/N5.txt…）：改完題目必跑，必過才能上線。

檢查：格式讀得進來、每題都有正解與中文解析、選項數目（一般 4 個，即時応答 3 個）、
同一題選項不重複、聽解每題都有台詞、每一節的題數。
同一級每回之間不能重複：題幹、考的單字（畫底線的字）、選項組、文章句子、聽解台詞出現在兩回就擋下；
同一個題組的正解單字在別回出現過只提醒（最後印出數量，加 -v 看清單）。
"""
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import jlpt_mock  # noqa: E402

# 題目數：每一級每回都要一樣
SPEC = {5: [21, 22, 24], 4: [28, 29, 28], 3: [35, 39, 28], 2: [73, 32], 1: [70, 37]}

problems = []
seen = {}
notes = []


def norm(text):
    text = re.sub(r'\{([^{}|]+)\|[^{}|]+\}', r'\1', str(text))
    text = re.sub(r'<[^>]+>', '', text)
    return re.sub(r'[\s　、。，．・！？!?…「」『』（）()＿_~〜：:]+', '', text)


def remember(kind, text, where, min_len, hard=True):
    """同一級（where 開頭 N5、N5-2…的等級）不同回出現一樣的內容就記下來。"""
    key = norm(text)
    if len(key) < min_len:
        return
    test_name = where.split(' ')[0]
    first = seen.setdefault((test_name[:2], kind, key), where)
    if first.split(' ')[0] != test_name:
        msg = f'{where}：和 {first} 重複（{kind}：{str(text)[:30]}）'
        (problems if hard else notes).append(msg)


for level, rnd in [(lv, r) for lv in jlpt_mock.LEVELS for r in jlpt_mock.rounds(lv)]:
    name = jlpt_mock.tid(level, rnd)
    try:
        test = jlpt_mock.load(level, rnd)
    except Exception as e:
        problems.append(f'{name}：讀不進來：{e}')
        continue
    if not test:
        print(f'{name}：還沒有題庫')
        continue
    if test.get('level') != level:
        problems.append(f'{name}：@test 的等級寫錯')
    kinds = set()
    summary = []
    if [s['total'] for s in test['sections']] != SPEC[level]:
        problems.append(f"{name}：各科題數是 {[s['total'] for s in test['sections']]}，應該是 {SPEC[level]}")
    for s in test['sections']:
        summary.append(f"{s['name']} {s['total']} 題")
        for gi, g in enumerate(s['groups']):
            kinds.add(g['kind'])
            qs = [it for it in g['items'] if it['type'] == 'q']
            for it in g['items']:
                if it['type'] == 'passage':
                    for sent in re.split(r'[。！？]|<br>|</t[dh]>|</tr>', ' '.join(it['lines'])):
                        if not norm(sent).startswith('以下は'):  # 「以下は、留学生が書いた作文である」這類固定開頭不算
                            remember('文章', sent, f"{name} {s['key']} {g['title']}", 14)
            if not qs:
                problems.append(f"{name} {g['title']}：沒有題目")
            for q in qs:
                where = f"{name} {s['key']} {g['title']} {q['label']}"
                n = len(q['options'])
                if n not in (3, 4):
                    problems.append(f'{where}：選項要 3 或 4 個（現在 {n} 個）')
                if not 1 <= q['answer'] <= n:
                    problems.append(f'{where}：沒有標正解（選項後面加 *）')
                if len(set(q['options'])) != n:
                    problems.append(f'{where}：選項重複')
                if not q['explain']:
                    problems.append(f'{where}：沒有中文解析')
                if g['kind'] == 'listen' and not q['cues']:
                    problems.append(f'{where}：聽解題沒有台詞')
                if g['kind'] != 'listen' and q['cues']:
                    problems.append(f'{where}：不是聽解題卻有台詞')
                gkey = f"{s['key']}{gi}"
                # 読解的問法（筆者が最も言いたいことは何か）本來就固定，文章不同就好
                if g['kind'] != 'read' and not re.fullmatch(r'(<u>[^<]*</u>|[\s　])*', q['stem']):
                    remember('題幹', q['stem'], where, 8)
                marked = [m for m in re.findall(r'<u>([^<]*)</u>', q['stem']) if m.strip(' 　★')]
                if g['kind'] == 'lang' and len(marked) == 1 and len(norm(marked[0])) < len(norm(q['stem'])):
                    remember(f'考的字 {gkey}', marked[0], where, 1)
                remember('選項組', '／'.join(sorted(q['options'])), where, 14)
                if g['kind'] == 'lang' and 1 <= q['answer'] <= n:
                    remember(f'正解 {gkey}', q['options'][q['answer'] - 1], where, 2, hard=False)
                for c in q['cues']:
                    # 旁白的場面說明（会社で、女の人と男の人が…）是固定句型；発話表現的旁白就是題目，要比
                    if c['v'] != 'n' or len(q['cues']) == 1:
                        remember('台詞', c['t'], where, 14)
                for c in q['cues']:
                    if c['v'] not in ('n', 'f1', 'f2', 'm1', 'm2'):
                        problems.append(f"{where}：說話者代號 {c['v']} 不存在")
    if kinds != {'lang', 'read', 'listen'}:
        problems.append(f'{name}：要有言語知識、読解、聴解三種題組')
    # 正解位置不要太偏（四個選項大致平均）
    answers = [q['answer'] for s in test['sections'] for g in s['groups'] for q in g['items'] if q['type'] == 'q']
    spread = {i: answers.count(i) for i in (1, 2, 3, 4)}
    print(f"{name}：{'、'.join(summary)}；正解分布 {spread}")

if notes:
    print(f'（提醒）同一題組的正解在別回出現過 {len(notes)} 題' + ('' if '-v' in sys.argv else '，加 -v 看清單'))
    if '-v' in sys.argv:
        for x in notes:
            print('  ・', x)
for p in problems:
    print('✗', p)
if problems:
    sys.exit(f'共 {len(problems)} 個問題')
print('✓ 日檢模擬考題庫檢查通過')
