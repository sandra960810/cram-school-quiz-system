"""檢查聽力題庫的一致性。

這支腳本在產生音檔之前跑，用來確保「音檔與題目完全匹配」：
每一題的答案都必須真的出現在同一個 Part 的逐字稿裡，題號不能漏也不能重複。

用法：python tools/check_listening.py          檢查全部
      python tools/check_listening.py L01      只檢查某一回
"""
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
BANK = ROOT / 'listening'
# 題號在題組裡的寫法：{3} 或 {ex:Fraser}
GAP_RE = re.compile(r'\{(\d+)\}')
LETTER_ONLY = re.compile(r'^[A-H]$')


def transcript_of(part):
    """把 Part 的逐字稿串成一段純文字（略過停頓）。"""
    return ' '.join(c['t'] for c in part['cues'] if c['v'] != 'pause')


def normalise(s):
    return re.sub(r'[^a-z0-9]+', ' ', s.lower()).strip()


SPELLED = {
    '0': 'zero', '1': 'one', '2': 'two', '3': 'three', '4': 'four', '5': 'five',
    '6': 'six', '7': 'seven', '8': 'eight', '9': 'nine', '10': 'ten',
    '14': 'fourteenth', '15': 'fifteen', '20': 'twenty', '60': 'sixty',
    '850': 'eight hundred and fifty',
}


def answer_in_transcript(ans, text):
    """答案是否能在逐字稿中找到（數字允許以英文拼字出現）。"""
    t = normalise(text)
    a = normalise(ans)
    if a and a in t:
        return True
    if a in SPELLED and normalise(SPELLED[a]) in t:
        return True
    return False


def check_part(test_key, part, problems):
    where = f'{test_key} Part {part["no"]}'
    text = transcript_of(part)

    # 題組中宣告的題號
    declared = []
    for g in part['groups']:
        if g['type'] == 'gapfill':
            blocks = g.get('rows', [])
            for sec in g.get('sections', []):
                blocks += [{'text': ln} for ln in sec['lines']]
            for row in blocks:
                declared += [int(n) for n in GAP_RE.findall(row.get('text', ''))]
        elif g['type'] in ('mcq', 'matching', 'map'):
            declared += [it['no'] for it in g['items']]

    answered = [q['no'] for q in part['questions']]

    if sorted(declared) != sorted(answered):
        problems.append(f'{where}: 題組題號 {sorted(declared)} 與答案題號 {sorted(answered)} 不一致')
    if len(set(answered)) != len(answered):
        problems.append(f'{where}: 答案區有重複題號')

    # 選項字母必須真的存在於該題組
    letter_sets = {}
    for g in part['groups']:
        if g['type'] == 'mcq':
            for it in g['items']:
                letter_sets[it['no']] = set(it['options'])
        elif g['type'] in ('matching', 'map'):
            # matching 的 options 是 {字母: 說明}，map 的 options 是字母清單
            for it in g['items']:
                letter_sets[it['no']] = set(g['options'])

    for q in part['questions']:
        if not q.get('answers'):
            problems.append(f'{where} Q{q["no"]}: 沒有答案')
            continue
        if not q.get('explain'):
            problems.append(f'{where} Q{q["no"]}: 沒有解析')

        first = q['answers'][0]
        if LETTER_ONLY.match(first):
            valid = letter_sets.get(q['no'])
            if valid is None:
                problems.append(f'{where} Q{q["no"]}: 答案是字母但題組不是選擇/配對題')
            elif first not in valid:
                problems.append(f'{where} Q{q["no"]}: 答案 {first} 不在選項 {sorted(valid)} 中')
            # 字母題改以 quote 驗證內容確實在逐字稿
            if q.get('quote') and not answer_in_transcript(q['quote'][:40], text):
                problems.append(f'{where} Q{q["no"]}: 解析引用的句子不在逐字稿中')
        else:
            if not any(answer_in_transcript(a, text) for a in q['answers']):
                problems.append(f'{where} Q{q["no"]}: 答案 {q["answers"]} 在逐字稿中找不到')


def check_test(test_dir, problems):
    key = test_dir.name
    nos = []
    for pf in sorted(test_dir.glob('part*.json')):
        part = json.loads(pf.read_text(encoding='utf-8'))
        check_part(key, part, problems)
        nos += [q['no'] for q in part['questions']]
    if sorted(nos) != list(range(1, 41)):
        missing = sorted(set(range(1, 41)) - set(nos))
        extra = sorted(set(nos) - set(range(1, 41)))
        problems.append(f'{key}: 題號不是完整的 1–40（缺 {missing}，多 {extra}）')
    return len(nos)


def main():
    only = sys.argv[1] if len(sys.argv) > 1 else None
    problems = []
    total = 0
    dirs = sorted(d for d in BANK.iterdir() if d.is_dir() and (only is None or d.name == only))
    if not dirs:
        print('找不到任何題庫資料夾')
        return 1
    for d in dirs:
        total += check_test(d, problems)

    if problems:
        print(f'發現 {len(problems)} 個問題：')
        for p in problems:
            print('  ✗', p)
        return 1
    print(f'✅ 檢查通過：{len(dirs)} 回、共 {total} 題，答案全部可在逐字稿中找到')
    return 0


if __name__ == '__main__':
    sys.exit(main())
