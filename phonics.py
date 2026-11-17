"""英文零基礎：ABC 字母與自然發音（phonics）教學頁。

網址 /phonics/<學生id>，入口在零基礎的主介面（exams.py 的 features 有 "phonics"）。
頁面分三塊：
1. ABC 字母：大小寫、字母名稱、字母的「代表音」與代表單字、嘴型提示
2. 自然發音課：短母音、長母音（Magic e）、子音組合、子音連音、母音組合、r 控制母音
   每個單字可以「拼拼看」：一格一格亮起來再唸出整個字（c·a·t → cat）
3. 聽音選字：聽一個字，從長得很像的幾個字裡選出來（cat／cut／cot）

發音一律用 UI.speak（Edge 神經語音，或伺服器 /tts）。電腦語音沒辦法單獨唸出 /k/ 這種「音」，
所以字母的音用「代表單字」示範，並附注音近似音與嘴型說明，由老師或學生跟著唸。

單字的拆法寫成 "c.a.t"：每一格是一個發音單位；前面加 * 的格子不發音（例如 Magic e 的 e）。
"""
from flask import Blueprint, render_template

bp = Blueprint('phonics', __name__)

# 字母：letter, 代表單字, 代表音的注音近似, 嘴型或發音提示
LETTERS = [
    ("A", "apple", "ㄝ", "嘴巴張大、嘴角往兩邊拉，像「ㄝ」但更開"),
    ("B", "ball", "ㄅ", "雙唇閉緊再打開，喉嚨要震動"),
    ("C", "cat", "ㄎ", "C 通常唸 /k/；後面接 e、i、y 時唸 /s/，例如 city"),
    ("D", "dog", "ㄉ", "舌尖頂住上排牙齒後面，喉嚨震動"),
    ("E", "egg", "ㄝ", "嘴巴微開，比 A 的音小一點"),
    ("F", "fish", "ㄈ", "上排牙齒輕咬下唇，吹氣"),
    ("G", "goat", "ㄍ", "G 通常唸 /g/；後面接 e、i、y 時常唸 /dʒ/，例如 giraffe"),
    ("H", "hat", "ㄏ", "輕輕哈一口氣，像對著鏡子呵氣"),
    ("I", "ink", "短促的「一」", "比中文的「一」短、嘴巴放鬆"),
    ("J", "jam", "ㄐㄩ", "嘴唇往前嘟，像中文「居」的開頭"),
    ("K", "kite", "ㄎ", "和 C 的 /k/ 一樣，舌根頂住上顎再放開"),
    ("L", "lion", "ㄌ", "舌尖頂住上排牙齒後面"),
    ("M", "moon", "ㄇ", "嘴巴閉起來，從鼻子哼出聲音"),
    ("N", "nose", "ㄋ", "舌尖頂住上排牙齒後面，從鼻子出聲"),
    ("O", "octopus", "介於ㄚ和ㄛ之間", "嘴巴張大、圓一點，聲音短"),
    ("P", "pig", "ㄆ", "雙唇閉緊，用力噴出一口氣，喉嚨不震動"),
    ("Q", "queen", "ㄎㄨ", "Q 幾乎都和 u 一起出現：qu 唸 /kw/"),
    ("R", "red", "ㄖ", "嘴唇往前嘟、舌頭往後捲，不碰到上顎"),
    ("S", "sun", "ㄙ", "牙齒輕輕合起來，像蛇一樣嘶嘶叫"),
    ("T", "top", "ㄊ", "舌尖頂住上排牙齒後面，噴出一口氣"),
    ("U", "umbrella", "短促的「ㄚ」", "嘴巴放鬆、微開，聲音短"),
    ("V", "van", "像ㄈ但喉嚨震動", "上排牙齒輕咬下唇，喉嚨要震動（和 F 不同）"),
    ("W", "water", "ㄨ", "嘴唇嘟成小圓圈再放開"),
    ("X", "fox", "ㄎㄙ", "X 多半在字尾，唸 /ks/，例如 box、six"),
    ("Y", "yellow", "一", "在字首像「一」；在字尾常唸「ㄞ」或「一」，例如 my、happy"),
    ("Z", "zoo", "像ㄙ但喉嚨震動", "和 S 同樣的嘴型，喉嚨要震動，像蜜蜂嗡嗡叫"),
]

# 自然發音課。每課：key, 標題, 說明, patterns（pat 拼法、hint 提示、words 單字）
LESSONS = [
    {"key": "short", "title": "短母音 a e i o u", "intro":
        "五個母音字母 a、e、i、o、u 夾在兩個子音中間（子音＋母音＋子音），通常唸「短母音」。"
        "先把這五個音唸熟，就能拼出很多三個字母的單字。",
     "patterns": [
         {"pat": "a", "hint": "嘴巴張大的「ㄝ」", "words": ["c.a.t", "h.a.t", "b.a.g", "m.a.p", "f.a.n"]},
         {"pat": "e", "hint": "嘴巴微開的「ㄝ」", "words": ["b.e.d", "r.e.d", "p.e.n", "t.e.n", "n.e.t"]},
         {"pat": "i", "hint": "短促的「一」", "words": ["p.i.g", "s.i.t", "b.i.g", "s.i.x", "l.i.p"]},
         {"pat": "o", "hint": "嘴巴張圓的「ㄚ／ㄛ」", "words": ["d.o.g", "h.o.t", "b.o.x", "t.o.p", "p.o.t"]},
         {"pat": "u", "hint": "短促放鬆的「ㄚ」", "words": ["c.u.p", "b.u.s", "s.u.n", "r.u.n", "b.u.g"]},
     ]},
    {"key": "magic-e", "title": "長母音：神奇的 e（Magic e）", "intro":
        "單字最後加一個不發音的 e，前面的母音就改唸「字母本身的名字」：cap 變成 cape、kit 變成 kite。"
        "灰色的 e 不發音，但它讓前面的母音變長。",
     "patterns": [
         {"pat": "a_e", "hint": "唸成字母 A 的名字「ㄟ」", "words": ["c.a.k.*e", "m.a.k.*e", "n.a.m.*e", "g.a.t.*e"],
          "pairs": [["cap", "cape"], ["tap", "tape"], ["can", "cane"]]},
         {"pat": "i_e", "hint": "唸成字母 I 的名字「ㄞ」", "words": ["k.i.t.*e", "b.i.k.*e", "f.i.v.*e", "r.i.d.*e"],
          "pairs": [["kit", "kite"], ["pin", "pine"], ["bit", "bite"]]},
         {"pat": "o_e", "hint": "唸成字母 O 的名字「ㄡ」", "words": ["h.o.m.*e", "n.o.s.*e", "r.o.p.*e", "b.o.n.*e"],
          "pairs": [["hop", "hope"], ["not", "note"], ["rod", "rode"]]},
         {"pat": "u_e", "hint": "唸成字母 U 的名字「一ㄨ」", "words": ["c.u.b.*e", "c.u.t.*e", "t.u.b.*e", "m.u.l.*e"],
          "pairs": [["cub", "cube"], ["cut", "cute"], ["tub", "tube"]]},
     ]},
    {"key": "digraph", "title": "子音組合 sh ch th wh ph ck ng", "intro":
        "兩個子音字母放在一起，合起來唸成一個新的音，要當成一格來拼。",
     "patterns": [
         {"pat": "sh", "hint": "嘟嘴的「ㄒ」，像叫人安靜「噓」", "words": ["sh.i.p", "f.i.sh", "sh.o.p", "sh.ee.p"]},
         {"pat": "ch", "hint": "嘟嘴的「ㄑ」", "words": ["ch.i.n", "ch.i.ck", "l.u.n.ch", "ch.ee.se"]},
         {"pat": "th", "hint": "舌尖輕放在上下牙齒中間吹氣", "words": ["th.i.n", "th.r.ee", "b.a.th", "th.i.s"]},
         {"pat": "wh", "hint": "和 w 一樣，嘴唇嘟成小圓圈", "words": ["wh.e.n", "wh.i.te", "wh.a.le", "wh.ea.t"]},
         {"pat": "ph", "hint": "和 f 一樣，上齒輕咬下唇", "words": ["ph.o.ne", "ph.o.t.o", "d.o.l.ph.i.n"]},
         {"pat": "ck", "hint": "和 k 一樣，常在短母音後面", "words": ["d.u.ck", "b.a.ck", "s.o.ck", "k.i.ck"]},
         {"pat": "ng", "hint": "從鼻子出聲的「ㄥ」", "words": ["s.i.ng", "k.i.ng", "l.o.ng", "r.i.ng"]},
     ]},
    {"key": "blend", "title": "子音連音 bl cl fl gr tr st sp sn dr", "intro":
        "兩個子音連在一起時，兩個音都要唸出來，只是唸得很快、中間不加母音。"
        "注意不要唸成「ㄅㄜ ㄌㄜ」，要一口氣把 b 和 l 連起來。",
     "patterns": [
         {"pat": "bl", "hint": "b＋l 一口氣唸", "words": ["bl.a.ck", "bl.o.ck", "bl.ue"]},
         {"pat": "cl", "hint": "c＋l 一口氣唸", "words": ["cl.a.p", "cl.o.ck", "cl.a.ss"]},
         {"pat": "fl", "hint": "f＋l 一口氣唸", "words": ["fl.a.g", "fl.y", "fl.o.p"]},
         {"pat": "gr", "hint": "g＋r 一口氣唸", "words": ["gr.ee.n", "gr.a.ss", "gr.a.b"]},
         {"pat": "tr", "hint": "t＋r 一口氣唸，有點像「ㄔ」", "words": ["tr.ee", "tr.a.p", "tr.u.ck"]},
         {"pat": "dr", "hint": "d＋r 一口氣唸，有點像「ㄓ」", "words": ["dr.u.m", "dr.e.ss", "dr.i.p"]},
         {"pat": "st", "hint": "s＋t 一口氣唸", "words": ["st.o.p", "st.a.r", "n.e.st"]},
         {"pat": "sp", "hint": "s＋p 一口氣唸", "words": ["sp.o.t", "sp.i.n", "sp.oo.n"]},
         {"pat": "sn", "hint": "s＋n 一口氣唸", "words": ["sn.a.ck", "sn.ow", "sn.a.ke"]},
     ]},
    {"key": "team", "title": "母音組合 ai ay ee ea oa ow oo ou oi oy", "intro":
        "兩個字母合起來唸一個母音，常常「第一個字母唸自己的名字，第二個不出聲」，"
        "例如 rain 的 ai 唸 A 的名字。oo、ou、oi、oy 則有自己的音。",
     "patterns": [
         {"pat": "ai / ay", "hint": "唸 A 的名字「ㄟ」；ay 多在字尾", "words": ["r.ai.n", "t.ai.l", "d.ay", "p.l.ay"]},
         {"pat": "ee / ea", "hint": "長長的「一」", "words": ["t.r.ee", "s.ee", "ea.t", "s.ea"]},
         {"pat": "oa / ow", "hint": "唸 O 的名字「ㄡ」", "words": ["b.oa.t", "c.oa.t", "s.n.ow", "s.l.ow"]},
         {"pat": "oo", "hint": "長的「ㄨ」，也有短的「ㄨ」（book）", "words": ["m.oo.n", "f.oo.d", "b.oo.k", "l.oo.k"]},
         {"pat": "ou / ow", "hint": "「ㄠ」，像被嚇到時的 ouch", "words": ["ou.t", "h.ou.se", "c.ow", "n.ow"]},
         {"pat": "oi / oy", "hint": "「ㄛ一」", "words": ["oi.l", "c.oi.n", "b.oy", "t.oy"]},
     ]},
    {"key": "r-vowel", "title": "r 控制母音 ar or er ir ur", "intro":
        "母音後面接 r，聲音會被 r 帶著捲起來。er、ir、ur 三個拼法唸起來一樣。",
     "patterns": [
         {"pat": "ar", "hint": "「ㄚ」再捲舌", "words": ["c.ar", "st.ar", "f.ar.m", "p.ar.k"]},
         {"pat": "or", "hint": "「ㄛ」再捲舌", "words": ["f.or.k", "h.or.se", "c.or.n", "sh.or.t"]},
         {"pat": "er / ir / ur", "hint": "捲舌的「ㄦ」，三種拼法同一個音", "words": ["h.er", "b.ir.d", "g.ir.l", "n.ur.se", "t.ur.n"]},
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


def register(app, get_student):
    @bp.route('/phonics/<int:student_id>')
    def phonics_home(student_id):
        student = get_student(student_id)
        return render_template('phonics.html', student=student, letters=LETTERS,
                               lessons=lessons_json(), listen_sets=LISTEN_SETS)

    app.register_blueprint(bp)
