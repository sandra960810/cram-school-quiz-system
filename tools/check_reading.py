"""檢查閱讀題庫的一致性。

改完閱讀題目一定要跑，確保：
- 每一回題號 1–40 完整、不重複，題組與答案一一對應
- 每題的原文引句（quote）真的出現在同一篇文章裡
- 填空題的答案能在文章中逐字找到；選擇類題目的答案是有效選項

用法：python tools/check_reading.py          檢查全部
      python tools/check_reading.py R01      只檢查某一回
"""
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
BANK = ROOT / 'reading'
GAP_RE = re.compile(r'\{(\d+)\}')
JUDGE = {'tfng': {'TRUE', 'FALSE', 'NOT GIVEN'}, 'ynng': {'YES', 'NO', 'NOT GIVEN'}}


def normalise(s):
    return re.sub(r'[^a-z0-9]+', ' ', s.lower()).strip()


def check_passage(key, p, problems):
    where = f'{key} Passage {p["no"]}'
    text = ' '.join(para['text'] for para in p['paragraphs'])
    answers = {q['no']: q for q in p['questions']}
    valid = {}   # 題號 -> 允許的選項（None 表示自由填寫）

    for g in p['groups']:
        t = g['type']
        if t == 'gapfill':
            blob = json.dumps(g.get('rows', []) + g.get('sections', []), ensure_ascii=False)
            for n in GAP_RE.findall(blob):
                valid[int(n)] = set(g['options']) if g.get('options') else None
        elif t in JUDGE:
            for it in g['items']:
                valid[it['no']] = JUDGE[t]
        elif t == 'mcq':
            for it in g['items']:
                valid[it['no']] = set(it['options'])
        elif t in ('matching', 'headings'):
            for it in g['items']:
                valid[it['no']] = set(g['options'])
        else:
            problems.append(f'{where}：不認得的題型 {t}')

    if set(valid) != set(answers):
        problems.append(f'{where}：題組題號 {sorted(valid)} 與答案題號 {sorted(answers)} 不一致')

    for no, q in answers.items():
        if not q.get('answers'):
            problems.append(f'{where} 第 {no} 題：沒有答案')
            continue
        if q.get('quote') and normalise(q['quote']) not in normalise(text):
            problems.append(f'{where} 第 {no} 題：原文引句在文章中找不到')
        if not q.get('explain'):
            problems.append(f'{where} 第 {no} 題：沒有解析')
        allowed = valid.get(no)
        for i, a in enumerate(q['answers']):
            if allowed is None:
                # 第一個答案必須逐字出自文章；後面的是可接受的其他寫法
                # （例如美式拼法 summarize），不要求出現在文章裡
                if i == 0 and normalise(a) not in normalise(text):
                    problems.append(f'{where} 第 {no} 題：答案「{a}」在文章中找不到')
            elif a not in allowed:
                problems.append(f'{where} 第 {no} 題：答案「{a}」不是有效選項')
    return sorted(answers)


def check_test(key, problems):
    d = BANK / key
    files = sorted(d.glob('passage*.json'))
    if not files:
        problems.append(f'{key}：沒有任何 passage 檔')
        return 0
    nums = []
    for f in files:
        p = json.loads(f.read_text(encoding='utf-8'))
        nums += check_passage(key, p, problems)
    if sorted(nums) != list(range(1, 41)):
        problems.append(f'{key}：題號應為 1–40，實際是 {sorted(nums)}')
    return len(nums)


def main():
    tests = json.loads((BANK / 'tests.json').read_text(encoding='utf-8'))
    keys = [t['key'] for t in tests]
    if len(sys.argv) > 1:
        keys = [k for k in keys if k in sys.argv[1:]]
    problems, total = [], 0
    for k in keys:
        total += check_test(k, problems)
    if problems:
        print('❌ 發現問題：')
        for p in problems:
            print('  -', p)
        sys.exit(1)
    print(f'✅ 檢查通過：{len(keys)} 回、共 {total} 題，引句與填空答案都能在文章中找到')


if __name__ == '__main__':
    main()
