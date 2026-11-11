import random
from datetime import datetime

from flask import Flask, request, render_template, redirect, jsonify, url_for, abort
from flask_sqlalchemy import SQLAlchemy
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


def build_theme_list(student):
    """依資料庫實際內容產生主題清單（含每個主題的字數與已解鎖數）。"""
    totals = dict(db.session.query(Vocabulary.theme, func.count(Vocabulary.id))
                  .filter(Vocabulary.category == student.enrolled_course)
                  .group_by(Vocabulary.theme).all())
    unlocked = dict(db.session.query(Vocabulary.theme, func.count(func.distinct(Vocabulary.id)))
                    .join(LearningProgress, LearningProgress.vocab_id == Vocabulary.id)
                    .filter(Vocabulary.category == student.enrolled_course,
                            LearningProgress.student_id == student.id,
                            LearningProgress.status == 'familiar')
                    .group_by(Vocabulary.theme).all())

    themes = [dict(t, key=t["id"], label=f'{t["id"]} {t["name"]}', total=0, unlocked=0)
              for t in OFFICIAL_THEMES]
    by_key = {t["key"]: t for t in themes}
    extras = []
    for theme_name, total in sorted(totals.items()):
        oid = official_id_of(theme_name)
        if oid:
            by_key[oid]["total"] += total
            by_key[oid]["unlocked"] += unlocked.get(theme_name, 0)
        else:
            extras.append({"key": theme_name, "label": theme_name, "desc": "其他字庫",
                           "icon": "🗂️", "total": total, "unlocked": unlocked.get(theme_name, 0)})
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
                           unlocked_count=unlocked_count, total_count=total_count)


@app.route('/learn/<int:student_id>/theme/<path:theme_key>')
def learn_theme(student_id, theme_key):
    """單一主題的圖鑑，也是開始學習／複習的地方。"""
    student = get_student(student_id)
    theme = theme_info(student, theme_key)
    words = theme_words(student, theme_key)
    familiar = familiar_ids_of(student_id)

    cards = [{"number": i, "id": w.id, "word": w.word, "pos": w.pos or '', "meaning": w.meaning,
              "sentence": clean_sentence(w.sentence), "letter": first_letter(w.word),
              "is_unlocked": w.id in familiar}
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
            stat["unlocked"] += c["is_unlocked"]
        letters = [counts[k] for k in sorted(counts)]
        if not q:
            letter = (request.args.get('letter') or '').upper()
            if letter not in counts:
                letter = letters[0]["letter"] if letters else None
            cards = [c for c in cards if c["letter"] == letter]
    if q:
        # 跟原本的圖鑑一樣，只搜得到已解鎖的字，未解鎖的不會洩漏答案
        ql = q.lower()
        cards = [c for c in cards if c["is_unlocked"]
                 and (ql in c["word"].lower() or ql in c["meaning"].lower())]

    scope_new = sum(1 for c in cards if not c["is_unlocked"])
    scope_review = sum(1 for c in cards if c["is_unlocked"])
    return render_template('learn_theme.html', student=student, theme=theme, cards=cards,
                           paged=paged, letters=letters, letter=letter, q=q,
                           scope_new=scope_new, scope_review=scope_review,
                           batch=STUDY_BATCH_SIZE)


@app.route('/learn/<int:student_id>/study/<path:theme_key>')
def learn_study(student_id, theme_key):
    """閃卡學習。mode=new 學還沒解鎖的字，mode=review 複習已解鎖的字。"""
    student = get_student(student_id)
    theme = theme_info(student, theme_key)
    mode = request.args.get('mode', 'new')
    if mode not in ('new', 'review'):
        mode = 'new'
    letter = (request.args.get('letter') or '').upper() or None

    words = theme_words(student, theme_key)
    if letter:
        words = [w for w in words if first_letter(w.word) == letter]
    familiar = familiar_ids_of(student_id)
    if mode == 'new':
        picked = [w for w in words if w.id not in familiar][:STUDY_BATCH_SIZE]
    else:
        pool = [w for w in words if w.id in familiar]
        picked = random.sample(pool, min(STUDY_BATCH_SIZE, len(pool)))

    words_data = [{"id": w.id, "theme": theme["label"], "word": w.word, "pos": w.pos or '',
                   "meaning": w.meaning,
                   "meaning_en": w.meaning_en if w.meaning_en and w.meaning_en != w.meaning else '',
                   "sentence": clean_sentence(w.sentence), "sentence_zh": w.sentence_zh or ''}
                  for w in picked]
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
