"""考試類型（雅思、多益…）的設定與「目前在哪個考試」的判斷。

網站會涵蓋多種考試，每種考試是 EXAMS 裡的一筆：
- course   對應單字資料的「課程」（Vocabulary.category），單字學習與單字測驗只看這個課程的字
- features 這個考試開放哪些功能：learn（單字學習與圖鑑）、vocab_quiz（單字測驗區）、exam（模擬測驗區）
- ready    False 代表還在準備，選擇頁顯示「即將開放」
- 色系在 static/theme.css 用 :root[data-exam="…"] 覆寫，每個樣板的 <html> 都帶 data-exam

新增一種考試：在 EXAMS 加一筆、在 theme.css 加一組色系、匯入該課程的單字即可。
之後做學生登入與後台開通權限時，只要改 exams_for() 依學生的權限回傳可用的考試，
其他頁面都透過 exams_for() / current_exam() 判斷，不用逐頁修改。
"""
from flask import g, request

COOKIE = 'exam'

EXAMS = [
    {"key": "ielts", "name": "雅思", "en": "IELTS", "course": "IELTS", "icon": "globe", "ready": True,
     "desc": "單字學習、單字測驗、聽說讀寫模擬測驗",
     "features": ["learn", "vocab_quiz", "exam"]},
    {"key": "toeic", "name": "多益", "en": "TOEIC", "course": "TOEIC", "icon": "briefcase", "ready": True,
     "desc": "職場情境單字學習與單字測驗",
     "features": ["learn", "vocab_quiz"]},
    {"key": "topik", "name": "韓檢", "en": "TOPIK", "course": "TOPIK", "icon": "letter", "ready": False,
     "desc": "韓國語文能力測驗", "features": []},
    {"key": "jlpt", "name": "日檢", "en": "JLPT", "course": "JLPT", "icon": "letter", "ready": False,
     "desc": "日本語能力試驗", "features": []},
    {"key": "basic", "name": "英文零基礎", "en": "Basic English", "course": "BASIC", "icon": "smile",
     "ready": False, "desc": "從字母、發音與生活單字開始", "features": []},
]
EXAM_BY_KEY = {e["key"]: e for e in EXAMS}
DEFAULT_EXAM = "ielts"

# 這些網址只屬於某個考試：進到這裡一律算那個考試（例如模擬測驗區是雅思的）
PATH_EXAM = [("/exam/", "ielts")]


def exams_for(student):
    """這個學生可以用的考試。目前還沒有登入與權限，開放所有已準備好的考試。
    之後接後台權限時改這裡就好（例如讀 student 的開通紀錄）。"""
    return [e for e in EXAMS if e["ready"]]


def can_use(student, exam_key):
    return any(e["key"] == exam_key for e in exams_for(student))


def current_exam():
    """這次請求屬於哪個考試：網址決定的優先，其次是 ?exam=，再來是 cookie（選擇考試時記下來的）。"""
    if 'exam' in g:
        return g.exam
    key = None
    for prefix, k in PATH_EXAM:
        if request.path.startswith(prefix):
            key = k
    key = key or request.args.get('exam') or request.cookies.get(COOKIE)
    exam = EXAM_BY_KEY.get(key)
    if not exam or not exam["ready"]:
        exam = EXAM_BY_KEY[DEFAULT_EXAM]
    g.exam = exam
    return exam


def use_exam(exam_key):
    """把這次請求切到某個考試（選擇考試頁進入時用）。"""
    g.exam = EXAM_BY_KEY[exam_key]
    return g.exam


def course_of(student):
    """單字學習與測驗要看哪個課程的字。"""
    return current_exam()["course"]


def init_app(app):
    @app.context_processor
    def _inject():
        return {"exam": current_exam(), "exams_all": EXAMS}

    @app.after_request
    def _remember(resp):
        # 記住目前的考試，之後進單字學習、單字測驗都會留在同一個考試
        if 'exam' in g and request.cookies.get(COOKIE) != g.exam["key"] \
                and not any(request.path.startswith(p) for p, _k in PATH_EXAM) \
                and resp.mimetype == 'text/html':
            resp.set_cookie(COOKIE, g.exam["key"], max_age=365 * 24 * 3600, samesite='Lax')
        return resp
