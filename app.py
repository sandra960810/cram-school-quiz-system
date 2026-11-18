import json
import os
import random
from datetime import datetime, timedelta, timezone

from flask import Flask, request, render_template, redirect, jsonify, url_for, abort, send_from_directory
from flask_sqlalchemy import SQLAlchemy

import listening_bank
import reading_bank
import writing_bank
import speaking_bank
import exams
from sqlalchemy import or_, func, text

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///quiz.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
# 口說測驗交卷時一次上傳整場錄音（約 3–8MB），上限放寬到 60MB
app.config['MAX_CONTENT_LENGTH'] = 60 * 1024 * 1024
db = SQLAlchemy(app)
exams.init_app(app)   # 考試類型（雅思、多益…）：目前在哪個考試、色系、可用功能


@app.url_defaults
def _static_version(endpoint, values):
    """靜態檔網址加上修改時間（ui.js?v=…）：更新程式後手機不會拿到瀏覽器快取的舊 JS／CSS，
    避免新頁面配舊 ui.js 而出錯（曾因此讓滑卡整個滑不動）。"""
    if endpoint == 'static' and 'filename' in values and 'v' not in values:
        path = os.path.join(app.static_folder, values['filename'])
        if os.path.isfile(path):
            values['v'] = int(os.path.getmtime(path))


class Student(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    token = db.Column(db.String(100), unique=True, nullable=False)
    name = db.Column(db.String(50), nullable=False)
    enrolled_course = db.Column(db.String(50))
    # 分級考試（韓檢…）開通了哪幾級，JSON，例如 {"topik": [1, 2]}；空的＝全部開放（見 exams.open_levels）
    unlocked_levels = db.Column(db.Text)


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
    # 管理員後台改過、新增或刪除（移到回收區）的字：匯入單字檔時跳過，不會被蓋回去（見 admin.py）
    admin_locked = db.Column(db.Boolean, default=False)
    src_key = db.Column(db.String(200))      # 管理員第一次動它之前，它在單字檔裡的「課程|主題|單字」


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


class WritingSubmission(db.Model):
    """一次寫作模擬考的交卷紀錄：兩篇作文與 AI 老師的批改結果。"""
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('student.id'), nullable=False)
    test_key = db.Column(db.String(20), nullable=False)
    task1 = db.Column(db.Text, default='')
    task2 = db.Column(db.Text, default='')
    seconds_used = db.Column(db.Integer, default=0)
    submitted_at = db.Column(db.DateTime, default=datetime.utcnow)
    ai_status = db.Column(db.String(20), default='pending')   # pending / done / error
    ai_error = db.Column(db.String(300))
    ai_result = db.Column(db.Text)          # JSON：各 Task 的四項分數與評語
    overall = db.Column(db.Float)           # AI 估計的寫作總分
    graded_at = db.Column(db.DateTime)


class SpeakingSubmission(db.Model):
    """一次口說模擬考的交卷紀錄：每題的錄音檔、瀏覽器辨識的逐字稿與 AI 老師的批改結果。
    錄音檔存在 instance/speaking_audio/<id>/（不進 git）。"""
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('student.id'), nullable=False)
    test_key = db.Column(db.String(20), nullable=False)
    answers = db.Column(db.Text)            # JSON：[{qid, seconds, file, transcript}]
    notes = db.Column(db.Text, default='')  # Part 2 準備時寫的筆記
    seconds_used = db.Column(db.Integer, default=0)
    submitted_at = db.Column(db.DateTime, default=datetime.utcnow)
    ai_status = db.Column(db.String(20), default='pending')   # pending / done / error
    ai_error = db.Column(db.String(300))
    ai_result = db.Column(db.Text)          # JSON：四項分數、評語、逐字稿
    overall = db.Column(db.Float)           # AI 估計的口說總分
    graded_at = db.Column(db.DateTime)


class Favorite(db.Model):
    """學生收藏的單字。同一個字在不同主題算同一個收藏（以拼字判斷）。"""
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('student.id'), nullable=False)
    vocab_id = db.Column(db.Integer, db.ForeignKey('vocabulary.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    __table_args__ = (db.UniqueConstraint('student_id', 'vocab_id'),)


# 舊版資料庫沒有的欄位：啟動時自動補上（SQLite 的 create_all 不會幫既有的表加欄位）
NEW_VOCAB_COLUMNS = [("pos", "VARCHAR(20)"), ("meaning_en", "VARCHAR(500)"), ("sentence_zh", "VARCHAR(500)"),
                     ("admin_locked", "BOOLEAN DEFAULT 0"), ("src_key", "VARCHAR(200)")]

with app.app_context():
    db.create_all()
    existing_cols = {row[1] for row in db.session.execute(text("PRAGMA table_info(vocabulary)"))}
    for col, ddl in NEW_VOCAB_COLUMNS:
        if col not in existing_cols:
            db.session.execute(text(f"ALTER TABLE vocabulary ADD COLUMN {col} {ddl}"))
    student_cols = {row[1] for row in db.session.execute(text("PRAGMA table_info(student)"))}
    if 'unlocked_levels' not in student_cols:
        db.session.execute(text("ALTER TABLE student ADD COLUMN unlocked_levels TEXT"))
    db.session.commit()


# ---------------------------------------------------------------------------
# 單字學習與圖鑑：設定
# ---------------------------------------------------------------------------

# 官方主題。資料庫裡的 theme 只要以「編號 + 空白」開頭就歸到這個主題，
# 例如 "01 教育與學習" 會算進 01。名稱以這裡為準，資料庫裡的舊名稱不影響顯示。
OFFICIAL_THEMES = [
    {"course": "IELTS", "id": "01", "name": "教育與職涯", "desc": "教育制度、學術研究、就業、職場發展", "icon": "cap"},
    {"course": "IELTS", "id": "02", "name": "環境與自然生態", "desc": "氣候變遷、環境污染、能源、動物保育", "icon": "globe"},
    {"course": "IELTS", "id": "03", "name": "科技與科學", "desc": "人工智慧、數位科技、科學研究、創新", "icon": "microscope"},
    {"course": "IELTS", "id": "04", "name": "健康與心理", "desc": "醫療、公共衛生、心理健康、人類行為", "icon": "heart"},
    {"course": "IELTS", "id": "05", "name": "社會與文化", "desc": "社會議題、文化差異、家庭、全球化", "icon": "users"},
    {"course": "IELTS", "id": "06", "name": "經濟與商業", "desc": "經濟發展、金融、消費、企業經營", "icon": "coins"},
    {"course": "IELTS", "id": "07", "name": "政府與法律", "desc": "公共政策、社會福利、犯罪、司法制度", "icon": "scale"},
    {"course": "IELTS", "id": "08", "name": "城市與交通", "desc": "都市化、住房、交通、公共建設", "icon": "building"},
    {"course": "IELTS", "id": "09", "name": "媒體與藝術", "desc": "新聞、廣告、社群媒體、藝術娛樂", "icon": "palette"},
    {"course": "IELTS", "id": "10", "name": "食品與觀光", "desc": "食品安全、農業、飲食文化、觀光產業", "icon": "plane"},
    # 11「雅思學術高頻字彙」原本是 4,000 多字的 A–Z 大字庫，已拆進 01–10、12–15 各主題；編號 11 保留不再使用
    {"course": "IELTS", "id": "12", "name": "學術寫作與進階字彙", "desc": "圖表趨勢、因果與轉折連接詞、抽象概念", "icon": "pen"},
    {"course": "IELTS", "id": "13", "name": "人物性格與情緒", "desc": "個性、態度、情緒與待人處事", "icon": "smile"},
    {"course": "IELTS", "id": "14", "name": "日常生活與物品", "desc": "居家用品、衣物工具、日常動作", "icon": "home"},
    {"course": "IELTS", "id": "15", "name": "通用核心字彙", "desc": "不限主題、各種文章都會出現的常用字，依字首 A–Z 分頁", "icon": "book-open"},
    # 多益（TOEIC）：依職場情境自訂的 12 個主題。編號前面加 T，避免和雅思的 01–12 混在一起
    {"course": "TOEIC", "id": "T01", "name": "辦公室與行政", "desc": "文書、設備、行程安排、日常庶務", "icon": "clipboard"},
    {"course": "TOEIC", "id": "T02", "name": "人事與職涯", "desc": "招募、面試、薪資福利、升遷與訓練", "icon": "users"},
    {"course": "TOEIC", "id": "T03", "name": "會議與溝通", "desc": "會議、簡報、電話、信件與協商", "icon": "speech"},
    {"course": "TOEIC", "id": "T04", "name": "行銷與銷售", "desc": "廣告、促銷、顧客服務、購物", "icon": "megaphone"},
    {"course": "TOEIC", "id": "T05", "name": "財務與會計", "desc": "預算、帳單、銀行、稅務與投資", "icon": "coins"},
    {"course": "TOEIC", "id": "T06", "name": "採購與物流", "desc": "訂單、出貨、庫存、倉儲與供應商", "icon": "truck"},
    {"course": "TOEIC", "id": "T07", "name": "製造與設施", "desc": "工廠、設備維修、建築工程、房地產", "icon": "wrench"},
    {"course": "TOEIC", "id": "T08", "name": "旅遊與交通", "desc": "機票、飯店、行程、通勤與交通", "icon": "plane"},
    {"course": "TOEIC", "id": "T09", "name": "餐飲與活動", "desc": "餐廳、外燴、宴會、展覽與娛樂", "icon": "utensils"},
    {"course": "TOEIC", "id": "T10", "name": "科技與通訊", "desc": "電腦、網路、軟體、媒體與出版", "icon": "monitor"},
    {"course": "TOEIC", "id": "T11", "name": "生活與健康", "desc": "居家、醫療、天氣、休閒與運動", "icon": "heart"},
    {"course": "TOEIC", "id": "T12", "name": "通用商務字彙", "desc": "各種情境都會用到的動詞、形容詞與副詞", "icon": "book-open"},
    # 英文零基礎（BASIC）：國中小程度約 2,000 字，編號 B01–B13
    {"course": "BASIC", "id": "B01", "name": "數字與時間", "desc": "數字、星期、月份、時間與季節", "icon": "clock"},
    {"course": "BASIC", "id": "B02", "name": "家人與人物", "desc": "家人、朋友、職業與稱呼", "icon": "users"},
    {"course": "BASIC", "id": "B03", "name": "身體與健康", "desc": "身體部位、生病與看醫生", "icon": "heart"},
    {"course": "BASIC", "id": "B04", "name": "食物與飲料", "desc": "三餐、水果、點心與飲料", "icon": "utensils"},
    {"course": "BASIC", "id": "B05", "name": "動物與大自然", "desc": "動物、植物、天氣與自然景物", "icon": "globe"},
    {"course": "BASIC", "id": "B06", "name": "學校與學習", "desc": "教室、文具、科目與上課用語", "icon": "cap"},
    {"course": "BASIC", "id": "B07", "name": "家與日常用品", "desc": "房間、家具、家電與生活用品", "icon": "home"},
    {"course": "BASIC", "id": "B08", "name": "衣服、顏色與購物", "desc": "衣服、顏色、形狀與買東西", "icon": "tag"},
    {"course": "BASIC", "id": "B09", "name": "地方與交通", "desc": "城市裡的地方、方向與交通工具", "icon": "truck"},
    {"course": "BASIC", "id": "B10", "name": "運動與休閒", "desc": "運動、遊戲、音樂與假日活動", "icon": "target"},
    {"course": "BASIC", "id": "B11", "name": "常用動詞", "desc": "每天都會用到的動作", "icon": "pencil"},
    {"course": "BASIC", "id": "B12", "name": "形容詞與感覺", "desc": "大小、顏色以外的描述與心情", "icon": "smile"},
    {"course": "BASIC", "id": "B13", "name": "常用小字", "desc": "代名詞、介系詞、連接詞與疑問詞", "icon": "type"},
    # 一般英文（GENERAL）：零基礎之後的 4,000 個日常生活單字，編號 G01–G15（和零基礎不重複）
    {"course": "GENERAL", "id": "G01", "name": "人際與家庭", "desc": "家人親戚、朋友、感情與人際往來", "icon": "users"},
    {"course": "GENERAL", "id": "G02", "name": "居家生活", "desc": "房子、家具、家事與生活用品", "icon": "home"},
    {"course": "GENERAL", "id": "G03", "name": "飲食與烹飪", "desc": "食材、料理、餐廳與飲料", "icon": "utensils"},
    {"course": "GENERAL", "id": "G04", "name": "購物與金錢", "desc": "買賣、價格、銀行與消費", "icon": "coins"},
    {"course": "GENERAL", "id": "G05", "name": "交通與旅行", "desc": "交通工具、道路、旅遊與住宿", "icon": "plane"},
    {"course": "GENERAL", "id": "G06", "name": "工作與職場", "desc": "職業、公司、工作內容與同事", "icon": "briefcase"},
    {"course": "GENERAL", "id": "G07", "name": "學習與知識", "desc": "學校、科目、考試與知識", "icon": "cap"},
    {"course": "GENERAL", "id": "G08", "name": "健康與醫療", "desc": "身體、疾病、醫院與保健", "icon": "heart"},
    {"course": "GENERAL", "id": "G09", "name": "自然與環境", "desc": "動植物、天氣、地理與環境", "icon": "globe"},
    {"course": "GENERAL", "id": "G10", "name": "休閒娛樂與媒體", "desc": "運動、音樂、電影、遊戲與網路", "icon": "palette"},
    {"course": "GENERAL", "id": "G11", "name": "社會與新聞", "desc": "政府、法律、犯罪、宗教與時事", "icon": "megaphone"},
    {"course": "GENERAL", "id": "G12", "name": "情緒與個性", "desc": "心情、感受、個性與態度", "icon": "smile"},
    {"course": "GENERAL", "id": "G13", "name": "常用動詞", "desc": "生活中常用的動作與片語動詞", "icon": "pencil"},
    {"course": "GENERAL", "id": "G14", "name": "常用形容詞與副詞", "desc": "描述人事物的常用字", "icon": "sparkle"},
    {"course": "GENERAL", "id": "G15", "name": "通用名詞與概念", "desc": "時間、數量、狀態等各種場合都會用到的字", "icon": "book-open"},
    # 韓檢依等級分主題（K1～K6），每一級可以各自對學生開放（exams.open_levels）
    {"course": "TOPIK", "id": "K1", "level": 1, "name": "1級", "desc": "TOPIK I 初級：數字、家人、食物、日常動作等最基本的字", "icon": "smile"},
    {"course": "TOPIK", "id": "K2", "level": 2, "name": "2級", "desc": "TOPIK I 初級：購物、交通、天氣、心情等生活用字", "icon": "home"},
    {"course": "TOPIK", "id": "K3", "level": 3, "name": "3級", "desc": "TOPIK II 中級：工作、學校、社會生活的常用字", "icon": "briefcase"},
    {"course": "TOPIK", "id": "K4", "level": 4, "name": "4級", "desc": "TOPIK II 中級：新聞、說明文常見的字與正式說法", "icon": "megaphone"},
    {"course": "TOPIK", "id": "K5", "level": 5, "name": "5級", "desc": "TOPIK II 高級：社會、經濟、文化等抽象概念", "icon": "globe"},
    {"course": "TOPIK", "id": "K6", "level": 6, "name": "6級", "desc": "TOPIK II 高級：論說文、專業領域與書面語", "icon": "cap"},
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


def locked_theme_ids(student):
    """目前這個考試裡，學生還沒開通的等級主題（例如韓檢沒買的級數）。"""
    levels = exams.open_levels(student, exams.current_exam())
    if levels is None:
        return set()
    course = exams.course_of(student)
    return {t["id"] for t in OFFICIAL_THEMES
            if t["course"] == course and t.get("level") and t["level"] not in levels}


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
    course = exams.course_of(student)
    # 同一主題裡同拼字的字只算一次（高頻字庫拆進主題後，少數字和主題原本的字重複；學習紀錄本來就同步）
    word_key = func.lower(Vocabulary.word)
    totals = dict(db.session.query(Vocabulary.theme, func.count(func.distinct(word_key)))
                  .filter(Vocabulary.category == course)
                  .group_by(Vocabulary.theme).all())
    def count_status(status):
        return dict(db.session.query(Vocabulary.theme, func.count(func.distinct(word_key)))
                    .join(LearningProgress, LearningProgress.vocab_id == Vocabulary.id)
                    .filter(Vocabulary.category == course,
                            LearningProgress.student_id == student.id,
                            LearningProgress.status == status)
                    .group_by(Vocabulary.theme).all())
    unlocked = count_status('familiar')   # 熟
    weak = count_status('unfamiliar')     # 不熟

    locked = locked_theme_ids(student)
    themes = [dict(t, key=t["id"], label=f'{t["id"]} {t["name"]}', total=0, unlocked=0, weak=0,
                   locked=t["id"] in locked)
              for t in OFFICIAL_THEMES if t["course"] == course]
    by_key = {t["key"]: t for t in themes}
    extras = []
    for theme_name, total in sorted(totals.items()):
        oid = official_id_of(theme_name)
        if oid in by_key:
            by_key[oid]["total"] += total
            by_key[oid]["unlocked"] += unlocked.get(theme_name, 0)
            by_key[oid]["weak"] += weak.get(theme_name, 0)
        else:
            extras.append({"key": theme_name, "label": theme_name, "desc": "其他字庫",
                           "icon": "folder", "locked": False, "total": total, "unlocked": unlocked.get(theme_name, 0),
                           "weak": weak.get(theme_name, 0)})
    return themes + extras


def theme_info(student, theme_key):
    for t in build_theme_list(student):
        if t["key"] == theme_key:
            if t.get("locked"):
                abort(403, description="這個等級還沒有開通")
            return t
    abort(404, description="找不到這個主題")


def theme_words(student, theme_key, dedupe=True):
    """主題裡的字（依字母排序）。

    dedupe：同拼字只留一張卡，留有中文意思／例句的那筆。高頻字庫拆進各主題後，
    約 240 個字和主題原本的字重複；兩筆的學習紀錄與收藏本來就同步（set_progress），隱藏其中一筆不會少紀錄。
    """
    rows = (Vocabulary.query
            .filter(Vocabulary.category == exams.course_of(student), theme_condition(theme_key))
            .order_by(func.lower(Vocabulary.word), Vocabulary.id)
            .all())
    if not dedupe:
        return rows
    best = {}
    for w in rows:
        key = w.word.lower()
        richness = (bool(clean_sentence(w.sentence)), bool(w.pos), not w.meaning_en or w.meaning != w.meaning_en)
        if key not in best or richness > best[key][0]:
            best[key] = (richness, w)
    keep = {v[1].id for v in best.values()}
    return [w for w in rows if w.id in keep]


HANGUL_INITIALS = 'ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ'
# 分頁時雙子音併到單子音（ㄲ 算 ㄱ），每一頁的字數比較平均
HANGUL_MERGE = {'ㄲ': 'ㄱ', 'ㄸ': 'ㄷ', 'ㅃ': 'ㅂ', 'ㅆ': 'ㅅ', 'ㅉ': 'ㅈ'}


def first_letter(word):
    """分頁用的字首：英文取 A–Z，韓文取第一個字的子音（가→ㄱ、나→ㄴ），其他歸到 #。"""
    c = (word or '?')[0].upper()
    if '가' <= c <= '힣':
        initial = HANGUL_INITIALS[(ord(c) - 0xAC00) // 588]
        return HANGUL_MERGE.get(initial, initial)
    return c if 'A' <= c <= 'Z' else '#'


def clean_sentence(sentence):
    if not sentence or sentence.startswith(NO_SENTENCE_PREFIX):
        return None
    return sentence.replace('[', '').replace(']', '')   # 韓文例句用 [ ] 標出填空處（vocab_quiz.find_cloze_ko），顯示時拿掉


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
    """主介面：先選考試類型（雅思、多益…），再進到該考試的功能選單。"""
    student = get_student(student_id)
    allowed = {e["key"] for e in exams.exams_for(student)}
    cards = []
    for e in exams.EXAMS:
        themes = []
        if e["key"] in allowed:
            exams.use_exam(e["key"])          # 切到該考試，才算得到它的字數
            themes = build_theme_list(student)
        cards.append(dict(e, allowed=e["key"] in allowed,
                          unlocked=sum(t["unlocked"] for t in themes if not t["locked"]),
                          total=sum(t["total"] for t in themes if not t["locked"])))
    # 選擇頁本身用雅思的色系（紫色學院風）；卡片各自帶自己的主色
    exams.use_exam(exams.DEFAULT_EXAM)
    return render_template('exam_select.html', student=student, cards=cards)


@app.route('/dashboard/<int:student_id>/<exam_key>')
def exam_dashboard(student_id, exam_key):
    """某個考試的功能選單（雅思：單字＋模擬測驗；多益：單字學習＋單字測驗）。"""
    student = get_student(student_id)
    if exam_key not in exams.EXAM_BY_KEY or not exams.can_use(student, exam_key):
        return redirect(url_for('dashboard', student_id=student_id))
    exam = exams.use_exam(exam_key)
    themes = build_theme_list(student)
    unlocked_count = sum(t["unlocked"] for t in themes if not t["locked"])
    total_count = sum(t["total"] for t in themes if not t["locked"])
    return render_template('dashboard.html', student=student, features=exam["features"],
                           unlocked_count=unlocked_count, total_count=total_count)


@app.route('/learn/<int:student_id>')
def learn_home(student_id):
    """單字學習與圖鑑：主題總覽。"""
    student = get_student(student_id)
    themes = build_theme_list(student)
    unlocked_count = sum(t["unlocked"] for t in themes if not t["locked"])
    total_count = sum(t["total"] for t in themes if not t["locked"])
    return render_template('learn_home.html', student=student, themes=themes,
                           unlocked_count=unlocked_count, total_count=total_count,
                           weak_count=sum(t["weak"] for t in themes if not t["locked"]),
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
                    Vocabulary.category == exams.course_of(student))
            .order_by(Favorite.created_at.desc(), Favorite.id.desc())
            .all())
    seen, result = set(), []
    locked = locked_theme_ids(student)
    for v, _ in rows:
        if locked and official_id_of(v.theme) in locked:
            continue   # 沒開通的等級：收藏先藏起來（紀錄還在，開通後就會出現）
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
                           student_id=student_id, theme={"label": "我的收藏"}, mode='fav', letter=None,
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
    word = next((w for w in theme_words(student, theme_key, dedupe=False) if w.id == vocab_id), None)
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
    """同一個字可能同時出現在多個主題（或同主題的兩筆），學過一次都算。"""
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


# ---------------------------------------------------------------------------
# 測驗區：四個技能各自一套原創題庫
# ---------------------------------------------------------------------------

# 舊的 Test 3（轉錄自採購書）已移除，資料庫裡殘留的紀錄一律略過不顯示。
RETIRED_TEST_KEYS = ('test3',)

# 資料庫存的是 UTC，顯示時要換成台灣時間，否則會差 8 小時
TAIPEI = timezone(timedelta(hours=8))


import icons
icons.init_app(app)


@app.template_filter('twtime')
def twtime(dt, fmt='%m/%d %H:%M'):
    if not dt:
        return ''
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(TAIPEI).strftime(fmt)

SKILLS = [
    {'key': 'listening', 'name': '聽力', 'icon': 'headphones', 'endpoint': 'listen_home',
     'desc': 'Parts 1–4，共 40 題'},
    {'key': 'reading', 'name': '閱讀', 'icon': 'book-open', 'endpoint': 'read_home',
     'desc': '3 篇文章，共 40 題'},
    {'key': 'writing', 'name': '寫作', 'icon': 'pen', 'endpoint': 'writing_home',
     'desc': 'Task 1＋2，60 分鐘，AI 批改'},
    {'key': 'speaking', 'name': '口說', 'icon': 'speech', 'endpoint': 'speaking_home',
     'desc': 'Part 1–3，錄音作答，AI 評分'},
]
SKILL_BY_KEY = {s['key']: s for s in SKILLS}


def ielts_band(correct):
    """雅思聽力／閱讀（學術組）答對題數對應的大約分數帶。"""
    table = [(39, '8.5–9.0'), (37, '8.0'), (35, '7.5'), (33, '7.0'), (30, '6.5'),
             (27, '6.0'), (23, '5.5'), (16, '5.0'), (13, '4.5'), (10, '4.0')]
    for need, band in table:
        if correct >= need:
            return band
    return '4.0 以下'


def live_mistakes(student_id, section=None):
    """錯題本的資料，不含已移除試卷的殘留紀錄。"""
    q = TestMistake.query.filter_by(student_id=student_id)
    q = q.filter(TestMistake.test_key.notin_(RETIRED_TEST_KEYS))
    if section:
        q = q.filter_by(section=section)
    return q.order_by(TestMistake.corrected, TestMistake.last_wrong_at.desc()).all()


def open_mistake_count(student_id):
    return (TestMistake.query
            .filter_by(student_id=student_id, corrected=False)
            .filter(TestMistake.test_key.notin_(RETIRED_TEST_KEYS)).count())


def bank_summary():
    """各技能題庫目前的進度。"""
    listening_tests = listening_bank.list_tests()
    ready = sum(1 for t in listening_tests if t.get('audio_ready'))
    out = {}
    for s in SKILLS:
        info = dict(s)
        if s['key'] == 'listening':
            info['ready_count'] = ready
            info['total_count'] = 10
            info['available'] = bool(listening_tests)
        elif s['key'] == 'reading':
            reading_tests = reading_bank.list_tests()
            info['ready_count'] = len(reading_tests)
            info['total_count'] = 10
            info['available'] = bool(reading_tests)
        elif s['key'] == 'writing':
            writing_tests = writing_bank.list_tests()
            info['ready_count'] = len(writing_tests)
            info['total_count'] = 10
            info['available'] = bool(writing_tests)
        elif s['key'] == 'speaking':
            speaking_tests = speaking_bank.list_tests()
            info['ready_count'] = len(speaking_tests)
            info['total_count'] = 10
            info['available'] = bool(speaking_tests)
        else:
            info['ready_count'] = 0
            info['total_count'] = 10
            info['available'] = False
        out[s['key']] = info
    return [out[s['key']] for s in SKILLS]


@app.route('/exam/<int:student_id>')
def exam_home(student_id):
    student = get_student(student_id)
    attempts = (TestAttempt.query.filter_by(student_id=student_id)
                .filter(TestAttempt.finished_at.isnot(None))
                .filter(TestAttempt.test_key.notin_(RETIRED_TEST_KEYS))
                .order_by(TestAttempt.finished_at.desc()).limit(8).all())
    rows = []
    for a in attempts:
        skill = SKILL_BY_KEY.get(a.section, {})
        rows.append({'id': a.id, 'section': a.section,
                     'name': skill.get('name', a.section), 'icon': skill.get('icon', ''),
                     'test_key': a.test_key, 'correct': a.correct, 'total': a.total,
                     'when': a.finished_at})
    return render_template('exam_home.html', student=student, skills=bank_summary(),
                           attempts=rows, pending=open_mistake_count(student_id))


@app.route('/exam/<int:student_id>/mistakes')
def exam_mistakes(student_id):
    student = get_student(student_id)
    only = request.args.get('section') or None
    show_starred = request.args.get('starred') == '1'

    explain_cache = {}
    rows = []
    for m in live_mistakes(student_id, only):
        if show_starred and not m.starred:
            continue
        skill = SKILL_BY_KEY.get(m.section, {})
        info = {}
        bank = {'listening': listening_bank, 'reading': reading_bank}.get(m.section)
        if bank:
            cache_key = (m.section, m.test_key)
            if cache_key not in explain_cache:
                explain_cache[cache_key] = bank.explanations(m.test_key)
            info = explain_cache[cache_key].get(m.qno, {})
        rows.append({
            'section': m.section, 'name': skill.get('name', m.section),
            'icon': skill.get('icon', ''), 'test_key': m.test_key, 'qno': m.qno,
            'part': info.get('part'), 'answer': ' / '.join(info.get('answers', [])),
            'explain': info.get('explain', ''), 'quote': info.get('quote', ''),
            'given': m.last_given or '', 'wrong_count': m.wrong_count,
            'starred': m.starred, 'corrected': m.corrected,
        })

    counts = {}
    for m in live_mistakes(student_id):
        counts[m.section] = counts.get(m.section, 0) + 1
    return render_template('bank_mistakes.html', student=student, rows=rows,
                           skills=[s for s in SKILLS if counts.get(s['key'])],
                           counts=counts, only=only, show_starred=show_starred,
                           pending=open_mistake_count(student_id))


# 聽力題庫：原創的完整模擬測驗，每回 Parts 1-4 共 40 題
# ---------------------------------------------------------------------------

def _listen_best(student_id):
    """每份聽力試卷的最佳成績 {test_key: 答對題數}。"""
    rows = (TestAttempt.query
            .filter_by(student_id=student_id, section=listening_bank.SECTION)
            .filter(TestAttempt.finished_at.isnot(None)).all())
    best = {}
    for a in rows:
        if a.test_key not in best or a.correct > best[a.test_key]:
            best[a.test_key] = a.correct
    return best


@app.route('/exam/<int:student_id>/listening-bank')
def listen_home(student_id):
    student = get_student(student_id)
    return render_template('listen_home.html', student=student,
                           tests=listening_bank.list_tests(),
                           best=_listen_best(student_id))


@app.route('/exam/<int:student_id>/listening-bank/<test_key>')
def listen_test(student_id, test_key):
    student = get_student(student_id)
    test = listening_bank.load_test(test_key)
    if not test:
        abort(404, description="找不到這份聽力試卷")
    return render_template('listen_test.html', student=student, test=test)


@app.route('/exam/<int:student_id>/listening-bank/<test_key>/submit', methods=['POST'])
def listen_submit(student_id, test_key):
    get_student(student_id)
    test = listening_bank.load_test(test_key)
    if not test:
        abort(404, description="找不到這份聽力試卷")

    given = {}
    for field, value in request.form.items():
        if field.startswith('q_'):
            try:
                given[int(field[2:])] = value
            except ValueError:
                pass

    results = listening_bank.grade(test_key, given)
    correct = sum(1 for r in results if r['is_correct'])
    attempt = TestAttempt(student_id=student_id, test_key=test_key,
                          section=listening_bank.SECTION, total=len(results),
                          correct=correct, finished_at=datetime.utcnow())
    db.session.add(attempt)
    db.session.flush()

    for r in results:
        db.session.add(TestAnswer(attempt_id=attempt.id, qno=r['qno'],
                                  given=r['given'][:300], is_correct=r['is_correct']))
        mistake = TestMistake.query.filter_by(student_id=student_id, test_key=test_key,
                                              section=listening_bank.SECTION,
                                              qno=r['qno']).first()
        if not r['is_correct']:
            if not mistake:
                mistake = TestMistake(student_id=student_id, test_key=test_key,
                                      section=listening_bank.SECTION, qno=r['qno'],
                                      wrong_count=0)
                db.session.add(mistake)
            mistake.wrong_count += 1
            mistake.last_given = r['given'][:300]
            mistake.corrected = False
            mistake.last_wrong_at = datetime.utcnow()
        elif mistake and not mistake.corrected:
            mistake.corrected = True
    db.session.commit()
    return redirect(url_for('listen_result', student_id=student_id, attempt_id=attempt.id))


@app.route('/exam/<int:student_id>/listening-bank/result/<int:attempt_id>')
def listen_result(student_id, attempt_id):
    student = get_student(student_id)
    attempt = db.session.get(TestAttempt, attempt_id)
    if not attempt or attempt.student_id != student_id:
        abort(404, description="找不到這次測驗")
    test = listening_bank.load_test(attempt.test_key)
    if not test:
        abort(404, description="找不到這份聽力試卷")

    info = listening_bank.explanations(attempt.test_key)
    starred = {m.qno for m in TestMistake.query.filter_by(
        student_id=student_id, test_key=attempt.test_key,
        section=listening_bank.SECTION, starred=True).all()}

    rows, part_scores = [], {}
    for a in TestAnswer.query.filter_by(attempt_id=attempt.id).order_by(TestAnswer.qno).all():
        meta = info.get(a.qno, {})
        rows.append({'qno': a.qno, 'given': a.given or '', 'is_correct': a.is_correct,
                     'answer': ' / '.join(meta.get('answers', [])),
                     'explain': meta.get('explain', ''), 'quote': meta.get('quote', ''),
                     'starred': a.qno in starred})
        pno = meta.get('part')
        if pno:
            bucket = part_scores.setdefault(pno, {'no': pno, 'total': 0, 'correct': 0})
            bucket['total'] += 1
            bucket['correct'] += 1 if a.is_correct else 0

    pct = round(attempt.correct * 100 / attempt.total) if attempt.total else 0
    return render_template('listen_result.html', student=student, attempt=attempt, test=test,
                           rows=rows, pct=pct, band=ielts_band(attempt.correct),
                           part_scores=[part_scores[k] for k in sorted(part_scores)])


@app.route('/api/listen/star', methods=['POST'])
def listen_star():
    data = request.get_json(silent=True) or {}
    student_id = data.get('student_id')
    test_key = data.get('test_key')
    qno = data.get('qno')
    if not (student_id and test_key and qno):
        return jsonify({'ok': False}), 400
    # 閱讀的成績頁也共用這支 API，用 section 區分；沒帶就是聽力（舊頁面相容）
    section = data.get('section') or listening_bank.SECTION
    if section not in (listening_bank.SECTION, reading_bank.SECTION):
        return jsonify({'ok': False}), 400
    m = TestMistake.query.filter_by(student_id=student_id, test_key=test_key,
                                    section=section, qno=qno).first()
    if not m:
        m = TestMistake(student_id=student_id, test_key=test_key,
                        section=section, qno=qno, wrong_count=0,
                        corrected=True)
        db.session.add(m)
    m.starred = bool(data.get('starred'))
    db.session.commit()
    return jsonify({'ok': True, 'starred': m.starred})


# ---------------------------------------------------------------------------
# 閱讀題庫：原創的學術組模擬測驗，每回 3 篇文章共 40 題
# ---------------------------------------------------------------------------

def _read_best(student_id):
    """每份閱讀試卷的最佳成績 {test_key: 答對題數}。"""
    rows = (TestAttempt.query
            .filter_by(student_id=student_id, section=reading_bank.SECTION)
            .filter(TestAttempt.finished_at.isnot(None)).all())
    best = {}
    for a in rows:
        if a.test_key not in best or a.correct > best[a.test_key]:
            best[a.test_key] = a.correct
    return best


@app.route('/exam/<int:student_id>/reading')
def read_home(student_id):
    student = get_student(student_id)
    return render_template('read_home.html', student=student,
                           tests=reading_bank.list_tests(),
                           best=_read_best(student_id))


@app.route('/exam/<int:student_id>/reading/<test_key>')
def read_test(student_id, test_key):
    student = get_student(student_id)
    test = reading_bank.load_test(test_key)
    if not test:
        abort(404, description="找不到這份閱讀試卷")
    return render_template('read_test.html', student=student, test=test)


@app.route('/exam/<int:student_id>/reading/<test_key>/submit', methods=['POST'])
def read_submit(student_id, test_key):
    get_student(student_id)
    test = reading_bank.load_test(test_key)
    if not test:
        abort(404, description="找不到這份閱讀試卷")

    given = {}
    for field, value in request.form.items():
        if field.startswith('q_'):
            try:
                given[int(field[2:])] = value
            except ValueError:
                pass

    results = reading_bank.grade(test_key, given)
    correct = sum(1 for r in results if r['is_correct'])
    attempt = TestAttempt(student_id=student_id, test_key=test_key,
                          section=reading_bank.SECTION, total=len(results),
                          correct=correct, finished_at=datetime.utcnow())
    db.session.add(attempt)
    db.session.flush()

    for r in results:
        db.session.add(TestAnswer(attempt_id=attempt.id, qno=r['qno'],
                                  given=r['given'][:300], is_correct=r['is_correct']))
        mistake = TestMistake.query.filter_by(student_id=student_id, test_key=test_key,
                                              section=reading_bank.SECTION,
                                              qno=r['qno']).first()
        if not r['is_correct']:
            if not mistake:
                mistake = TestMistake(student_id=student_id, test_key=test_key,
                                      section=reading_bank.SECTION, qno=r['qno'],
                                      wrong_count=0)
                db.session.add(mistake)
            mistake.wrong_count += 1
            mistake.last_given = r['given'][:300]
            mistake.corrected = False
            mistake.last_wrong_at = datetime.utcnow()
        elif mistake and not mistake.corrected:
            mistake.corrected = True
    db.session.commit()
    return redirect(url_for('read_result', student_id=student_id, attempt_id=attempt.id))


@app.route('/exam/<int:student_id>/reading/result/<int:attempt_id>')
def read_result(student_id, attempt_id):
    student = get_student(student_id)
    attempt = db.session.get(TestAttempt, attempt_id)
    if not attempt or attempt.student_id != student_id or attempt.section != reading_bank.SECTION:
        abort(404, description="找不到這次測驗")
    test = reading_bank.load_test(attempt.test_key)
    if not test:
        abort(404, description="找不到這份閱讀試卷")

    info = reading_bank.explanations(attempt.test_key)
    starred = {m.qno for m in TestMistake.query.filter_by(
        student_id=student_id, test_key=attempt.test_key,
        section=reading_bank.SECTION, starred=True).all()}

    rows, part_scores = [], {}
    for a in TestAnswer.query.filter_by(attempt_id=attempt.id).order_by(TestAnswer.qno).all():
        meta = info.get(a.qno, {})
        rows.append({'qno': a.qno, 'given': a.given or '', 'is_correct': a.is_correct,
                     'answer': ' / '.join(meta.get('answers', [])),
                     'explain': meta.get('explain', ''), 'quote': meta.get('quote', ''),
                     'passage': meta.get('part'), 'starred': a.qno in starred})
        pno = meta.get('part')
        if pno:
            bucket = part_scores.setdefault(pno, {'no': pno, 'total': 0, 'correct': 0})
            bucket['total'] += 1
            bucket['correct'] += 1 if a.is_correct else 0

    pct = round(attempt.correct * 100 / attempt.total) if attempt.total else 0
    return render_template('read_result.html', student=student, attempt=attempt, test=test,
                           rows=rows, pct=pct, band=ielts_band(attempt.correct),
                           part_scores=[part_scores[k] for k in sorted(part_scores)])



# ---------------------------------------------------------------------------
# 寫作題庫：比照電腦考的作答介面，交卷後由 AI 老師依四項標準批改
# ---------------------------------------------------------------------------

def _writing_rows(student_id, test_key=None):
    q = WritingSubmission.query.filter_by(student_id=student_id)
    if test_key:
        q = q.filter_by(test_key=test_key)
    return q.order_by(WritingSubmission.submitted_at.desc()).all()


@app.route('/exam/<int:student_id>/writing')
def writing_home(student_id):
    student = get_student(student_id)
    history = _writing_rows(student_id)
    best = {}
    for w in history:
        if w.overall is not None and w.overall > best.get(w.test_key, -1):
            best[w.test_key] = w.overall
    return render_template('write_home.html', student=student, tests=writing_bank.list_tests(),
                           best=best, history=history[:10], ai_ready=writing_bank.ai_ready(),
                           ai_label=writing_bank.ai_label())


@app.route('/exam/<int:student_id>/writing/<test_key>')
def writing_test(student_id, test_key):
    student = get_student(student_id)
    test = writing_bank.load_test(test_key)
    if not test:
        abort(404, description="找不到這份寫作試卷")
    drafts = {d.task_no: d.content for d in
              WritingDraft.query.filter_by(student_id=student_id, test_key=test_key).all()}
    return render_template('write_test.html', student=student, test=test, drafts=drafts)


@app.route('/api/writing/draft', methods=['POST'])
def writing_draft():
    """作答中每隔幾秒自動存草稿，當機或關錯視窗都找得回來。"""
    data = request.get_json(silent=True) or {}
    try:
        student_id = int(data.get('student_id'))
        task_no = int(data.get('task_no'))
    except (TypeError, ValueError):
        return jsonify({'ok': False}), 400
    test_key = str(data.get('test_key', ''))
    if task_no not in (1, 2) or not writing_bank.load_test(test_key) or not db.session.get(Student, student_id):
        return jsonify({'ok': False}), 400
    draft = WritingDraft.query.filter_by(student_id=student_id, test_key=test_key, task_no=task_no).first()
    if not draft:
        draft = WritingDraft(student_id=student_id, test_key=test_key, task_no=task_no)
        db.session.add(draft)
    draft.content = str(data.get('content', ''))[:20000]
    draft.updated_at = datetime.utcnow()
    db.session.commit()
    return jsonify({'ok': True})


@app.route('/exam/<int:student_id>/writing/<test_key>/submit', methods=['POST'])
def writing_submit(student_id, test_key):
    get_student(student_id)
    if not writing_bank.load_test(test_key):
        abort(404, description="找不到這份寫作試卷")
    try:
        used = max(0, int(request.form.get('seconds_used', 0)))
    except ValueError:
        used = 0
    sub = WritingSubmission(student_id=student_id, test_key=test_key,
                            task1=request.form.get('task1', '')[:20000],
                            task2=request.form.get('task2', '')[:20000],
                            seconds_used=used)
    db.session.add(sub)
    # 交卷後草稿清空，下次重考從空白開始
    WritingDraft.query.filter_by(student_id=student_id, test_key=test_key).delete()
    db.session.commit()
    return redirect(url_for('writing_result', student_id=student_id, sub_id=sub.id))


def _writing_sub(student_id, sub_id):
    sub = db.session.get(WritingSubmission, sub_id)
    if not sub or sub.student_id != student_id:
        abort(404, description="找不到這次寫作紀錄")
    return sub


@app.route('/exam/<int:student_id>/writing/result/<int:sub_id>')
def writing_result(student_id, sub_id):
    student = get_student(student_id)
    sub = _writing_sub(student_id, sub_id)
    test = writing_bank.load_test(sub.test_key)
    if not test:
        abort(404, description="找不到這份寫作試卷")
    result = json.loads(sub.ai_result) if sub.ai_result else None
    essays = {1: sub.task1 or '', 2: sub.task2 or ''}
    return render_template('write_result.html', student=student, sub=sub, test=test, result=result,
                           essays=essays, words={n: writing_bank.count_words(e) for n, e in essays.items()},
                           criteria=writing_bank.CRITERIA, ai_ready=writing_bank.ai_ready())


@app.route('/exam/<int:student_id>/writing/result/<int:sub_id>/grade', methods=['POST'])
def writing_grade(student_id, sub_id):
    """請 AI 老師批改（約需 1–2 分鐘）。結果存進資料庫，之後打開不用再花錢重批。"""
    get_student(student_id)
    sub = _writing_sub(student_id, sub_id)
    if sub.ai_status == 'done' and request.args.get('again') != '1':
        return jsonify({'ok': True})
    if not writing_bank.ai_ready():
        return jsonify({'ok': False, 'error': 'AI 老師還沒設定：請在櫃台電腦雙擊 set_ai_key.bat 輸入 API 金鑰。'}), 400
    test = writing_bank.load_test(sub.test_key)
    try:
        result = writing_bank.grade_all(test, {1: sub.task1 or '', 2: sub.task2 or ''})
    except RuntimeError as e:
        sub.ai_status, sub.ai_error = 'error', str(e)[:300]
        db.session.commit()
        return jsonify({'ok': False, 'error': str(e)}), 502
    except Exception as e:  # 其他意外：記下來，不讓整頁壞掉
        app.logger.exception('寫作批改失敗')
        sub.ai_status, sub.ai_error = 'error', f'批改時發生錯誤：{e}'[:300]
        db.session.commit()
        return jsonify({'ok': False, 'error': sub.ai_error}), 500
    sub.ai_result = json.dumps(result, ensure_ascii=False)
    sub.overall = result['overall']
    sub.ai_status, sub.ai_error = 'done', None
    sub.graded_at = datetime.utcnow()
    db.session.commit()
    return jsonify({'ok': True, 'overall': sub.overall})


# ---------------------------------------------------------------------------
# 口說題庫：比照正式考試 Part 1–3，錄音交卷後由 AI 老師辨識語音、依四項標準評分
# ---------------------------------------------------------------------------

def _speaking_rows(student_id):
    return (SpeakingSubmission.query.filter_by(student_id=student_id)
            .order_by(SpeakingSubmission.submitted_at.desc()).all())


@app.route('/exam/<int:student_id>/speaking')
def speaking_home(student_id):
    student = get_student(student_id)
    history = _speaking_rows(student_id)
    best = {}
    for w in history:
        if w.overall is not None and w.overall > best.get(w.test_key, -1):
            best[w.test_key] = w.overall
    return render_template('speak_home.html', student=student, tests=speaking_bank.list_tests(),
                           best=best, history=history[:10], ai_ready=speaking_bank.ai_ready(),
                           ai_label=speaking_bank.ai_label(), provider=speaking_bank.ai_config()[0])


@app.route('/exam/<int:student_id>/speaking/<test_key>')
def speaking_test(student_id, test_key):
    student = get_student(student_id)
    test = speaking_bank.load_test(test_key)
    if not test:
        abort(404, description="找不到這份口說試卷")
    return render_template('speak_test.html', student=student, test=test,
                           provider=speaking_bank.ai_config()[0], ai_ready=speaking_bank.ai_ready())


@app.route('/exam/<int:student_id>/speaking/<test_key>/submit', methods=['POST'])
def speaking_submit(student_id, test_key):
    """交卷：表單裡有 meta（每題秒數與逐字稿的 JSON）和每題一個錄音檔 audio_<qid>。"""
    get_student(student_id)
    test = speaking_bank.load_test(test_key)
    if not test:
        return jsonify({'ok': False, 'error': '找不到這份口說試卷'}), 404
    try:
        meta = json.loads(request.form.get('meta', '{}'))
        used = max(0, int(request.form.get('seconds_used', 0)))
    except (ValueError, TypeError):
        return jsonify({'ok': False, 'error': '交卷資料格式不正確'}), 400
    sub = SpeakingSubmission(student_id=student_id, test_key=test_key, seconds_used=used,
                             notes=str(request.form.get('notes', ''))[:3000])
    db.session.add(sub)
    db.session.flush()          # 先拿到 id 才能建錄音資料夾
    folder = speaking_bank.sub_dir(sub.id)
    os.makedirs(folder, exist_ok=True)
    answers = []
    for qid in test['questions']:
        info = meta.get(qid) if isinstance(meta, dict) else None
        f = request.files.get('audio_' + qid)
        if not info and not f:
            continue
        info = info if isinstance(info, dict) else {}
        row = {'qid': qid, 'transcript': str(info.get('transcript', ''))[:5000], 'file': ''}
        try:
            row['seconds'] = max(0, min(600, int(info.get('seconds', 0))))
        except (TypeError, ValueError):
            row['seconds'] = 0
        if f:
            ext = speaking_bank.audio_ext(f.mimetype) or speaking_bank.audio_ext(info.get('mime', ''))
            if ext:
                name = f'{qid}.{ext}'
                f.save(os.path.join(folder, name))
                row['file'] = name
        answers.append(row)
    sub.answers = json.dumps(answers, ensure_ascii=False)
    db.session.commit()
    return jsonify({'ok': True, 'url': url_for('speaking_result', student_id=student_id, sub_id=sub.id)})


def _speaking_sub(student_id, sub_id):
    sub = db.session.get(SpeakingSubmission, sub_id)
    if not sub or sub.student_id != student_id:
        abort(404, description="找不到這次口說紀錄")
    return sub


@app.route('/exam/<int:student_id>/speaking/audio/<int:sub_id>/<filename>')
def speaking_audio(student_id, sub_id, filename):
    _speaking_sub(student_id, sub_id)
    return send_from_directory(speaking_bank.sub_dir(sub_id), filename,
                               mimetype=speaking_bank.audio_mime(filename))


@app.route('/exam/<int:student_id>/speaking/result/<int:sub_id>')
def speaking_result(student_id, sub_id):
    student = get_student(student_id)
    sub = _speaking_sub(student_id, sub_id)
    test = speaking_bank.load_test(sub.test_key)
    if not test:
        abort(404, description="找不到這份口說試卷")
    answers = {a['qid']: a for a in json.loads(sub.answers or '[]')}
    result = json.loads(sub.ai_result) if sub.ai_result else None
    return render_template('speak_result.html', student=student, sub=sub, test=test, answers=answers,
                           result=result, criteria=speaking_bank.CRITERIA, ai_ready=speaking_bank.ai_ready())


@app.route('/exam/<int:student_id>/speaking/result/<int:sub_id>/grade', methods=['POST'])
def speaking_grade(student_id, sub_id):
    """請 AI 老師聽錄音批改（約 1–2 分鐘）。結果存進資料庫，重開不會重複扣費。"""
    get_student(student_id)
    sub = _speaking_sub(student_id, sub_id)
    if sub.ai_status == 'done' and request.args.get('again') != '1':
        return jsonify({'ok': True})
    if not speaking_bank.ai_ready():
        return jsonify({'ok': False, 'error': 'AI 老師還沒設定：請在櫃台電腦雙擊 set_ai_key.bat 輸入 API 金鑰。'}), 400
    test = speaking_bank.load_test(sub.test_key)
    answers = []
    for a in json.loads(sub.answers or '[]'):
        if a['qid'] not in test['questions']:
            continue
        path = os.path.join(speaking_bank.sub_dir(sub.id), a['file']) if a.get('file') else ''
        answers.append({**a, 'path': path if path and os.path.exists(path) else ''})
    try:
        result = speaking_bank.grade(test, answers)
    except RuntimeError as e:
        sub.ai_status, sub.ai_error = 'error', str(e)[:300]
        db.session.commit()
        return jsonify({'ok': False, 'error': str(e)}), 502
    except Exception as e:  # 其他意外：記下來，不讓整頁壞掉
        app.logger.exception('口說批改失敗')
        sub.ai_status, sub.ai_error = 'error', f'批改時發生錯誤：{e}'[:300]
        db.session.commit()
        return jsonify({'ok': False, 'error': sub.ai_error}), 500
    sub.ai_result = json.dumps(result, ensure_ascii=False)
    sub.overall = result['overall']
    sub.ai_status, sub.ai_error = 'done', None
    sub.graded_at = datetime.utcnow()
    db.session.commit()
    return jsonify({'ok': True, 'overall': sub.overall})


# ---------------------------------------------------------------------------
# 單字測驗區（程式在 vocab_quiz.py）：只考學生在單字學習區學過的字
# ---------------------------------------------------------------------------
import vocab_quiz  # noqa: E402  放在最後，等上面的模型與輔助函式都定義好
vocab_quiz.register(app, db, dict(
    Student=Student, Vocabulary=Vocabulary, get_student=get_student, status_of=status_of,
    theme_condition=theme_condition, build_theme_list=build_theme_list,
    favorite_rows=favorite_rows, set_progress=set_progress, official_id_of=official_id_of,
    course_of=exams.course_of, locked_theme_ids=locked_theme_ids))

# 單字與例句的發音音檔（程式在 word_audio.py）：手機的瀏覽器語音不可靠，改由伺服器產生
import word_audio  # noqa: E402
app.register_blueprint(word_audio.bp)

# 英文零基礎的 ABC 與自然發音教學頁（程式在 phonics.py）
import phonics  # noqa: E402
phonics.register(app, get_student, Vocabulary, theme_condition, OFFICIAL_THEMES)


# 管理員後台（程式在 admin.py）：新增、編輯、刪除單字，要先輸入管理員密碼
import admin  # noqa: E402
admin.register(app, db, dict(
    Vocabulary=Vocabulary, LearningProgress=LearningProgress, Favorite=Favorite, exams=exams,
    OFFICIAL_THEMES=OFFICIAL_THEMES, official_id_of=official_id_of, theme_condition=theme_condition,
    find_cloze=vocab_quiz.find_cloze))


if __name__ == '__main__':
    app.run(debug=True)
