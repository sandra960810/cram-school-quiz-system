"""日檢單字原稿（word|reading|pos|meaning|sentence|sentence_zh）→ 檢查＋自動標例句填空 [寫法|讀音]。
用法：python build.py data/n5_*.txt  → 印出問題，產生 out/<level>.tsv"""
import sys, re, glob, json, os
import fugashi, opencc
T = fugashi.Tagger()
CC = opencc.OpenCC('s2tw')
import sqlite3
JM = sqlite3.connect('/tmp/claude-0/jl/jamdict.db')
def in_jmdict(word, r):
    if JM.execute('select 1 from Kanji k join Kana n on n.idseq=k.idseq where k.text=? and n.text=? limit 1', (word, r)).fetchone(): return True
    return False
KANA = re.compile(r'^[ぁ-ゖァ-ヺー・／〜～]+$')
def hira(s): return ''.join(chr(ord(c) - 0x60) if 'ァ' <= c <= 'ヶ' else c for c in s)
def kata(s): return ''.join(chr(ord(c) + 0x60) if 'ぁ' <= c <= 'ゖ' else c for c in s)
def is_kata_word(w): return all('ァ' <= c <= 'ヺ' or c == 'ー' for c in w)
def tok_kana(t):
    k = t.feature.kana
    return k if k and k != '*' else t.surface
def feat(t, name):
    v = getattr(t.feature, name, None)
    return v if v and v != '*' else ''
AUX_OK = {'助動詞'}
def chunk_after(toks, j):
    """動詞、形容詞後面接的助動詞（ます、た、ない…）與 て／で 一起挖掉，答案才是完整的一段。"""
    k = j + 1
    while k < len(toks):
        p = toks[k].pos.split(',')
        if (p[0] == '助動詞' and toks[k].surface not in ('です', 'だ', 'でしょう', 'だろう', 'でし', 'だっ')) or (p[0] == '助詞' and p[1] == '接続助詞' and toks[k].surface in ('て', 'で')):
            k += 1
        else:
            break
    return k
def find_cloze(word, reading, sentence):
    readings = reading.split('／')
    toks = list(T(sentence))
    # 位置表
    pos = []; i = 0
    for t in toks:
        i = sentence.index(t.surface, i); pos.append(i); i += len(t.surface)
    # 1) 動詞、形容詞：用辭書形比對（lemma／orthBase／kanaBase）
    wk = {kata(r) for r in readings}
    for j, t in enumerate(toks):
        p = t.pos.split(',')[0]
        if p not in ('動詞', '形容詞', '形状詞', '副詞', '名詞', '代名詞', '連体詞', '感動詞', '接続詞'):
            continue
        base = {feat(t, 'orthBase'), feat(t, 'lemma').split('-')[0]}
        kbase = {feat(t, 'kanaBase'), feat(t, 'lForm')}
        if word in base or (wk & kbase and (any(c in word for c in t.surface) or KANA.match(word))):
            if p in ('動詞', '形容詞'):
                k = chunk_after(toks, j)
            else:
                k = j + 1
            s, e = pos[j], pos[k - 1] + len(toks[k - 1].surface)
            form = sentence[s:e]
            rd = ''.join(tok_kana(x) for x in toks[j:k])
            stem = word.rstrip('ぁ-ゖ'.join('') ) if False else re.sub(r'[ぁ-ゖ]+$', '', word)
            if stem and stem != word and form.startswith(stem) and not KANA.match(stem):
                tail = word[len(stem):]
                alts = []
                for r in readings:
                    if r.endswith(tail):
                        alts.append(r[:len(r) - len(tail)] + form[len(stem):])
                if alts:
                    rd = '／'.join(dict.fromkeys(alts))
            elif form == word and '／' not in reading:
                rd = reading
            elif form == word and hira(rd) not in reading.split('／'):
                return 'MULTI'
            return s, e, form, rd
    # 2) 名詞等：原字直接出現在句子裡
    idx = sentence.find(word)
    if idx >= 0:
        if '／' in reading:
            return 'MULTI'
        return idx, idx + len(word), word, reading
    return None
def check_reading(word, reading):
    if KANA.match(word): return True
    if all(in_jmdict(word, r) for r in reading.split('／')): return True
    got = hira(''.join(tok_kana(t) for t in T(word)))
    return any(hira(r) == got for r in reading.split('／'))
def main(files):
    rows, problems, seen = [], [], {}
    for f in files:
        lv = re.search(r'n(\d)', os.path.basename(f)).group(1)
        for ln, line in enumerate(open(f, encoding='utf-8'), 1):
            line = line.rstrip('\n')
            if not line.strip() or line.startswith('#'): continue
            parts = line.split('|')
            tag = f'{os.path.basename(f)}:{ln} {parts[0]}'
            if len(parts) != 6:
                problems.append(f'{tag} 欄位數 {len(parts)}'); continue
            word, reading, pos, meaning, sent, sent_zh = [p.strip() for p in parts]
            if word in seen: problems.append(f'{tag} 重複（{seen[word]}）')
            seen[word] = tag
            if not KANA.match(reading): problems.append(f'{tag} 讀音不是假名：{reading}')
            if not check_reading(word, reading): problems.append(f'{tag} 讀音待查：{reading}（字典：{hira("".join(tok_kana(t) for t in T(word)))}）')
            for fld in (meaning, sent_zh):
                if CC.convert(fld).replace('臺', '台') != fld: problems.append(f'{tag} 可能有簡體或非台灣用語：{fld} → {CC.convert(fld)}')
            if not sent.endswith(('。', '？', '！', '」', '?', '!')) : problems.append(f'{tag} 例句結尾沒有句號：{sent}')
            if '[' in sent:
                out = sent.replace('=', '|')
                if not re.search(r'\[[^\[\]]+\]', out): problems.append(f'{tag} 手動標記格式不對：{sent}')
            else:
                c = find_cloze(word, reading, sent)
                if c == 'MULTI':
                    problems.append(f'{tag} 有多個讀音，請在例句手動標 [寫法|讀音]：{sent}'); out = sent
                elif not c:
                    problems.append(f'{tag} 例句找不到這個字：{sent}'); out = sent
                else:
                    s, e, form, rd = c
                    rd = rd if is_kata_word(form) else hira(rd)
                    if form == rd: out = sent[:s] + f'[{form}]' + sent[e:]
                    else: out = sent[:s] + f'[{form}|{rd}]' + sent[e:]
            m = re.search(r'\[([^\[\]|]+)(?:\|[^\[\]]*)?\]', out)
            if m and '[' not in sent:
                plain = out[:m.start()] + m.group(1) + out[m.end():]
                b = set(); i = 0
                for t in T(plain):
                    i = plain.index(t.surface, i); b.add(i); i += len(t.surface); b.add(i)
                if m.start() not in b or m.start() + len(m.group(1)) not in b:
                    problems.append(f'{tag} 挖空位置可能切在詞中間：{out}')
            rows.append(dict(level=lv, word=word, reading=reading, pos=pos, meaning=meaning, sentence=out, sentence_zh=sent_zh))
    return rows, problems
if __name__ == '__main__':
    files = sorted(sum((glob.glob(a) for a in sys.argv[1:]), []))
    rows, problems = main(files)
    for p in problems: print('⚠', p)
    json.dump(rows, open('/tmp/claude-0/jl/work/built.json', 'w'), ensure_ascii=False, indent=0)
    print(len(rows), 'rows', len(problems), 'problems')
