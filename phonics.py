"""英文零基礎：單字發音教學頁（/phonics/<學生id>）。

入口在零基礎的主介面（exams.py 的 features 有 "phonics"）。重點是「每個單字怎麼唸」：
1. 單字發音（主角）：選主題逐字學。每個字有 KK 音標、音節拆解與重音、正常／慢速示範、
   「一個音節一個音節」的慢速拆唸、這個字用到的發音規則（連到發音規則課），最後按麥克風跟讀，
   瀏覽器語音辨識（Edge 送微軟、Chrome 送 Google）聽懂就給星星，也能重聽自己的錄音（錄音不上傳）
2. 發音規則：短母音、Magic e、子音組合、子音連音、母音組合、r 控制母音，每個字可以「拼拼看」
3. 聽音選字：聽一個字，從長得很像的幾個字裡選出來（cat／cut／cot）
4. ABC 字母（補充）：大小寫、KK 音標、嘴型、ABC 唸唸歌

音標資料在 pronunciation/kk.json（tools/make_pronunciation.py 由 CMU 發音字典產生）。
電腦語音沒辦法單獨唸出 /k/ 這種「音」，所以音節拆唸是把整個字放慢、音節一格一格亮起來。
發音規則課的單字寫成 "c.a.t"：每一格是一個發音單位；前面加 * 的格子不發音（例如 Magic e 的 e）。
"""
import json
import os
import re

from flask import Blueprint, jsonify, render_template, request

bp = Blueprint('phonics', __name__)

# 字母：letter, 代表單字, KK 音標, 嘴型（MOUTHS 的 key）, 注音近似音（輔助）, 發音提示
LETTERS = [
    ("A", "apple", "æ", "open", "ㄝ", "嘴巴張大、嘴角往兩邊拉，像「ㄝ」但更開"),
    ("B", "ball", "b", "closed", "ㄅ", "雙唇閉緊再打開，喉嚨要震動"),
    ("C", "cat", "k", "back", "ㄎ", "C 通常唸 /k/；後面接 e、i、y 時唸 /s/，例如 city"),
    ("D", "dog", "d", "tip", "ㄉ", "舌尖頂住上排牙齒後面，喉嚨震動"),
    ("E", "egg", "ɛ", "smile", "ㄝ", "嘴巴微開，比 A 的音小一點"),
    ("F", "fish", "f", "bite", "ㄈ", "上排牙齒輕咬下唇，吹氣"),
    ("G", "goat", "g", "back", "ㄍ", "G 通常唸 /g/；後面接 e、i、y 時常唸 /dʒ/，例如 giraffe"),
    ("H", "hat", "h", "back", "ㄏ", "輕輕哈一口氣，像對著鏡子呵氣"),
    ("I", "ink", "ɪ", "smile", "短促的「一」", "比中文的「一」短、嘴巴放鬆"),
    ("J", "jam", "dʒ", "round", "ㄐㄩ", "嘴唇往前嘟，像中文「居」的開頭"),
    ("K", "kite", "k", "back", "ㄎ", "和 C 的 /k/ 一樣，舌根頂住上顎再放開"),
    ("L", "lion", "l", "tip", "ㄌ", "舌尖頂住上排牙齒後面"),
    ("M", "moon", "m", "closed", "ㄇ", "嘴巴閉起來，從鼻子哼出聲音"),
    ("N", "nose", "n", "tip", "ㄋ", "舌尖頂住上排牙齒後面，從鼻子出聲"),
    ("O", "octopus", "ɑ", "open", "介於ㄚ和ㄛ之間", "嘴巴張大、圓一點，聲音短"),
    ("P", "pig", "p", "closed", "ㄆ", "雙唇閉緊，用力噴出一口氣，喉嚨不震動"),
    ("Q", "queen", "kw", "round", "ㄎㄨ", "Q 幾乎都和 u 一起出現：qu 唸 /kw/"),
    ("R", "red", "r", "round", "ㄖ", "嘴唇往前嘟、舌頭往後捲，不碰到上顎"),
    ("S", "sun", "s", "smile", "ㄙ", "牙齒輕輕合起來，像蛇一樣嘶嘶叫"),
    ("T", "top", "t", "tip", "ㄊ", "舌尖頂住上排牙齒後面，噴出一口氣"),
    ("U", "umbrella", "ʌ", "back", "短促的「ㄚ」", "嘴巴放鬆、微開，聲音短"),
    ("V", "van", "v", "bite", "像ㄈ但喉嚨震動", "上排牙齒輕咬下唇，喉嚨要震動（和 F 不同）"),
    ("W", "water", "w", "round", "ㄨ", "嘴唇嘟成小圓圈再放開"),
    ("X", "fox", "ks", "back", "ㄎㄙ", "X 多半在字尾，唸 /ks/，例如 box、six"),
    ("Y", "yellow", "j", "smile", "一", "在字首像「一」；在字尾常唸「ㄞ」或「一」，例如 my、happy"),
    ("Z", "zoo", "z", "smile", "像ㄙ但喉嚨震動", "和 S 同樣的嘴型，喉嚨要震動，像蜜蜂嗡嗡叫"),
]

# 嘴型圖（樣板裡畫成小圖）：key → 名稱
MOUTHS = {
    "open": "嘴巴張大", "smile": "嘴角往兩邊拉", "round": "嘴唇嘟圓", "closed": "雙唇閉起來",
    "bite": "上排牙齒輕咬下唇", "tip": "舌尖頂上排牙齒後面", "back": "嘴巴放鬆、聲音從喉嚨後面出來",
}

# 自然發音課。每課：key, 標題, 說明, patterns（pat 拼法、hint 提示、words 單字）
LESSONS = [
    {"key": "short", "title": "短母音 a e i o u", "intro":
        "五個母音字母 a、e、i、o、u 夾在兩個子音中間（子音＋母音＋子音），通常唸「短母音」。"
        "先把這五個音唸熟，就能拼出很多三個字母的單字。",
     "patterns": [
         {"pat": "a", "kk": "æ", "hint": "嘴巴張大的「ㄝ」", "words": ["c.a.t", "h.a.t", "b.a.g", "m.a.p", "f.a.n"]},
         {"pat": "e", "kk": "ɛ", "hint": "嘴巴微開的「ㄝ」", "words": ["b.e.d", "r.e.d", "p.e.n", "t.e.n", "n.e.t"]},
         {"pat": "i", "kk": "ɪ", "hint": "短促的「一」", "words": ["p.i.g", "s.i.t", "b.i.g", "s.i.x", "l.i.p"]},
         {"pat": "o", "kk": "ɑ", "hint": "嘴巴張圓的「ㄚ／ㄛ」", "words": ["d.o.g", "h.o.t", "b.o.x", "t.o.p", "p.o.t"]},
         {"pat": "u", "kk": "ʌ", "hint": "短促放鬆的「ㄚ」", "words": ["c.u.p", "b.u.s", "s.u.n", "r.u.n", "b.u.g"]},
     ]},
    {"key": "magic-e", "title": "長母音：神奇的 e（Magic e）", "intro":
        "單字最後加一個不發音的 e，前面的母音就改唸「字母本身的名字」：cap 變成 cape、kit 變成 kite。"
        "灰色的 e 不發音，但它讓前面的母音變長。",
     "patterns": [
         {"pat": "a_e", "kk": "e", "hint": "唸成字母 A 的名字「ㄟ」", "words": ["c.a.k.*e", "m.a.k.*e", "n.a.m.*e", "g.a.t.*e"],
          "pairs": [["cap", "cape"], ["tap", "tape"], ["can", "cane"]]},
         {"pat": "i_e", "kk": "aɪ", "hint": "唸成字母 I 的名字「ㄞ」", "words": ["k.i.t.*e", "b.i.k.*e", "f.i.v.*e", "r.i.d.*e"],
          "pairs": [["kit", "kite"], ["pin", "pine"], ["bit", "bite"]]},
         {"pat": "o_e", "kk": "o", "hint": "唸成字母 O 的名字「ㄡ」", "words": ["h.o.m.*e", "n.o.s.*e", "r.o.p.*e", "b.o.n.*e"],
          "pairs": [["hop", "hope"], ["not", "note"], ["rod", "rode"]]},
         {"pat": "u_e", "kk": "ju", "hint": "唸成字母 U 的名字「一ㄨ」", "words": ["c.u.b.*e", "c.u.t.*e", "t.u.b.*e", "m.u.l.*e"],
          "pairs": [["cub", "cube"], ["cut", "cute"], ["tub", "tube"]]},
     ]},
    {"key": "digraph", "title": "子音組合 sh ch th wh ph ck ng", "intro":
        "兩個子音字母放在一起，合起來唸成一個新的音，要當成一格來拼。",
     "patterns": [
         {"pat": "sh", "kk": "ʃ", "hint": "嘟嘴的「ㄒ」，像叫人安靜「噓」", "words": ["sh.i.p", "f.i.sh", "sh.o.p", "sh.ee.p"]},
         {"pat": "ch", "kk": "tʃ", "hint": "嘟嘴的「ㄑ」", "words": ["ch.i.n", "ch.i.ck", "l.u.n.ch", "ch.ee.se"]},
         {"pat": "th", "kk": "θ／ð", "hint": "舌尖輕放在上下牙齒中間吹氣", "words": ["th.i.n", "th.r.ee", "b.a.th", "th.i.s"]},
         {"pat": "wh", "kk": "w", "hint": "和 w 一樣，嘴唇嘟成小圓圈", "words": ["wh.e.n", "wh.i.te", "wh.a.le", "wh.ea.t"]},
         {"pat": "ph", "kk": "f", "hint": "和 f 一樣，上齒輕咬下唇", "words": ["ph.o.ne", "ph.o.t.o", "d.o.l.ph.i.n"]},
         {"pat": "ck", "kk": "k", "hint": "和 k 一樣，常在短母音後面", "words": ["d.u.ck", "b.a.ck", "s.o.ck", "k.i.ck"]},
         {"pat": "ng", "kk": "ŋ", "hint": "從鼻子出聲的「ㄥ」", "words": ["s.i.ng", "k.i.ng", "l.o.ng", "r.i.ng"]},
     ]},
    {"key": "blend", "title": "子音連音 bl cl fl gr tr st sp sn dr", "intro":
        "兩個子音連在一起時，兩個音都要唸出來，只是唸得很快、中間不加母音。"
        "注意不要唸成「ㄅㄜ ㄌㄜ」，要一口氣把 b 和 l 連起來。",
     "patterns": [
         {"pat": "bl", "kk": "bl", "hint": "b＋l 一口氣唸", "words": ["bl.a.ck", "bl.o.ck", "bl.ue"]},
         {"pat": "cl", "kk": "kl", "hint": "c＋l 一口氣唸", "words": ["cl.a.p", "cl.o.ck", "cl.a.ss"]},
         {"pat": "fl", "kk": "fl", "hint": "f＋l 一口氣唸", "words": ["fl.a.g", "fl.y", "fl.o.p"]},
         {"pat": "gr", "kk": "gr", "hint": "g＋r 一口氣唸", "words": ["gr.ee.n", "gr.a.ss", "gr.a.b"]},
         {"pat": "tr", "kk": "tr", "hint": "t＋r 一口氣唸，有點像「ㄔ」", "words": ["tr.ee", "tr.a.p", "tr.u.ck"]},
         {"pat": "dr", "kk": "dr", "hint": "d＋r 一口氣唸，有點像「ㄓ」", "words": ["dr.u.m", "dr.e.ss", "dr.i.p"]},
         {"pat": "st", "kk": "st", "hint": "s＋t 一口氣唸", "words": ["st.o.p", "st.a.r", "n.e.st"]},
         {"pat": "sp", "kk": "sp", "hint": "s＋p 一口氣唸", "words": ["sp.o.t", "sp.i.n", "sp.oo.n"]},
         {"pat": "sn", "kk": "sn", "hint": "s＋n 一口氣唸", "words": ["sn.a.ck", "sn.ow", "sn.a.ke"]},
     ]},
    {"key": "team", "title": "母音組合 ai ay ee ea oa ow oo ou oi oy", "intro":
        "兩個字母合起來唸一個母音，常常「第一個字母唸自己的名字，第二個不出聲」，"
        "例如 rain 的 ai 唸 A 的名字。oo、ou、oi、oy 則有自己的音。",
     "patterns": [
         {"pat": "ai / ay", "kk": "e", "hint": "唸 A 的名字「ㄟ」；ay 多在字尾", "words": ["r.ai.n", "t.ai.l", "d.ay", "p.l.ay"]},
         {"pat": "ee / ea", "kk": "i", "hint": "長長的「一」", "words": ["t.r.ee", "s.ee", "ea.t", "s.ea"]},
         {"pat": "oa / ow", "kk": "o", "hint": "唸 O 的名字「ㄡ」", "words": ["b.oa.t", "c.oa.t", "s.n.ow", "s.l.ow"]},
         {"pat": "oo", "kk": "u／ʊ", "hint": "長的「ㄨ」，也有短的「ㄨ」（book）", "words": ["m.oo.n", "f.oo.d", "b.oo.k", "l.oo.k"]},
         {"pat": "ou / ow", "kk": "aʊ", "hint": "「ㄠ」，像被嚇到時的 ouch", "words": ["ou.t", "h.ou.se", "c.ow", "n.ow"]},
         {"pat": "oi / oy", "kk": "ɔɪ", "hint": "「ㄛ一」", "words": ["oi.l", "c.oi.n", "b.oy", "t.oy"]},
     ]},
    {"key": "r-vowel", "title": "r 控制母音 ar or er ir ur", "intro":
        "母音後面接 r，聲音會被 r 帶著捲起來。er、ir、ur 三個拼法唸起來一樣。",
     "patterns": [
         {"pat": "ar", "kk": "ɑr", "hint": "「ㄚ」再捲舌", "words": ["c.ar", "st.ar", "f.ar.m", "p.ar.k"]},
         {"pat": "or", "kk": "ɔr", "hint": "「ㄛ」再捲舌", "words": ["f.or.k", "h.or.se", "c.or.n", "sh.or.t"]},
         {"pat": "er / ir / ur", "kk": "ɝ", "hint": "捲舌的「ㄦ」，三種拼法同一個音", "words": ["h.er", "b.ir.d", "g.ir.l", "n.ur.se", "t.ur.n"]},
     ]},
]

# 聽音選字：每組是長得很像、只差一個音的字
LISTEN_SETS = [
    ["cat", "cut", "cot"], ["bed", "bad", "bid"], ["pin", "pen", "pan"], ["hot", "hat", "hut"],
    ["big", "bag", "bug"], ["sit", "set", "sat"], ["cap", "cape", "cup"], ["kit", "kite", "cat"],
    ["hop", "hope", "hip"], ["not", "note", "net"], ["cub", "cube", "cab"], ["ship", "chip", "sip"],
    ["shop", "chop", "stop"], ["three", "tree", "free"], ["thin", "tin", "fin"], ["sing", "sin", "sink"],
    ["boat", "boot", "bat"], ["rain", "ran", "run"], ["moon", "man", "moan"], ["star", "store", "stir"],
    ["bird", "bud", "bed"], ["black", "back", "block"], ["green", "grin", "grain"], ["see", "say", "sigh"],
    ["cow", "coat", "cot"], ["boy", "bay", "buy"], ["fan", "van", "pan"], ["light", "right", "night"],
]


def lessons_json():
    """樣板與前端用：把 "c.a.t" 拆成 [{t:'c'}, {t:'a'}, {t:'t'}]，* 開頭的格子標成不發音。"""
    out = []
    for lesson in LESSONS:
        pats = []
        for p in lesson["patterns"]:
            words = []
            for w in p["words"]:
                parts = [{"t": s.lstrip('*'), "silent": s.startswith('*')} for s in w.split('.')]
                words.append({"word": ''.join(x["t"] for x in parts), "parts": parts})
            pats.append(dict(p, words=words))
        out.append(dict(lesson, patterns=pats))
    return out


KK_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'pronunciation', 'kk.json')
_kk = None


def kk_table():
    global _kk
    if _kk is None:
        try:
            with open(KK_PATH, encoding='utf-8') as f:
                _kk = json.load(f)
        except OSError:
            _kk = {}
    return _kk


# 單字裡看得到的發音規則：(拼字的正規表示式, 要在 KK 裡出現的音, 顯示的拼法, 提示, 發音規則課的 key)
# 拼字對上、KK 也真的有那個音才顯示（例如 bread 的 ea 唸 /ɛ/，就不提示「ea 唸長長的一」）
RULES = [
    (r'a[^aeiouy]e$', 'e', 'a_e', '字尾不發音的 e，a 唸字母名字 /e/', 'magic-e'),
    (r'i[^aeiouy]e$', 'aɪ', 'i_e', '字尾不發音的 e，i 唸字母名字 /aɪ/', 'magic-e'),
    (r'o[^aeiouy]e$', 'o', 'o_e', '字尾不發音的 e，o 唸字母名字 /o/', 'magic-e'),
    (r'u[^aeiouy]e$', 'ju', 'u_e', '字尾不發音的 e，u 唸字母名字 /ju/', 'magic-e'),
    (r'a[iy]', 'e', 'ai／ay', '唸 A 的名字 /e/', 'team'),
    (r'ee|ea', 'i', 'ee／ea', '長長的 /i/', 'team'),
    (r'oa|ow', 'o', 'oa／ow', '唸 O 的名字 /o/', 'team'),
    (r'ou|ow', 'aʊ', 'ou／ow', '/aʊ/，像被嚇到的 ouch', 'team'),
    (r'oi|oy', 'ɔɪ', 'oi／oy', '/ɔɪ/', 'team'),
    (r'oo', 'u', 'oo', '長的 /u/', 'team'),
    (r'oo', 'ʊ', 'oo', '短的 /ʊ/，像 book', 'team'),
    (r'ar', 'ɑr', 'ar', '/ɑr/，ㄚ再捲舌', 'r-vowel'),
    (r'or', 'ɔr', 'or', '/ɔr/，ㄛ再捲舌', 'r-vowel'),
    (r'[eiu]r', 'ɝ', 'er／ir／ur', '捲舌的 /ɝ/（重音）', 'r-vowel'),
    (r'er$|ar$|or$', 'ɚ', '字尾 er', '輕輕捲舌的 /ɚ/', 'r-vowel'),
    (r'sh', 'ʃ', 'sh', '/ʃ/，嘟嘴像叫人安靜', 'digraph'),
    (r'tch|ch', 'tʃ', 'ch', '/tʃ/，嘟嘴的ㄑ', 'digraph'),
    (r'th', 'θ', 'th', '/θ/，舌尖放在上下牙齒中間吹氣', 'digraph'),
    (r'th', 'ð', 'th', '/ð/，舌尖在齒間、喉嚨震動', 'digraph'),
    (r'ph', 'f', 'ph', '和 f 一樣 /f/', 'digraph'),
    (r'ck', 'k', 'ck', '和 k 一樣 /k/', 'digraph'),
    (r'ng', 'ŋ', 'ng', '/ŋ/，從鼻子出聲', 'digraph'),
    (r'^(bl|cl|fl|gl|pl|sl|br|cr|dr|fr|gr|pr|tr|sc|sk|sm|sn|sp|st|sw)', '', '連音', '開頭兩個子音要一口氣唸', 'blend'),
]
LESSON_NO = {}


def rules_for(word, kk):
    """這個字用到哪些發音規則（最多 3 個）。"""
    w, out, seen = word.lower(), [], set()
    for pat, sound, label, hint, lesson in RULES:
        m = re.search(pat, w)
        if not m or (sound and sound not in kk) or label in seen:
            continue
        if label == '連音':
            label = m.group(1)
        seen.add(label)
        out.append({"pat": label, "kk": sound, "hint": hint, "lesson": lesson})
        if len(out) >= 3:
            break
    # 三、四個字母的短字：只有一個母音字母又是短母音，提示短母音
    vowels = [c for c in w if c in 'aeiou']
    short = {'a': 'æ', 'e': 'ɛ', 'i': 'ɪ', 'o': 'ɑ', 'u': 'ʌ'}
    if not out and len(w) <= 5 and len(vowels) == 1 and short[vowels[0]] in kk and not w.endswith('e'):
        out.append({"pat": vowels[0], "kk": short[vowels[0]], "hint": '夾在子音中間的短母音', "lesson": 'short'})
    return out


def pron_of(word):
    """單字的發音資料：kk、音節、重音、拼字音節、發音規則；字典沒有就回 None。"""
    p = kk_table().get(word.strip().lower())
    if not p:
        return None
    return dict(p, rules=rules_for(word, p["kk"]))


def register(app, get_student, Vocabulary, theme_condition, themes):
    """themes：官方主題，單字發音可以挑零基礎（BASIC）與一般英文（GENERAL）的主題。"""
    word_themes = {t["id"]: t for t in themes if t["course"] in ("BASIC", "GENERAL")}

    @bp.route('/phonics/<int:student_id>')
    def phonics_home(student_id):
        student = get_student(student_id)
        # 發音規則課與 ABC 的字也附上音標，單字發音分頁可以直接練
        extra = {w: pron_of(w) for w in
                 [x[1] for x in LETTERS] + [w["word"] for l in lessons_json() for p in l["patterns"] for w in p["words"]]}
        return render_template('phonics.html', student=student, letters=LETTERS, mouths=MOUTHS,
                               lessons=lessons_json(), listen_sets=LISTEN_SETS,
                               basic_themes=[t for t in word_themes.values() if t["course"] == "BASIC"],
                               general_themes=[t for t in word_themes.values() if t["course"] == "GENERAL"],
                               pron={k: v for k, v in extra.items() if v})

    @bp.route('/phonics/<int:student_id>/words')
    def phonics_words(student_id):
        """單字發音用：某個主題的單字（拼字、中文、例句、音標），同拼字只給一次。"""
        get_student(student_id)
        theme = word_themes.get(request.args.get('theme', ''))
        if not theme:
            return jsonify([])
        rows = Vocabulary.query.filter(Vocabulary.category == theme["course"], theme_condition(theme["id"])) \
            .order_by(Vocabulary.id).all()
        seen, out = set(), []
        for v in rows:
            key = v.word.strip().lower()
            if key in seen or ' ' in key:
                continue
            seen.add(key)
            out.append({"word": v.word.strip(), "zh": v.meaning or '', "sentence": v.sentence or '',
                        "pron": pron_of(key)})
        return jsonify(out)

    app.register_blueprint(bp)
