"""產生單字的 KK 音標、發音音節與拼字音節：pronunciation/kk.json。

用法（在專案資料夾執行，cmudict.dict 要先下載）：
    python tools/make_pronunciation.py 路徑/cmudict.dict

- 音標來源：CMU Pronouncing Dictionary（美式發音，BSD 授權），ARPAbet 轉成台灣常用的 KK 音標
- 音節：依 CMU 的母音切音節，子音照「最大字首」原則分給後一個音節（例如 ba·nan·a → bə·ˈnæ·nə）
- 拼字音節：先用 pyphen（LibreOffice 斷字字典），音節數和發音對不上時改用簡單的拼字規則；
  還是對不上就不拆（前端只顯示整個字）
- 收錄 basic/basic_vocab.csv 與 general/general_vocab.csv 裡的字；字典查不到的字不放
"""
import csv
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSVS = ['basic/basic_vocab.csv', 'general/general_vocab.csv']
OUT = os.path.join(ROOT, 'pronunciation', 'kk.json')

VOWELS = {'AA': 'ɑ', 'AE': 'æ', 'AH': 'ʌ', 'AO': 'ɔ', 'AW': 'aʊ', 'AY': 'aɪ', 'EH': 'ɛ', 'ER': 'ɝ',
          'EY': 'e', 'IH': 'ɪ', 'IY': 'i', 'OW': 'o', 'OY': 'ɔɪ', 'UH': 'ʊ', 'UW': 'u'}
CONS = {'B': 'b', 'CH': 'tʃ', 'D': 'd', 'DH': 'ð', 'F': 'f', 'G': 'g', 'HH': 'h', 'JH': 'dʒ', 'K': 'k',
        'L': 'l', 'M': 'm', 'N': 'n', 'NG': 'ŋ', 'P': 'p', 'R': 'r', 'S': 's', 'SH': 'ʃ', 'T': 't',
        'TH': 'θ', 'V': 'v', 'W': 'w', 'Y': 'j', 'Z': 'z', 'ZH': 'ʒ'}
# 英文字首可以出現的子音組合（切音節時，子音盡量分給後面的音節，但要是合法字首）
ONSETS = {(c,) for c in 'P B T D K G F V TH DH S Z SH ZH HH CH JH M N L R W Y'.split()} | {tuple(o.split()) for o in '''
P L|P R|P Y|B L|B R|B Y|T R|T W|D R|D W|K L|K R|K W|K Y|G L|G R|G W|F L|F R|F Y|TH R|SH R|M Y|N Y|V Y|HH Y
S P|S T|S K|S M|S N|S L|S W|S F|S P L|S P R|S T R|S K R|S K W|S K Y|S P Y|S M Y
'''.replace('|', '\n').split('\n') if o.strip()}


def kk_of(phones):
    """['B','AH0','N','AE1','N','AH0'] → 音節列表 [('b','ə',0), ...]，回傳 (音節字串列表, 重音列表)。"""
    # 先找出每個母音的位置
    vidx = [i for i, p in enumerate(phones) if p[-1].isdigit()]
    if not vidx:
        return None
    bounds = [0]
    for a, b in zip(vidx, vidx[1:]):
        cons = phones[a + 1:b]
        # 最大字首：從最長的合法字首開始找
        split = len(cons)
        for k in range(len(cons), -1, -1):
            if k == 0 or tuple(cons[len(cons) - k:]) in ONSETS:
                split = len(cons) - k
                break
        bounds.append(a + 1 + split)
    bounds.append(len(phones))
    sylls, stress = [], []
    for s, e in zip(bounds, bounds[1:]):
        out, st = '', 0
        for p in phones[s:e]:
            if p[-1].isdigit():
                base, st = p[:-1], int(p[-1])
                if base == 'AH' and st == 0:
                    out += 'ə'
                elif base == 'ER' and st == 0:
                    out += 'ɚ'
                else:
                    out += VOWELS[base]
            else:
                out += CONS[p]
        sylls.append(out)
        stress.append(st)
    return sylls, stress


def kk_string(sylls, stress):
    if len(sylls) == 1:
        return sylls[0]
    return ''.join(('ˈ' if st == 1 else 'ˌ' if st == 2 else '') + s for s, st in zip(sylls, stress))


DIGRAPHS = ['tch', 'sh', 'ch', 'th', 'wh', 'ph', 'ck', 'ng', 'qu']


def rule_split(word):
    """簡單的拼字音節規則：母音群之間的子音，一個給後面（ti·ger），兩個以上前後各分（rab·bit），雙字母音不拆。"""
    w = word.lower()
    if not re.fullmatch(r'[a-z]+', w):
        return None
    # 標出母音群（y 在字首當子音），字尾不發音的 e 不算
    vow = [c in 'aeiou' or (c == 'y' and i > 0) for i, c in enumerate(w)]
    if len(w) > 2 and w.endswith('e') and not w.endswith(('le', 'ee', 'ye')) and vow[-2] is False:
        vow[-1] = False
    groups, i = [], 0
    while i < len(w):
        if vow[i]:
            j = i
            while j < len(w) and vow[j]:
                j += 1
            groups.append((i, j))
            i = j
        else:
            i += 1
    if not groups:
        return None
    cuts = []
    for (a, b), (c, d) in zip(groups, groups[1:]):
        mid = w[b:c]
        if len(mid) == 0:
            cuts.append(b)                      # 兩個母音群緊接（少見）
        elif len(mid) == 1:
            cuts.append(b)                      # V·CV
        else:
            k = b + 1
            for dg in DIGRAPHS:                 # 雙字母子音不拆
                if mid.startswith(dg):
                    k = b + len(dg)
                    break
                if mid.endswith(dg) and len(mid) > len(dg):
                    k = c - len(dg)
                    break
            if mid.endswith('le') is False and w[c - 1:c + 2] == 'le' and c + 2 == len(w):
                k = c - 1
            cuts.append(k)
    parts, s = [], 0
    for k in cuts:
        parts.append(word[s:k])
        s = k
    parts.append(word[s:])
    return [p for p in parts if p]


def spell_split(word, n, hy):
    if n <= 1:
        return [word]
    if hy:
        p = hy.inserted(word).split('-')
        if len(p) == n:
            return p
    p = rule_split(word)
    if p and len(p) == n:
        return p
    return None


# 英式拼法（字典是美式）
BRITISH = {'jewellery': 'jewelry', 'offence': 'offense', 'aunty': 'auntie'}
# 字典沒有、也拆不出來的常用字：自己補（ARPAbet）
EXTRA = {'smoothie': 'S M UW1 DH IY0', 'sharpener': 'SH AA1 R P AH0 N ER0', 'hoodie': 'HH UH1 D IY0',
         'shush': 'SH AH1 SH'}


def lookup(cmu, key):
    """回傳「每個組成字的音素」列表：一般字只有一段；複合字（toothache = tooth + ache）分段，
    各段自己切音節，子音不會跨字（tooth·ache，不是 too·thache）。
    查不到時也試英式拼法改美式、-ise 改 -ize。"""
    if key in EXTRA:
        return [EXTRA[key].split()]
    if key in cmu:
        return [cmu[key]]
    for k in (BRITISH.get(key), re.sub(r'is(e|ation|ing|ed)$', r'iz\1', key)):
        if k and k in cmu:
            return [cmu[k]]
    if ' ' in key:
        return None
    for i in range(3, len(key) - 2):
        a, b = key[:i], key[i:]
        if a in cmu and b in cmu:
            # 複合字：第二個字的主重音降為次重音
            return [cmu[a], [x[:-1] + '2' if x.endswith('1') else x for x in cmu[b]]]
    return None


def main(cmu_path):
    try:
        import pyphen
        hy = pyphen.Pyphen(lang='en_US')
    except ImportError:
        hy = None
    cmu = {}
    with open(cmu_path, encoding='utf-8') as f:
        for line in f:
            line = line.split('#')[0].strip()
            if not line:
                continue
            head, *ph = line.split()
            if '(' in head:                      # 只取第一個（最常見的）唸法
                continue
            cmu[head.lower()] = ph
    out, missing = {}, []
    for path in CSVS:
        with open(os.path.join(ROOT, path), encoding='utf-8-sig', newline='') as f:
            for row in list(csv.reader(f))[1:]:
                word = row[3].strip()
                key = word.lower()
                if key in out:
                    continue
                ph = lookup(cmu, key)
                if not ph:
                    missing.append(word)
                    continue
                sylls, stress = [], []
                for part in ph:
                    r = kk_of(part)
                    if not r:
                        break
                    sylls += r[0]
                    stress += r[1]
                if not sylls:
                    missing.append(word)
                    continue
                item = {"kk": kk_string(sylls, stress), "syl": sylls, "stress": stress}
                sp = spell_split(word, len(sylls), hy)
                if sp:
                    item["spell"] = sp
                out[key] = item
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, separators=(',', ':'), sort_keys=True)
    print(f'寫入 {len(out)} 個字的音標；字典查不到 {len(missing)} 個：{" ".join(missing[:80])}')


if __name__ == '__main__':
    if len(sys.argv) < 2:
        sys.exit('用法：python tools/make_pronunciation.py 路徑/cmudict.dict')
    main(sys.argv[1])
