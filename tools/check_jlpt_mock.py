"""檢查日檢模擬考題庫（jlpt_mock/N5.txt…）：改完題目必跑，必過才能上線。

檢查：格式讀得進來、每題都有正解與中文解析、選項數目（一般 4 個，即時応答 3 個）、
同一題選項不重複、聽解每題都有台詞、每一節的題數。
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import jlpt_mock  # noqa: E402

problems = []
for level in jlpt_mock.LEVELS:
    try:
        test = jlpt_mock.load(level)
    except Exception as e:
        problems.append(f'N{level}：讀不進來：{e}')
        continue
    if not test:
        print(f'N{level}：還沒有題庫')
        continue
    if test.get('level') != level:
        problems.append(f'N{level}：@test 的等級寫錯')
    kinds = set()
    summary = []
    for s in test['sections']:
        summary.append(f"{s['name']} {s['total']} 題")
        for g in s['groups']:
            kinds.add(g['kind'])
            qs = [it for it in g['items'] if it['type'] == 'q']
            if not qs:
                problems.append(f"N{level} {g['title']}：沒有題目")
            for q in qs:
                where = f"N{level} {s['key']} {g['title']} 第 {q['ban']} 題"
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
                for c in q['cues']:
                    if c['v'] not in ('n', 'f1', 'f2', 'm1', 'm2'):
                        problems.append(f"{where}：說話者代號 {c['v']} 不存在")
    if kinds != {'lang', 'read', 'listen'}:
        problems.append(f'N{level}：要有言語知識、読解、聴解三種題組')
    # 正解位置不要太偏（四個選項大致平均）
    answers = [q['answer'] for s in test['sections'] for g in s['groups'] for q in g['items'] if q['type'] == 'q']
    spread = {i: answers.count(i) for i in (1, 2, 3, 4)}
    print(f"N{level}：{'、'.join(summary)}；正解分布 {spread}")

for p in problems:
    print('✗', p)
if problems:
    sys.exit(f'共 {len(problems)} 個問題')
print('✓ 日檢模擬考題庫檢查通過')
