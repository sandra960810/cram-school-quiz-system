import json
import os
import random
from datetime import datetime

from flask import Flask, request, render_template, redirect, jsonify, url_for, abort
from flask_sqlalchemy import SQLAlchemy

import exam_data
from sqlalchemy import or_, func, text

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///quiz.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)


class Student(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    token = db.Column(db.String(100), unique=True, nullable=False)
    name = db.Column(db.String(50), nullable=False)
    enrolled_course = db.Column(db.String(50))


class Vocabulary(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    category = db.Column(db.String(50), nullable=False)
    level = db.Column(db.String(20), nullable=False)  # 基礎級/中級/中高級/進階級
    theme = db.Column(db.String(50), nullable=False)  # 主題，例如 "01 教育與學習"
    word = db.Column(db.String(100), nullable=False)
    pos = db.Column(db.String(20))           # 詞性，例如 n. / v. / adj.
    meaning = db.Column(db.String(200), nullable=False)  # 顯示用的意思（有中文用中文，沒有就用英文解釋）
    meaning_en = db.Column(db.String(500))   # 英文解釋
    sentence = db.Column(db.String(500))
    sentence_zh = db.Column(db.String(500))  # 例句中譯


class LearningProgress(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('student.id'), nullable=False)
    vocab_id = db.Column(db.Integer, db.ForeignKey('vocabulary.id'), nullable=False)
    status = db.Column(db.String(20), default='unfamiliar')
    last_reviewed = db.Column(db.DateTime, default=datetime.utcnow)


class TestAttempt(db.Model):
    """一次 IELTS 模擬測驗（listening / reading）。"""
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('student.id'), nullable=False)
    test_key = db.Column(db.String(20), default='test3')
    section = db.Column(db.String(20), nullable=False)   # listening / reading
    total = db.Column(db.Integer, default=40)
    correct = db.Column(db.Integer, default=0)
    started_at = db.Column(db.DateTime, default=datetime.utcnow)
    finished_at = db.Column(db.DateTime)


class TestAnswer(db.Model):
    """學生在某次測驗裡某一題的作答與批改結果。"""
    id = db.Column(db.Integer, primary_key=True)
    attempt_id = db.Column(db.Integer, db.ForeignKey('test_attempt.id'), nullable=False)
    qno = db.Column(db.Integer, nullable=False)
    given = db.Column(db.String(300))
    is_correct = db.Column(db.Boolean, default=False)


class TestMistake(db.Model):
    """錯題本：同一份測驗的同一題一筆。訂正後標成已訂正，之後再錯會重新打開。"""
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('student.id'), nullable=False)
    test_key = db.Column(db.String(20), default='test3')
    section = db.Column(db.String(20), nullable=False)
    qno = db.Column(db.Integer, nullable=False)
    wrong_count = db.Column(db.Integer, default=0)
    last_given = db.Column(db.String(300))
    starred = db.Column(db.Boolean, default=False)
    corrected = db.Column(db.Boolean, default=False)
    last_wrong_at = db.Column(db.DateTime, default=datetime.utcnow)
    __table_args__ = (db.UniqueConstraint('student_id', 'test_key', 'section', 'qno'),)


class WritingDraft(db.Model):
    """寫作草稿：每位學生每個 Task 一份，隨時可以回來改。"""
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('student.id'), nullable=False)
    test_key = db.Column(db.String(20), default='test3')
    task_no = db.Column(db.Integer, nullable=False)
    content = db.Column(db.Text, default='')
    updated_at = db.Column(db.DateTime, default=datetime.utcnow)
    __table_args__ = (db.UniqueConstraint('student_id', 'test_key', 'task_no'),)


class Favorite(db.Model):
    """學生收藏的單字。同一個字在不同主題算同一個收藏（以拼字判斷）。"""
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('student.id'), nullable=False)
    vocab_id = db.Column(db.Integer, db.ForeignKey('vocabulary.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    __table_args__ = (db.UniqueConstraint('student_id', 'vocab_id'),)


# 舊版資料庫沒有的欄位：啟動時自動補上（SQLite 的 create_all 不會幫既有的表加欄位）
NEW_VOCAB_COLUMNS = [("pos", "VARCHAR(20)"), ("meaning_en", "VARCHAR(500)"), ("sentence_zh", "VARCHAR(500)")]

with app.app_context():
    db.create_all()
    existing_cols = {row[1] for row in db.session.execute(text("PRAGMA table_info(vocabulary)"))}
    for col, ddl in NEW_VOCAB_COLUMNS:
        if col not in existing_cols:
            db.session.execute(text(f"ALTER TABLE vocabulary ADD COLUMN {col} {ddl}"))
    db.session.commit()


# ---------------------------------------------------------------------------
# 單字學習與圖鑑：設定
# ---------------------------------------------------------------------------

# 官方主題。資料庫裡的 theme 只要以「編號 + 空白」開頭就歸到這個主題，
# 例如 "01 教育與學習" 會算進 01。名稱以這裡為準，資料庫裡的舊名稱不影響顯示。
OFFICIAL_THEMES = [
    {"id": "01", "name": "教育與職涯", "desc": "教育制度、學術研究、就業、職場發展", "icon": "🎓"},
    {"id": "02", "name": "環境與自然生態", "desc": "氣候變遷、環境污染、能源、動物保育", "icon": "🌍"},
    {"id": "03", "name": "科技與科學", "desc": "人工智慧、數位科技、科學研究、創新", "icon": "🔬"},
    {"id": "04", "name": "健康與心理", "desc": "醫療、公共衛生、心理健康、人類行為", "icon": "🏥"},
    {"id": "05", "name": "社會與文化", "desc": "社會議題、文化差異、家庭、全球化", "icon": "🤝"},
    {"id": "06", "name": "經濟與商業", "desc": "經濟發展、金融、消費、企業經營", "icon": "💰"},
    {"id": "07", "name": "政府與法律", "desc": "公共政策、社會福利、犯罪、司法制度", "icon": "⚖️"},
    {"id": "08", "name": "城市與交通", "desc": "都市化、住房、交通、公共建設", "icon": "🏙️"},
    {"id": "09", "name": "媒體與藝術", "desc": "新聞、廣告、社群媒體、藝術娛樂", "icon": "🎨"},
    {"id": "10", "name": "食品與觀光", "desc": "食品安全、農業、飲食文化、觀光產業", "icon": "✈️"},
    {"id": "11", "name": "雅思學術高頻字彙", "desc": "4000 Academic Word List，依字首 A–Z 分頁學習", "icon": "📖"},
    {"id": "12", "name": "學術寫作與進階字彙", "desc": "圖表趨勢、因果與轉折連接詞、抽象概念", "icon": "✍️"},
]
OFFICIAL_BY_ID = {t["id"]: t for t in OFFICIAL_THEMES}

STUDY_BATCH_SIZE = 20     # 每次學習／複習的字數
LETTER_PAGING_MIN = 300   # 主題字數超過這個數量就依字首分頁
NO_SENTENCE_PREFIX = '無例句'


def get_student(student_id):
    student = db.session.get(Student, student_id)
    if not student:
        abort(404, description="找不到學生資料")
    return student


def official_id_of(theme_name):
    """資料庫的 theme 字串屬於哪個官方主題，不屬於任何官方主題就回傳 None。"""
    for t in OFFICIAL_THEMES:
        if theme_name == t["id"] or theme_name.startswith(t["id"] + " "):
            return t["id"]
    return None


def theme_condition(theme_key):
    if theme_key in OFFICIAL_BY_ID:
        return or_(Vocabulary.theme == theme_key, Vocabulary.theme.like(f"{theme_key} %"))
    return Vocabulary.theme == theme_key


def familiar_ids_of(student_id):
    rows = db.session.query(LearningProgress.vocab_id).filter_by(
        student_id=student_id, status='familiar').all()
    return {r[0] for r in rows}


def unfamiliar_ids_of(student_id):
    rows = db.session.query(LearningProgress.vocab_id).filter_by(
        student_id=student_id, status='unfamiliar').all()
    return {r[0] for r in rows}


def status_of(student_id):
    """{vocab_id: 'familiar' | 'unfamiliar'}；沒出現的字就是還沒學過（new）。"""
    status = {i: 'unfamiliar' for i in unfamiliar_ids_of(student_id)}
    status.update({i: 'familiar' for i in familiar_ids_of(student_id)})
    return status


def build_theme_list(student):
    """依資料庫實際內容產生主題清單（含每個主題的字數與已解鎖數）。"""
    totals = dict(db.session.query(Vocabulary.theme, func.count(Vocabulary.id))
                  .filter(Vocabulary.category == student.enrolled_course)
                  .group_by(Vocabulary.theme).all())
    def count_status(status):
        return dict(db.session.query(Vocabulary.theme, func.count(func.distinct(Vocabulary.id)))
                    .join(LearningProgress, LearningProgress.vocab_id == Vocabulary.id)
                    .filter(Vocabulary.category == student.enrolled_course,
                            LearningProgress.student_id == student.id,
                            LearningProgress.status == status)
                    .group_by(Vocabulary.theme).all())
    unlocked = count_status('familiar')   # 熟
    weak = count_status('unfamiliar')     # 不熟

    themes = [dict(t, key=t["id"], label=f'{t["id"]} {t["name"]}', total=0, unlocked=0, weak=0)
              for t in OFFICIAL_THEMES]
    by_key = {t["key"]: t for t in themes}
    extras = []
    for theme_name, total in sorted(totals.items()):
        oid = official_id_of(theme_name)
        if oid:
            by_key[oid]["total"] += total
            by_key[oid]["unlocked"] += unlocked.get(theme_name, 0)
            by_key[oid]["weak"] += weak.get(theme_name, 0)
        else:
            extras.append({"key": theme_name, "label": theme_name, "desc": "其他字庫",
                           "icon": "🗂️", "total": total, "unlocked": unlocked.get(theme_name, 0),
                           "weak": weak.get(theme_name, 0)})
    return themes + extras


def theme_info(student, theme_key):
    for t in build_theme_list(student):
        if t["key"] == theme_key:
            return t
    abort(404, description="找不到這個主題")


def theme_words(student, theme_key):
    return (Vocabulary.query
            .filter(Vocabulary.category == student.enrolled_course, theme_condition(theme_key))
            .order_by(func.lower(Vocabulary.word), Vocabulary.id)
            .all())


def first_letter(word):
    c = (word or '?')[0].upper()
    return c if 'A' <= c <= 'Z' else '#'


def clean_sentence(sentence):
    if not sentence or sentence.startswith(NO_SENTENCE_PREFIX):
        return None
    return sentence


# ---------------------------------------------------------------------------
# 頁面
# ---------------------------------------------------------------------------

@app.route('/login')
def login_redirect():
    token = request.args.get('token')
    student = Student.query.filter_by(token=token).first()
    if student:
        return redirect(f'/dashboard/{student.id}')
    return "無效的帳號或 Token，請從補習班系統重新進入。"


@app.route('/dashboard/<int:student_id>')
def dashboard(student_id):
    student = get_student(student_id)
    themes = build_theme_list(student)
    unlocked_count = sum(t["unlocked"] for t in themes)
    total_count = sum(t["total"] for t in themes)
    return render_template('dashboard.html', student=student,
                           unlocked_count=unlocked_count, total_count=total_count)


@app.route('/learn/<int:student_id>')
def learn_home(student_id):
    """單字學習與圖鑑：主題總覽。"""
    student = get_student(student_id)
    themes = build_theme_list(student)
    unlocked_count = sum(t["unlocked"] for t in themes)
    total_count = sum(t["total"] for t in themes)
    return render_template('learn_home.html', student=student, themes=themes,
                           unlocked_count=unlocked_count, total_count=total_count,
                           weak_count=sum(t["weak"] for t in themes),
                           favorite_count=len(favorite_rows(student)))


@app.route('/learn/<int:student_id>/theme/<path:theme_key>')
def learn_theme(student_id, theme_key):
    """單一主題的圖鑑，也是開始學習／複習的地方。"""
    student = get_student(student_id)
    theme = theme_info(student, theme_key)
    words = theme_words(student, theme_key)
    status = status_of(student_id)
    fav = favorite_words(student)

    # status：familiar 熟／unfamiliar 不熟／new 還沒學。學過（熟或不熟）的字才看得到內容
    cards = [{"number": i, "id": w.id, "word": w.word, "pos": w.pos or '', "meaning": w.meaning,
              "sentence": clean_sentence(w.sentence), "letter": first_letter(w.word),
              "status": status.get(w.id, 'new'), "is_unlocked": w.id in status,
              "is_favorite": w.word.lower() in fav}
             for i, w in enumerate(words, start=1)]

    # 字太多的主題依字首分頁，避免一次塞幾千張卡片
    paged = len(cards) > LETTER_PAGING_MIN
    letters = []
    letter = None
    q = (request.args.get('q') or '').strip()
    if paged:
        counts = {}
        for c in cards:
            stat = counts.setdefault(c["letter"], {"letter": c["letter"], "total": 0, "unlocked": 0})
            stat["total"] += 1
            stat["unlocked"] += c["status"] == 'familiar'
        letters = [counts[k] for k in sorted(counts)]
        if not q:
            letter = (request.args.get('letter') or '').upper()
            if letter not in counts:
                letter = letters[0]["letter"] if letters else None
            cards = [c for c in cards if c["letter"] == letter]
    if q:
        # 只搜得到學過的字，還沒學的不會洩漏答案
        ql = q.lower()
        cards = [c for c in cards if c["is_unlocked"]
                 and (ql in c["word"].lower() or ql in c["meaning"].lower())]

    zone_counts = {z: sum(1 for c in cards if c["status"] == z) for z in ('familiar', 'unfamiliar', 'new')}
    return render_template('learn_theme.html', student=student, theme=theme, cards=cards,
                           paged=paged, letters=letters, letter=letter, q=q,
                           zone_counts=zone_counts,
                           batch=STUDY_BATCH_SIZE)


@app.route('/learn/<int:student_id>/study/<path:theme_key>')
def learn_study(student_id, theme_key):
    """滑卡學習：右滑＝熟、左滑＝不熟。已經熟的字不會再出現。
    mode=swipe：先出不熟的字，再出還沒學過的字；mode=weak：只練不熟區。"""
    student = get_student(student_id)
    theme = theme_info(student, theme_key)
    mode = 'weak' if request.args.get('mode') == 'weak' else 'swipe'
    letter = (request.args.get('letter') or '').upper() or None

    words = theme_words(student, theme_key)
    if letter:
        words = [w for w in words if first_letter(w.word) == letter]
    picked = pick_swipe_words(words, status_of(student_id), weak_only=(mode == 'weak'))

    fav = favorite_words(student)
    status = status_of(student_id)
    words_data = [word_payload(w, theme["label"], fav, status) for w in picked]
    back_url = url_for('learn_theme', student_id=student_id, theme_key=theme_key,
                       letter=letter) if letter else url_for('learn_theme', student_id=student_id,
                                                             theme_key=theme_key)
    again_url = url_for('learn_study', student_id=student_id, theme_key=theme_key,
                        mode=mode, letter=letter) if letter else url_for(
        'learn_study', student_id=student_id, theme_key=theme_key, mode=mode)
    return render_template('ielts.html', words=words_data, student_id=student_id,
                           theme=theme, mode=mode, letter=letter,
                           back_url=back_url, again_url=again_url,
                           home_url=url_for('learn_home', student_id=student_id))


def pick_swipe_words(words, status, weak_only=False):
    """滑卡要出的字：不熟的優先，再來是還沒學過的；熟的字不出。"""
    weak = [w for w in words if status.get(w.id) == 'unfamiliar']
    new = [] if weak_only else [w for w in words if w.id not in status]
    return (weak + new)[:STUDY_BATCH_SIZE]


def word_payload(w, theme_label, fav_words=(), status=None):
    return {"id": w.id, "theme": theme_label, "word": w.word, "pos": w.pos or '',
            "meaning": w.meaning,
            "meaning_en": w.meaning_en if w.meaning_en and w.meaning_en != w.meaning else '',
            "sentence": clean_sentence(w.sentence), "sentence_zh": w.sentence_zh or '',
            "is_favorite": w.word.lower() in fav_words,
            "status": (status or {}).get(w.id, 'new')}


# ---------------------------------------------------------------------------
# 收藏
# ---------------------------------------------------------------------------

def favorite_rows(student):
    """學生收藏的字（同拼字只留一筆，新收藏的在前）。"""
    rows = (db.session.query(Vocabulary, Favorite.created_at)
            .join(Favorite, Favorite.vocab_id == Vocabulary.id)
            .filter(Favorite.student_id == student.id,
                    Vocabulary.category == student.enrolled_course)
            .order_by(Favorite.created_at.desc(), Favorite.id.desc())
            .all())
    seen, result = set(), []
    for v, _ in rows:
        if v.word.lower() not in seen:
            seen.add(v.word.lower())
            result.append(v)
    return result


def favorite_words(student):
    return {v.word.lower() for v in favorite_rows(student)}


def theme_key_of(vocab):
    return official_id_of(vocab.theme) or vocab.theme


def theme_label_of(vocab):
    oid = official_id_of(vocab.theme)
    return f'{oid} {OFFICIAL_BY_ID[oid]["name"]}' if oid else vocab.theme


@app.route('/learn/<int:student_id>/favorites')
def learn_favorites(student_id):
    student = get_student(student_id)
    status = status_of(student_id)
    cards = [{"id": v.id, "word": v.word, "pos": v.pos or '', "meaning": v.meaning,
              "theme": theme_label_of(v), "status": status.get(v.id, 'new'),
              "url": url_for('learn_word', student_id=student_id, theme_key=theme_key_of(v),
                             vocab_id=v.id, **{"from": "favorites"})}
             for v in favorite_rows(student)]
    swipe_count = len(pick_swipe_words(favorite_rows(student), status))
    return render_template('favorites.html', student=student, cards=cards, batch=STUDY_BATCH_SIZE,
                           swipe_count=swipe_count)


@app.route('/learn/<int:student_id>/favorites/study')
def learn_favorites_study(student_id):
    student = get_student(student_id)
    pool = favorite_rows(student)
    status = status_of(student_id)
    picked = pick_swipe_words(pool, status)   # 收藏裡熟的字一樣不出
    fav = {v.word.lower() for v in pool}
    back_url = url_for('learn_favorites', student_id=student_id)
    return render_template('ielts.html', words=[word_payload(v, theme_label_of(v), fav, status) for v in picked],
                           student_id=student_id, theme={"label": "⭐ 我的收藏"}, mode='fav', letter=None,
                           back_url=back_url, again_url=url_for('learn_favorites_study', student_id=student_id),
                           home_url=url_for('learn_home', student_id=student_id), back_label='返回我的收藏')


@app.route('/api/favorite', methods=['POST'])
def toggle_favorite():
    data = request.get_json(silent=True) or {}
    student = db.session.get(Student, data.get('student_id'))
    vocab = db.session.get(Vocabulary, data.get('vocab_id'))
    want = data.get('favorite')
    if not student or not vocab or not isinstance(want, bool):
        return jsonify({"success": False, "error": "資料不正確"}), 400
    same_ids = [v.id for v in same_word_rows(vocab)]
    existing = Favorite.query.filter(Favorite.student_id == student.id,
                                     Favorite.vocab_id.in_(same_ids)).all()
    if want and not existing:
        db.session.add(Favorite(student_id=student.id, vocab_id=vocab.id))
    elif not want:
        for f in existing:
            db.session.delete(f)
    db.session.commit()
    return jsonify({"success": True, "favorite": want})


@app.route('/learn/<int:student_id>/theme/<path:theme_key>/word/<int:vocab_id>')
def learn_word(student_id, theme_key, vocab_id):
    """圖鑑裡學過的單字卡：跟滑卡畫面一樣，但不用滑；可以手動移到熟區／不熟區。"""
    student = get_student(student_id)
    theme = theme_info(student, theme_key)
    word = next((w for w in theme_words(student, theme_key) if w.id == vocab_id), None)
    letter = first_letter(word.word) if word else None
    back_url = url_for('learn_theme', student_id=student_id, theme_key=theme_key,
                       letter=letter if letter and theme["total"] > LETTER_PAGING_MIN else None)
    fav = favorite_words(student)
    from_fav = request.args.get('from') == 'favorites'
    if from_fav:
        back_url = url_for('learn_favorites', student_id=student_id)
    status = status_of(student_id)
    # 不在這個主題、或還沒學過（也沒收藏）的字不給看，維持圖鑑的收集感
    if not word or (word.id not in status and word.word.lower() not in fav):
        return redirect(back_url)
    return render_template('ielts.html', words=[word_payload(word, theme["label"], fav, status)],
                           back_label='返回我的收藏' if from_fav else '返回主題圖鑑',
                           student_id=student_id,
                           theme=theme, mode='view', letter=None,
                           back_url=back_url, again_url=back_url,
                           home_url=url_for('learn_home', student_id=student_id))


# ---------------------------------------------------------------------------
# 模擬測驗區：IELTS Exam Practice Test 3（聽說讀寫）
# ---------------------------------------------------------------------------

ANSWER_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'exam')


def load_answers(section):
    path = os.path.join(ANSWER_DIR, f'answers_{exam_data.TEST_KEY}_{section}.json')
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def load_pairs(section):
    """成對作答的題目（例如 11/12 兩題任意順序）。"""
    path = os.path.join(ANSWER_DIR, f'answer_pairs_{exam_data.TEST_KEY}.json')
    try:
        with open(path, encoding='utf-8') as f:
            return [[int(q) for q in g] for g in json.load(f).get(section, [])]
    except FileNotFoundError:
        return []


def normalize(text):
    """比對用：去頭尾空白、多個空白合併成一個、不分大小寫。"""
    return ' '.join(str(text or '').split()).casefold()


def grade_section(section, given):
    """批改一個 section。given 是 {題號(int): 學生作答}。回傳每題的結果清單。"""
    answers = load_answers(section)
    pairs = load_pairs(section)
    paired = {q for group in pairs for q in group}
    results = {}

    # 成對題：兩題合起來看，答對幾個不同的選項就得幾分（同一個選項寫兩次只算一次）
    for group in pairs:
        accepted = {normalize(a) for a in answers[str(group[0])]}
        used = set()
        for qno in group:
            value = normalize(given.get(qno, ''))
            ok = bool(value) and value in accepted and value not in used
            if ok:
                used.add(value)
            results[qno] = ok

    for qno_str, accepted in answers.items():
        qno = int(qno_str)
        if qno in paired:
            continue
        results[qno] = normalize(given.get(qno, '')) in {normalize(a) for a in accepted}

    return [{"qno": qno,
             "given": (given.get(qno) or '').strip(),
             "is_correct": results[qno],
             "answer": ' / '.join(answers[str(qno)]),
             "label": exam_data.LABELS[section].get(qno, ''),
             "qtype": exam_data.QTYPES[section].get(qno, ''),
             "part": exam_data.part_of(section, qno)}
            for qno in sorted(results)]


def mistake_rows(student_id, section=None):
    q = TestMistake.query.filter_by(student_id=student_id, test_key=exam_data.TEST_KEY)
    if section:
        q = q.filter_by(section=section)
    return q.order_by(TestMistake.corrected, TestMistake.last_wrong_at.desc()).all()


def open_mistake_count(student_id):
    return TestMistake.query.filter_by(student_id=student_id, test_key=exam_data.TEST_KEY,
                                       corrected=False).count()


@app.route('/exam/<int:student_id>')
def exam_home(student_id):
    student = get_student(student_id)
    attempts = (TestAttempt.query.filter_by(student_id=student_id)
                .filter(TestAttempt.finished_at.isnot(None))
                .order_by(TestAttempt.finished_at.desc()).limit(8).all())
    best = {}
    for a in attempts:
        if a.section not in best or a.correct > best[a.section].correct:
            best[a.section] = a
    drafts = {d.task_no: d for d in WritingDraft.query.filter_by(
        student_id=student_id, test_key=exam_data.TEST_KEY).all()}
    return render_template('exam_home.html', student=student, sections=exam_data.SECTIONS,
                           title=exam_data.TEST_TITLE, attempts=attempts, best=best,
                           tests=exam_data.TESTS, test_key=exam_data.TEST_KEY,
                           drafts=drafts, pending=open_mistake_count(student_id))


@app.route('/exam/<int:student_id>/listening')
def exam_listening(student_id):
    return render_template('exam_listening.html', student=get_student(student_id))


@app.route('/exam/<int:student_id>/reading')
def exam_reading(student_id):
    return render_template('exam_reading.html', student=get_student(student_id))


@app.route('/exam/<int:student_id>/speaking')
def exam_speaking(student_id):
    return render_template('exam_speaking.html', student=get_student(student_id))


@app.route('/exam/<int:student_id>/writing', methods=['GET', 'POST'])
def exam_writing(student_id):
    student = get_student(student_id)
    if request.method == 'POST':
        for task_no in (1, 2):
            content = request.form.get(f'task{task_no}')
            if content is None:
                continue
            draft = WritingDraft.query.filter_by(student_id=student_id,
                                                 test_key=exam_data.TEST_KEY,
                                                 task_no=task_no).first()
            if not draft:
                draft = WritingDraft(student_id=student_id, test_key=exam_data.TEST_KEY,
                                     task_no=task_no)
                db.session.add(draft)
            draft.content = content
            draft.updated_at = datetime.utcnow()
        db.session.commit()
        return redirect(url_for('exam_writing', student_id=student_id, saved=1))
    drafts = {d.task_no: d for d in WritingDraft.query.filter_by(
        student_id=student_id, test_key=exam_data.TEST_KEY).all()}
    return render_template('exam_writing.html', student=student, drafts=drafts,
                           title=exam_data.TEST_TITLE,
                           saved=request.args.get('saved'))


@app.route('/exam/<int:student_id>/<section>/submit', methods=['POST'])
def exam_submit(student_id, section):
    student = get_student(student_id)
    if section not in exam_data.GRADED_SECTIONS:
        abort(404, description="這個部分沒有自動批改")

    given = {}
    for key, value in request.form.items():
        # 題目欄位命名是 q_1、q_2 …（單選題用同一個 name 讓選項互斥）
        if key.startswith('q_'):
            try:
                given[int(key[2:])] = value
            except ValueError:
                pass

    results = grade_section(section, given)
    correct = sum(1 for r in results if r["is_correct"])
    attempt = TestAttempt(student_id=student_id, test_key=exam_data.TEST_KEY, section=section,
                          total=len(results), correct=correct, finished_at=datetime.utcnow())
    db.session.add(attempt)
    db.session.flush()

    for r in results:
        db.session.add(TestAnswer(attempt_id=attempt.id, qno=r["qno"],
                                  given=r["given"][:300], is_correct=r["is_correct"]))
        mistake = TestMistake.query.filter_by(student_id=student_id, test_key=exam_data.TEST_KEY,
                                              section=section, qno=r["qno"]).first()
        if not r["is_correct"]:
            # 答錯就進錯題本；已訂正的會重新打開
            if not mistake:
                mistake = TestMistake(student_id=student_id, test_key=exam_data.TEST_KEY,
                                      section=section, qno=r["qno"], wrong_count=0)
                db.session.add(mistake)
            mistake.wrong_count += 1
            mistake.last_given = r["given"][:300]
            mistake.corrected = False
            mistake.last_wrong_at = datetime.utcnow()
        elif mistake and not mistake.corrected:
            mistake.corrected = True   # 這次答對了，算訂正完成
    db.session.commit()
    return redirect(url_for('exam_result', student_id=student_id, attempt_id=attempt.id))


@app.route('/exam/<int:student_id>/result/<int:attempt_id>')
def exam_result(student_id, attempt_id):
    student = get_student(student_id)
    attempt = db.session.get(TestAttempt, attempt_id)
    if not attempt or attempt.student_id != student_id:
        abort(404, description="找不到這次測驗")

    answers = load_answers(attempt.section)
    starred = {m.qno for m in mistake_rows(student_id, attempt.section) if m.starred}
    rows = []
    for a in TestAnswer.query.filter_by(attempt_id=attempt.id).order_by(TestAnswer.qno).all():
        rows.append({"qno": a.qno, "given": a.given or '', "is_correct": a.is_correct,
                     "answer": ' / '.join(answers[str(a.qno)]),
                     "label": exam_data.LABELS[attempt.section].get(a.qno, ''),
                     "qtype": exam_data.QTYPES[attempt.section].get(a.qno, ''),
                     "part": exam_data.part_of(attempt.section, a.qno),
                     "starred": a.qno in starred})
    pct = round(attempt.correct * 100 / attempt.total) if attempt.total else 0
    band = ielts_band(attempt.correct)
    return render_template('exam_result.html', student=student, attempt=attempt, rows=rows,
                           pct=pct, band=band, section=exam_data.SECTIONS[attempt.section],
                           section_key=attempt.section, pending=open_mistake_count(student_id))


def ielts_band(correct):
    """雅思聽力／閱讀（學術組）答對題數對應的大約分數帶。"""
    table = [(39, '8.5–9.0'), (37, '8.0'), (35, '7.5'), (33, '7.0'), (30, '6.5'),
             (27, '6.0'), (23, '5.5'), (16, '5.0'), (13, '4.5'), (10, '4.0')]
    for need, band in table:
        if correct >= need:
            return band
    return '4.0 以下'


@app.route('/exam/<int:student_id>/mistakes')
def exam_mistakes(student_id):
    student = get_student(student_id)
    items = []
    for m in mistake_rows(student_id):
        answers = load_answers(m.section)
        items.append({"id": m.id, "section": m.section,
                      "section_name": exam_data.SECTIONS[m.section]['name'],
                      "icon": exam_data.SECTIONS[m.section]['icon'],
                      "qno": m.qno, "part": exam_data.part_of(m.section, m.qno),
                      "label": exam_data.LABELS[m.section].get(m.qno, ''),
                      "qtype": exam_data.QTYPES[m.section].get(m.qno, ''),
                      "answer": ' / '.join(answers[str(m.qno)]),
                      "last_given": m.last_given or '（沒作答）',
                      "wrong_count": m.wrong_count, "starred": m.starred,
                      "corrected": m.corrected})
    return render_template('exam_mistakes.html', student=student, items=items,
                           pending=sum(1 for i in items if not i["corrected"]))


@app.route('/api/exam/star', methods=['POST'])
def exam_star():
    data = request.get_json(silent=True) or {}
    want = data.get('starred')
    if not isinstance(want, bool):
        return jsonify({"success": False, "error": "資料不正確"}), 400
    if data.get('mistake_id'):
        m = db.session.get(TestMistake, data['mistake_id'])
    else:
        section, qno = data.get('section'), data.get('qno')
        if section not in exam_data.SECTIONS or not isinstance(qno, int):
            return jsonify({"success": False, "error": "資料不正確"}), 400
        m = TestMistake.query.filter_by(student_id=data.get('student_id'),
                                        test_key=exam_data.TEST_KEY,
                                        section=section, qno=qno).first()
        if not m:
            # 答對的題目也可以收藏，補一筆（答錯次數 0、視為已訂正）
            m = TestMistake(student_id=data.get('student_id'), test_key=exam_data.TEST_KEY,
                            section=section, qno=qno, wrong_count=0, corrected=True)
            db.session.add(m)
    if not m:
        return jsonify({"success": False, "error": "找不到題目"}), 400
    m.starred = want
    db.session.commit()
    return jsonify({"success": True, "starred": m.starred, "mistake_id": m.id})


# 舊網址：合併後統一導到「單字學習與圖鑑」
@app.route('/vocab_themes/<int:student_id>')
@app.route('/profile/<int:student_id>')
@app.route('/vocab/<int:student_id>')
def legacy_learn_home(student_id):
    return redirect(url_for('learn_home', student_id=student_id))


@app.route('/vocab/<int:student_id>/<theme_id>')
def legacy_vocab_area(student_id, theme_id):
    return redirect(url_for('learn_theme', student_id=student_id, theme_key=theme_id))


@app.route('/api/update_progress', methods=['POST'])
def update_progress():
    data = request.get_json(silent=True) or {}
    student_id = data.get('student_id')
    vocab_id = data.get('vocab_id')
    status = data.get('status')
    if status not in ('familiar', 'unfamiliar') \
            or not db.session.get(Student, student_id) \
            or not db.session.get(Vocabulary, vocab_id):
        return jsonify({"success": False, "error": "資料不正確"}), 400

    set_progress(student_id, db.session.get(Vocabulary, vocab_id), status)
    db.session.commit()
    return jsonify({"success": True})


def same_word_rows(vocab):
    """同一個字可能同時出現在主題字庫和 A–Z 大字庫，學過一次兩邊都算。"""
    return Vocabulary.query.filter(Vocabulary.category == vocab.category,
                                   func.lower(Vocabulary.word) == vocab.word.lower()).all()


def set_progress(student_id, vocab, status):
    now = datetime.utcnow()
    for row in same_word_rows(vocab):
        record = LearningProgress.query.filter_by(student_id=student_id, vocab_id=row.id).first()
        if record:
            record.status = status
            record.last_reviewed = now
        else:
            db.session.add(LearningProgress(student_id=student_id, vocab_id=row.id,
                                            status=status, last_reviewed=now))


if __name__ == '__main__':
    app.run(debug=True)
