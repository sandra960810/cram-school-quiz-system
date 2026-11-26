"""檢查字根字首資料 morphology/roots.txt：格式、拼法、同一組有沒有重複的字、「單字=原本的字」的寫法。改完資料必跑。

    python tools/check_word_roots.py
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import word_roots  # noqa: E402

errors = []
with open(word_roots.DATA_FILE, encoding='utf-8') as f:
    for n, line in enumerate(f, 1):
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        parts = line.split('|')
        if len(parts) != 4:
            errors.append(f'第 {n} 行：要有 4 欄（種類|字形|意思|單字），現在是 {len(parts)} 欄')
            continue
        kind, form, meaning, words = parts
        if kind not in word_roots.KIND_NAMES:
            errors.append(f'第 {n} 行：種類「{kind}」不對，只能是 prefix、root、suffix')
        if not meaning.strip():
            errors.append(f'第 {n} 行：{form} 沒有寫意思')
        toks = words.split()
        ws = [t.split('=')[0] for t in toks]   # 「happiness=happy」：等號後面是去掉字尾後的字
        bad_stem = [t for t in toks if t.count('=') > 1 or (t.count('=') == 1 and not re.fullmatch(r"[a-z][a-z\-]*", t.split('=')[1]))]
        if bad_stem:
            errors.append(f'第 {n} 行：{form} 的「單字=原本的字」寫法不對：{" ".join(bad_stem)}')
        if len(ws) < 2:
            errors.append(f'第 {n} 行：{form} 至少要有 2 個字')
        bad = [w for w in ws if not re.fullmatch(r"[a-z][a-z\-]*", w)]
        if bad:
            errors.append(f'第 {n} 行：{form} 有拼法怪怪的字：{" ".join(bad)}')
        dup = sorted({w for w in ws if ws.count(w) > 1})
        if dup:
            errors.append(f'第 {n} 行：{form} 重複列了：{" ".join(dup)}')

print(f'共 {len(word_roots.FAMILIES)} 組（字首 {sum(f["kind"] == "prefix" for f in word_roots.FAMILIES)}、'
      f'字根 {sum(f["kind"] == "root" for f in word_roots.FAMILIES)}、字尾 {sum(f["kind"] == "suffix" for f in word_roots.FAMILIES)}），'
      f'{len(word_roots.FAMILIES_OF_WORD)} 個不同的字')
if errors:
    print('\n'.join(errors))
    sys.exit(1)
print('✓ 檢查通過')
