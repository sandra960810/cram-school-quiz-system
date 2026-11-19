"""單字測驗區：跟單字學習區綁定，只考學生已經學過（滑過卡）的字。

題型：
- spell   看意思拼單字
- dictate 聽寫：聽發音拼出單字
- cloze   例句填空：例句挖掉單字，看中譯補回去（只出有例句的字）
- meaning 看英文選意思（四選一）
- word    看意思選英文（四選一）

批改規則都在這個檔案（`check_answer`），前端即時回饋用的是同一套規則
（`normalize` 與 vocab_quiz.html 裡的 norm() 要保持一致）。
答錯的字會自動移回學習區的「不熟區」，下次滑卡、練不熟區就會再出現。

這個模組用 `register(app, db, deps)` 掛到主程式上，避免和 app.py 互相 import。
"""
import json
import random
import re
import unicodedata
from datetime import datetime

from flask import Blueprint, abort, jsonify, render_template, request, url_for

TYPES = [
    {"key": "spell", "name": "拼寫", "icon": "pencil", "desc": "看意思拼單字"},
    {"key": "dictate", "name": "聽寫", "icon": "headphones", "desc": "聽發音拼單字"},
    {"key": "cloze", "name": "例句填空", "icon": "puzzle", "desc": "填回例句中的字"},
    {"key": "meaning", "name": "選意思", "icon": "type", "desc": "看單字選意思"},
    {"key": "word", "name": "選單字", "icon": "letter", "desc": "看意思選單字"},
]
TYPE_KEYS = [t["key"] for t in TYPES]
TYPE_NAME = {t["key"]: t["name"] for t in TYPES}
TYPED = ('spell', 'dictate', 'cloze')     # 要自己打字的題型
SIZES = (10, 20, 30)
NO_SENTENCE_PREFIX = '無例句'

bp = Blueprint('vocab_quiz', __name__)
_ = {}   # register() 放進來的主程式物件：db、Student、Vocabulary、輔助函式


# ---------------------------------------------------------------------------
# 出題與批改（純函式，不碰資料庫）
# ---------------------------------------------------------------------------

def normalize(s):
    """比對用：去頭尾空白、小寫、彎引號換直引號、連續空白合併、去掉重音符號（résumé = resume）。"""
    s = unicodedata.normalize('NFD', s or '')
    s = ''.join(c for c in s if not unicodedata.combining(c)).strip().lower()
    s = s.replace('’', "'").replace('‘', "'").replace('‐', '-').replace('‑', '-')
    return re.sub(r'\s+', ' ', s)


CLOZE_MARK = re.compile(r'\[([^\[\]|]*)(?:\|([^\[\]]*))?\]')


def clean_sentence(sentence):
    if not sentence or sentence.startswith(NO_SENTENCE_PREFIX):
        return None
    # 例句用 [ ] 標出填空處（韓文 [들어요]、日文 [飲みます|のみます]），顯示時拿掉標記與讀音
    return CLOZE_MARK.sub(lambda m: m.group(1), sentence)


# ---------- 日文（日檢） ----------
def to_hiragana(text):
    return ''.join(chr(ord(c) - 0x60) if 'ァ' <= c <= 'ヶ' else c for c in (text or ''))


def normalize_ja(s):
    """日文打字題的比對：全形半形統一、片假名當平假名（カメラ＝かめら）、去掉空白與「・」。
    不能用 normalize()：它會把濁音點去掉（が→か）。前端 vocab_quiz.html 的 normJa() 要保持一致。"""
    s = unicodedata.normalize('NFKC', s or '')
    s = to_hiragana(s)
    return re.sub(r'[\s・･]', '', s).replace('〜', '').replace('~', '')


def find_cloze_ja(sentence):
    """日文例句填空：例句裡用 [寫法|讀音] 標出要挖掉的地方（例：毎朝コーヒーを[飲みます|のみます]。），
    回傳 (挖空前, 寫法, 挖空後, 讀音)。日文沒有空格分詞，所以挖空位置由製作字庫時先標好（見 jlpt/README.md）。"""
    raw = sentence or ''
    if raw.startswith(NO_SENTENCE_PREFIX):
        return None
    m = CLOZE_MARK.search(raw)
    if not m or not m.group(1):
        return None
    before, after = clean_sentence(raw[:m.start()]) or '', clean_sentence(raw[m.end():]) or ''
    return before, m.group(1), after, m.group(2) or m.group(1)


def _stems(word):
    """單字可能的字根：study → stud（studies、studied）、make → mak（making）。"""
    w = word.lower()
    stems = {w}
    if len(w) > 3 and w[-1] in 'ey':
        stems.add(w[:-1])
    if len(w) > 4 and w.endswith('ie'):
        stems.add(w[:-2])
    return stems


def find_cloze(word, sentence):
    """在例句裡找出這個單字（含詞形變化），回傳 (挖空前, 例句中的寫法, 挖空後)；找不到回傳 None。"""
    if is_korean(word):
        return find_cloze_ko(word, sentence)
    sentence = clean_sentence(sentence)
    if not sentence or not word:
        return None
    word = word.strip()
    # 片語（含空白）：整串比對
    if ' ' in word:
        m = re.search(r'(?<![A-Za-z])' + re.escape(word) + r'(?:s|es)?(?![A-Za-z])', sentence, re.I)
        return (sentence[:m.start()], m.group(0), sentence[m.end():]) if m else None
    tokens = list(re.finditer(r"[A-Za-zÀ-ÿ](?:[A-Za-zÀ-ÿ'\-]*[A-Za-zÀ-ÿ])?", sentence))
    w = word.lower()
    for m in tokens:   # 先找一模一樣的
        if m.group(0).lower() == w:
            return sentence[:m.start()], m.group(0), sentence[m.end():]
    for m in tokens:   # 再找詞形變化：同字根開頭、多出來的字母不超過 4 個（-s/-es/-ed/-ing/-ied/-ment 除外）
        t = m.group(0).lower()
        for stem in _stems(w):
            extra = len(t) - len(stem)
            if t.startswith(stem) and 0 < extra <= 4 and len(stem) >= 3:
                # 字根後面接的是常見字尾才算，避免 art → article 這種誤判
                rest = t[len(stem):]
                if re.fullmatch(r"(s|es|d|ed|ing|ied|ies|ier|iest|er|est|ly|'s|y|e|ted|ting|ned|ning|red|ring|ped|ping|ged|ging|led|ling|ded|ding|med|ming|bed|bing)", rest):
                    return sentence[:m.start()], m.group(0), sentence[m.end():]
    return None


# ---------- 韓文（韓檢） ----------
HANGUL = re.compile(r'[가-힣]')
# 名詞後面可以接的助詞、語尾（例句填空只挖掉名詞本身，助詞留在題目上）
KO_NOUN_TAIL = re.compile(
    r'(은|는|이|가|을|를|에|의|도|로|으로|와|과|랑|이랑|하고|에서|에게|한테|께|께서|까지|부터|만|보다|처럼|마다|밖에|입니까|인가요|이죠|죠|'
    r'이나|나|이든|든지|요|이요|이에요|예요|이야|야|이다|다|였다|이었다|입니다|이었어요|였어요|들|들이|들은|들을|들의|들도|들에게)*')
# 語幹最後一個字縮寫時母音的變化：오→와（보다→봐요）、우→워（주다→줘요）、이→여（마시다→마셔요）、으→어（쓰다→써요）、되→돼
KO_CONTRACT = {8: 9, 13: 14, 20: 6, 18: 4, 11: 10}   # 中聲編號：ㅗ→ㅘ、ㅜ→ㅝ、ㅣ→ㅕ、ㅡ→ㅓ、ㅚ→ㅙ


def is_korean(word):
    return bool(HANGUL.search(word or ''))


def _syl(c):
    """韓文字拆成 (初聲, 中聲, 終聲) 編號；不是韓文字回傳 None。"""
    o = ord(c) - 0xAC00
    return (o // 588, (o % 588) // 28, o % 28) if 0 <= o < 11172 else None


def _ko_stem_match(stem, token):
    """token 是不是這個語幹的活用形（가 → 가요、갑니다、갔어요；보 → 봐요；하 → 해요、했어요）。"""
    if len(token) < len(stem) or token[:len(stem) - 1] != stem[:-1]:
        return False
    s, t = _syl(stem[-1]), _syl(token[len(stem) - 1])
    if not s or not t:
        return False
    if s[2]:                       # 語幹有收尾音（먹、읽）：要完全一樣
        return token.startswith(stem)
    if t[0] != s[0]:
        return False
    if t[1] == s[1]:               # 가 → 가요、간、갈、갑니다、갔어요
        return True
    if stem[-1] == '하' and token[len(stem) - 1] in '해했':
        return True
    return KO_CONTRACT.get(s[1]) == t[1]


def find_cloze_ko(word, sentence):
    """韓文例句填空：在例句裡找出這個字，回傳 (挖空前, 例句中的寫法, 挖空後)；找不到回傳 None。
    名詞只挖名詞本身（助詞留著），動詞與形容詞挖整個活用形（例如 가다 → 갔어요）。
    自動找不到的不規則活用（듣다 → 들어요），例句裡用 [ ] 標出要挖的地方：음악을 [들어요].
    （[ ] 只給出題用，顯示例句時 clean_sentence 會拿掉）"""
    raw = sentence or ''
    if raw.startswith(NO_SENTENCE_PREFIX):
        return None
    m = re.search(r'\[([^\[\]]+)\]', raw)
    if m:
        before, after = raw[:m.start()], raw[m.end():]
        return before.replace('[', '').replace(']', ''), m.group(1), after.replace('[', '').replace(']', '')
    sentence = clean_sentence(raw)
    word = (word or '').strip()
    if not sentence or not word or ' ' in word:
        return None
    tokens = list(re.finditer(r'[가-힣]+', sentence))
    if word.endswith('다') and len(word) >= 2:
        stem = word[:-1]
        for m in reversed(tokens):   # 韓文的動詞、形容詞通常在句尾，從後面找比較不會誤認（가다 ≠ 가방）
            if _ko_stem_match(stem, m.group(0)):
                return sentence[:m.start()], m.group(0), sentence[m.end():]
    for m in tokens:
        t = m.group(0)
        if t.startswith(word) and KO_NOUN_TAIL.fullmatch(t[len(word):]):
            end = m.start() + len(word)
            return sentence[:m.start()], word, sentence[end:]
    return None


def initials(text):
    """韓文提示只給子音（좋아요 → ㅈㅇㅇ），直接給第一個字的話一個字的單字就等於給答案。"""
    return ''.join('ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ'[_syl(c)[0]] if _syl(c) else c for c in text)


def length_hint(word):
    if ' ' in word:
        if is_korean(word):
            return f'{len(word.split())} 個字'
        return f'{len(word.split())} 個字、{sum(c.isalpha() for c in word)} 個字母'
    return f'{len(word)} 個字' if is_korean(word) else f'{len(word)} 個字母'


def letter_mask(word, show_first=False):
    """英文打字題的底線提示：一個字母一條底線，空白、連字號、撇號照原樣顯示。
    例如 ice-cream → _ _ _ - _ _ _ _ _；show_first 時第一個字母直接給（apple → a _ _ _ _）。"""
    out = []
    for i, c in enumerate(word or ''):
        out.append(c if (not c.isalpha() or (show_first and i == 0)) else '_')
    return ''.join(out)


def check_answer(qtype, given, answer, accept=None):
    """批改一題。打字題不分大小寫；選擇題比對選項文字。
    accept：日文打字題可以接受的寫法（漢字或假名都算對，例如 学校／がっこう）。"""
    if qtype in TYPED and accept:
        g = normalize_ja(given)
        return bool(g) and g in {normalize_ja(a) for a in accept}
    if qtype in TYPED:
        return normalize(given) == normalize(answer) and normalize(answer) != ''
    return (given or '') == (answer or '')


def has_zh(text):
    return bool(re.search(r'[\u4e00-\u9fff]', text or ''))


def mask_word(text, word):
    """英文解釋裡如果直接出現答案（例如 runner: one who runs），把它遮掉。"""
    if not text or not word:
        return text
    return re.sub(r'(?i)\b' + re.escape(word) + r'\w*', '＿＿', text)


def assign_types(words, types, cloze_ok, rng=random):
    """平均分配題型。例句填空只能給例句裡找得到這個字的字，名額不夠時改成其他題型。"""
    slots = [types[i % len(types)] for i in range(len(words))]
    others = [t for t in types if t != 'cloze'] or ['spell']
    n_cloze = slots.count('cloze')
    plan, rest = {}, []
    for v in words:
        if n_cloze and v.id in cloze_ok:
            plan[v.id] = 'cloze'
            n_cloze -= 1
        else:
            rest.append(v)
    fill = [t for t in slots if t != 'cloze']
    fill += [others[i % len(others)] for i in range(len(rest) - len(fill))]
    rng.shuffle(fill)
    for v, t in zip(rest, fill):
        plan[v.id] = t
    return plan


def build_questions(words, types, size, distractor_pool, rng=random):
    """出題。words 是要考的字（已依優先順序排好），types 是勾選的題型。
    每個字只出一題；例句題只給有例句、而且例句裡找得到這個字的字。"""
    picked = words[:size]
    questions = []
    # 干擾選項要和正確答案同一種語言（中文意思配中文、英文解釋配英文），不然一眼就看出答案
    pools = {True: [d for d in distractor_pool if has_zh(d.meaning)],
             False: [d for d in distractor_pool if not has_zh(d.meaning)]}
    clozes = {v.id: (find_cloze_ja(v.sentence) if getattr(v, 'reading', None) else find_cloze(v.word, v.sentence))
              for v in picked} if 'cloze' in types else {}
    plan = assign_types(picked, types, {k for k, c in clozes.items() if c}, rng)
    for v in picked:
        qtype = plan[v.id]
        cloze = clozes.get(v.id)
        meaning = v.meaning or ''
        readings = [r for r in (getattr(v, 'reading', None) or '').split('／') if r]
        # 日文的中文意思本來就常和漢字一樣（学校＝學校），不遮
        q = {"vocab_id": v.id, "type": qtype, "word": v.word, "pos": v.pos or '',
             "meaning": meaning if readings else mask_word(meaning, v.word), "answer": v.word}
        if readings:
            # 日文：單字卡顯示讀音、發音唸假名；打字題漢字或假名都算對
            q.update(ja=True, say=readings[0], accept=[v.word] + readings,
                     reading='' if to_hiragana(readings[0]) == to_hiragana(v.word) else '／'.join(readings))
        if qtype == 'cloze' and readings:
            before, form, after, form_reading = cloze
            form_readings = [r for r in form_reading.split('／') if r]
            q.update(before=before, after=after, answer=form, sentence_zh=v.sentence_zh or '',
                     accept=[form] + form_readings, say=form_readings[0],
                     hint=form_readings[0][0] + ' ＿' * (len(form_readings[0]) - 1),
                     form_differs=form != v.word)
        elif qtype in ('spell', 'dictate') and readings:
            q["hint"] = f'{len(readings[0])} 個假名'
            q["first"] = readings[0][0]
        elif qtype == 'cloze':
            before, form, after = cloze
            q.update(before=before, after=after, answer=form, sentence_zh=v.sentence_zh or '',
                     hint=initials(form) if is_korean(form) else form[0] + ' _' * (len(form) - 1),
                     form_differs=form.lower() != v.word.lower())
        elif qtype in ('spell', 'dictate'):
            q["hint"] = length_hint(v.word)
            q["first"] = initials(v.word[0]) if is_korean(v.word) else v.word[0]
        else:
            pool_words = pools[has_zh(meaning)]
            sample = rng.sample(pool_words, min(40, len(pool_words)))
            others = [d for d in sample if d.word.lower() != v.word.lower()
                      and normalize(d.meaning) != normalize(meaning)]
            seen, opts = {normalize(meaning), v.word.lower()}, []
            for d in others:
                key = normalize(d.meaning) if qtype == 'meaning' else d.word.lower()
                if key in seen:
                    continue
                seen.add(key)
                opts.append(d)
                if len(opts) == 3:
                    break
            if len(opts) < 3:          # 湊不滿四個選項就改出拼寫
                qtype = 'spell'
                if readings:
                    q.update(type='spell', hint=f'{len(readings[0])} 個假名', first=readings[0][0])
                else:
                    q.update(type='spell', hint=length_hint(v.word),
                             first=initials(v.word[0]) if is_korean(v.word) else v.word[0])
            else:
                if qtype == 'meaning':
                    choices = [q["meaning"]] + [d.meaning if getattr(d, 'reading', None) else mask_word(d.meaning, d.word)
                                                for d in opts]
                    q["answer"] = q["meaning"]
                else:
                    choices = [v.word] + [d.word for d in opts]
                rng.shuffle(choices)
                q["choices"] = choices
        # 英文打字題：有幾個字母就幾條底線（日文、韓文不用，假名數與子音提示另外給）
        if q["type"] in TYPED and not readings and not is_korean(q["answer"]):
            q["mask"] = letter_mask(q["answer"], show_first=q["type"] != 'dictate')
        questions.append(q)
    rng.shuffle(questions)   # 不熟的字雖然優先選進來，出題順序還是打散
    return questions


# ---------------------------------------------------------------------------
# 資料庫
# ---------------------------------------------------------------------------

def register(app, db, deps):
    """掛到主程式：建立資料表、註冊路由。deps 是 app.py 裡的模型與輔助函式。"""
    _.update(deps, db=db)

    class VocabQuizAttempt(db.Model):
        """一次單字測驗。scope 記錄考哪些字（all / weak / fav / theme:01）。"""
        id = db.Column(db.Integer, primary_key=True)
        student_id = db.Column(db.Integer, db.ForeignKey('student.id'), nullable=False)
        scope = db.Column(db.String(120), nullable=False)
        scope_label = db.Column(db.String(120))
        types = db.Column(db.String(80))
        total = db.Column(db.Integer, default=0)
        correct = db.Column(db.Integer, default=0)
        created_at = db.Column(db.DateTime, default=datetime.utcnow)
        finished_at = db.Column(db.DateTime)
        questions = db.Column(db.Text)      # 出題內容（JSON），交卷時用來批改
        course = db.Column(db.String(50))   # 哪個考試的單字（IELTS / TOEIC…）；舊紀錄是空的，算雅思

    class VocabQuizAnswer(db.Model):
        id = db.Column(db.Integer, primary_key=True)
        attempt_id = db.Column(db.Integer, db.ForeignKey('vocab_quiz_attempt.id'), nullable=False)
        vocab_id = db.Column(db.Integer, db.ForeignKey('vocabulary.id'), nullable=False)
        qtype = db.Column(db.String(20))
        given = db.Column(db.String(300))
        is_correct = db.Column(db.Boolean, default=False)

    _.update(Attempt=VocabQuizAttempt, Answer=VocabQuizAnswer)
    with app.app_context():
        db.create_all()
        from sqlalchemy import text
        cols = {r[1] for r in db.session.execute(text("PRAGMA table_info(vocab_quiz_attempt)"))}
        if 'course' not in cols:
            db.session.execute(text("ALTER TABLE vocab_quiz_attempt ADD COLUMN course VARCHAR(50)"))
            db.session.commit()
    app.register_blueprint(bp)


def learned_words(student, scope):
    """依範圍取出學生學過的字。回傳 (字清單, 範圍名稱)；不熟的字排前面。"""
    Vocabulary = _['Vocabulary']
    status = _['status_of'](student.id)
    if scope == 'fav':
        words = [v for v in _['favorite_rows'](student)]
        label = '我的收藏'
    else:
        q = Vocabulary.query.filter(Vocabulary.category == _['course_of'](student))
        label = '全部學過的字'
        if scope.startswith('theme:'):
            key = scope[6:]
            q = q.filter(_['theme_condition'](key))
            info = next((t for t in _['build_theme_list'](student) if t["key"] == key), None)
            if not info:
                abort(404, description='找不到這個主題')
            label = info["label"]
        locked = _['locked_theme_ids'](student)
        words = [v for v in q.all() if v.id in status
                 and not (locked and _['official_id_of'](v.theme) in locked)]   # 沒開通的等級不出題
        if scope == 'weak':
            words = [v for v in words if status.get(v.id) == 'unfamiliar']
            label = '不熟區'
    # 同一個字可能同時在主題字庫與 A–Z 字庫，只留一筆（優先留有中文、有例句的）
    best = {}
    for v in words:
        k = v.word.lower()
        score = (bool(clean_sentence(v.sentence)), has_zh(v.meaning))
        if k not in best or score > best[k][0]:
            best[k] = (score, v)
    words = [v for _s, v in best.values()]
    random.shuffle(words)
    words.sort(key=lambda v: status.get(v.id) != 'unfamiliar')   # 不熟的優先
    return words, label


def scope_options(student):
    """測驗首頁的範圍選單：每個範圍學過幾個字（同一個字在多個主題只算一次，和出題一致）。"""
    Vocabulary = _['Vocabulary']
    status = _['status_of'](student.id)
    rows = (Vocabulary.query.with_entities(Vocabulary.id, Vocabulary.word, Vocabulary.theme)
            .filter(Vocabulary.category == _['course_of'](student)).all())
    seen = {}
    locked = _['locked_theme_ids'](student)
    for vid, word, theme in rows:
        st = status.get(vid)
        if not st or (locked and _['official_id_of'](theme) in locked):
            continue
        w = word.lower()
        seen.setdefault('all', set()).add(w)
        if st == 'unfamiliar':
            seen.setdefault('weak', set()).add(w)
        seen.setdefault('theme:' + (_['official_id_of'](theme) or theme), set()).add(w)
    count = lambda k: len(seen.get(k, ()))
    opts = [{"key": "all", "label": "全部學過的字", "icon": "library", "count": count('all')},
            {"key": "weak", "label": "不熟區", "icon": "dot", "count": count('weak')},
            {"key": "fav", "label": "我的收藏", "icon": "star", "count": len(_['favorite_rows'](student))}]
    for t in _['build_theme_list'](student):
        if t["total"] and not t.get("locked"):
            opts.append({"key": f'theme:{t["key"]}', "label": t["label"], "icon": t["icon"],
                         "count": count(f'theme:{t["key"]}')})
    return opts


def student_or_404(student_id):
    return _['get_student'](student_id)


# ---------------------------------------------------------------------------
# 頁面
# ---------------------------------------------------------------------------

@bp.route('/vocab-quiz/<int:student_id>')
def quiz_home(student_id):
    student = student_or_404(student_id)
    Attempt = _['Attempt']
    course = _['course_of'](student)
    same_course = (Attempt.course == course) if course != 'IELTS' else \
        ((Attempt.course == course) | Attempt.course.is_(None))
    history = (Attempt.query.filter(Attempt.student_id == student.id, Attempt.finished_at.isnot(None),
                                    same_course)
               .order_by(Attempt.finished_at.desc()).limit(10).all())
    return render_template('vocab_quiz_home.html', student=student, scopes=scope_options(student),
                           types=TYPES, sizes=SIZES, history=history,
                           pre_scope=request.args.get('scope') or 'all')


@bp.route('/vocab-quiz/<int:student_id>/start')
def quiz_start(student_id):
    student = student_or_404(student_id)
    scope = request.args.get('scope') or 'all'
    types = [t for t in request.args.getlist('type') if t in TYPE_KEYS] or TYPE_KEYS
    try:
        size = max(5, min(50, int(request.args.get('n') or 10)))
    except ValueError:
        size = 10
    words, label = learned_words(student, scope)
    back_url = url_for('vocab_quiz.quiz_home', student_id=student.id, scope=scope)
    if not words:
        return render_template('vocab_quiz.html', student=student, questions=[], scope_label=label,
                               back_url=back_url, attempt_id=None, empty=True,
                               learn_url=_learn_url(student, scope))
    Vocabulary = _['Vocabulary']
    # 選擇題的干擾選項：同課程的字都可以用（build_questions 會挑同語言的意思）
    pool = Vocabulary.query.filter(Vocabulary.category == _['course_of'](student)).all()
    questions = build_questions(words, types, size, pool)
    db = _['db']
    attempt = _['Attempt'](student_id=student.id, scope=scope, scope_label=label,
                           course=_['course_of'](student),
                           types=','.join(types), total=len(questions),
                           questions=json.dumps(questions, ensure_ascii=False))
    db.session.add(attempt)
    db.session.commit()
    retry_url = url_for('vocab_quiz.quiz_start', student_id=student.id, scope=scope, type=types, n=size)
    return render_template('vocab_quiz.html', student=student, questions=questions, scope_label=label,
                           back_url=back_url, attempt_id=attempt.id, empty=False,
                           retry_url=retry_url, type_names=TYPE_NAME,
                           learn_url=_learn_url(student, scope))


def _learn_url(student, scope):
    if scope.startswith('theme:'):
        return url_for('learn_theme', student_id=student.id, theme_key=scope[6:])
    if scope == 'fav':
        return url_for('learn_favorites', student_id=student.id)
    return url_for('learn_home', student_id=student.id)


@bp.route('/api/vocab-quiz/submit', methods=['POST'])
def quiz_submit():
    """交卷：伺服器重新批改、存紀錄，答錯的字移到不熟區。"""
    data = request.get_json(silent=True) or {}
    db = _['db']
    attempt = db.session.get(_['Attempt'], data.get('attempt_id'))
    if not attempt or attempt.student_id != data.get('student_id'):
        return jsonify({"ok": False, "error": "找不到這次測驗"}), 400
    if attempt.finished_at:
        return jsonify({"ok": True, "correct": attempt.correct, "total": attempt.total, "moved": 0})
    questions = json.loads(attempt.questions or '[]')
    given = data.get('answers') or []
    if not isinstance(given, list):
        return jsonify({"ok": False, "error": "資料不正確"}), 400
    correct, wrong_ids = 0, []
    for i, q in enumerate(questions):
        g = given[i] if i < len(given) and isinstance(given[i], str) else ''
        ok = check_answer(q["type"], g, q["answer"], q.get("accept"))
        correct += ok
        db.session.add(_['Answer'](attempt_id=attempt.id, vocab_id=q["vocab_id"], qtype=q["type"],
                                   given=g[:300], is_correct=ok))
        if not ok:
            wrong_ids.append(q["vocab_id"])
    # 和單字學習區綁定：答錯的字移回不熟區，下次滑卡會優先出現
    status = _['status_of'](attempt.student_id)
    moved = 0
    Vocabulary = _['Vocabulary']
    for vid in dict.fromkeys(wrong_ids):
        v = db.session.get(Vocabulary, vid)
        if v:
            moved += status.get(vid) != 'unfamiliar'
            _['set_progress'](attempt.student_id, v, 'unfamiliar')
    attempt.correct = correct
    attempt.finished_at = datetime.utcnow()
    db.session.commit()
    return jsonify({"ok": True, "correct": correct, "total": len(questions), "moved": moved})
