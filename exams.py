"""考試類型（雅思、多益…）的設定與「目前在哪個考試」的判斷。

網站會涵蓋多種考試，每種考試是 EXAMS 裡的一筆：
- course   對應單字資料的「課程」（Vocabulary.category），單字學習與單字測驗只看這個課程的字
- features 這個考試開放哪些功能：learn（單字學習與圖鑑）、vocab_quiz（單字測驗區）、exam（模擬測驗區）、
            phonics（ABC 與自然發音教學，零基礎用）、mock（日檢模擬考）
- ready    False 代表還在準備，選擇頁顯示「即將開放」
- 色系在 static/theme.css 用 :root[data-exam="…"] 覆寫，每個樣板的 <html> 都帶 data-exam

新增一種考試：在 EXAMS 加一筆、在 theme.css 加一組色系、匯入該課程的單字即可。
學生能用哪些考試、哪些功能由工作人員在後台開通（見下面的 access_of() 與 accounts.py），
其他頁面都透過 exams_for() / features_for() / current_exam() 判斷，不用逐頁修改。
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
    {"key": "topik", "name": "韓檢", "en": "TOPIK", "course": "TOPIK", "icon": "letter", "ready": True,
     "desc": "韓國語文能力測驗：1～6 級分級單字學習與單字測驗", "lang": "ko",
     "features": ["learn", "vocab_quiz"],
     # 分級字庫：每一級是一個主題（K1～K6，見 app.py 的 OFFICIAL_THEMES），可以逐級對學生開放
     "levels": [1, 2, 3, 4, 5, 6]},
    {"key": "jlpt", "name": "日檢", "en": "JLPT", "course": "JLPT", "icon": "letter", "ready": True,
     "desc": "日本語能力試驗：N5～N1 分級單字學習、單字測驗與模擬考", "lang": "ja",
     "features": ["learn", "vocab_quiz", "mock"],
     # 分級字庫：N5～N1 各是一個主題（app.py 的 OFFICIAL_THEMES），level 用 5～1，可以逐級對學生開放
     "levels": [5, 4, 3, 2, 1]},
    {"key": "basic", "name": "英文零基礎", "en": "Basic English", "course": "BASIC", "icon": "smile",
     "ready": True, "desc": "ABC 字母、自然發音，加上國中小程度 2,000 個生活單字",
     "features": ["phonics", "learn", "vocab_quiz"]},
    {"key": "general", "name": "一般英文", "en": "General English", "course": "GENERAL", "icon": "home",
     "ready": True, "desc": "零基礎之後的下一步：4,000 個日常生活單字",
     "features": ["learn", "vocab_quiz"]},
]
EXAM_BY_KEY = {e["key"]: e for e in EXAMS}
DEFAULT_EXAM = "ielts"

# 這些網址只屬於某個考試：進到這裡一律算那個考試（例如模擬測驗區是雅思的）
PATH_EXAM = [("/exam/", "ielts"), ("/phonics/", "basic"), ("/jlpt-mock/", "jlpt")]


# ---------------------------------------------------------------------------
# 學生的開通權限（工作人員在後台 /admin/students 設定，見 accounts.py）
#
# Student.access 是 JSON，每個考試一筆，例如：
#   {"jlpt": {"on": true, "features": ["learn", "vocab_quiz", "mock"], "levels": [5, 4],
#             "open_from": "2026-11-20", "course_start": "2026-11-20", "course_end": "2027-05-20"}}
# - features：開了哪些功能（learn、vocab_quiz、exam、phonics；mock 是日檢模擬考，見 jlpt_mock.py）
# - levels：分級考試（韓檢、日檢）開了哪幾級
# - open_from：開通日期，這天以前還不能用；course_end：課程結束日，過了就不能用（空的＝不限）
# Student.status：pending（等審核）、active（已開通）、rejected（退回）、disabled（停用）、
#                 demo（示範帳號：不用登入、全部開放，原本的測試學生是這種）
# ---------------------------------------------------------------------------

def today_tw():
    """台灣今天的日期（開通日期、課程結束日都用台灣時間判斷）。"""
    from datetime import datetime, timedelta, timezone
    return datetime.now(timezone(timedelta(hours=8))).date()


def is_open_account(student):
    """示範帳號：沒有開通設定，所有已準備好的考試都開放。"""
    return getattr(student, 'status', None) in (None, 'demo')


def access_of(student):
    """學生的開通設定（dict）。示範帳號回傳 None＝全部開放。"""
    if is_open_account(student):
        return None
    import json
    try:
        data = json.loads(getattr(student, 'access', None) or '{}')
    except ValueError:
        data = {}
    return data if isinstance(data, dict) else {}


def entry_state(entry, today=None):
    """某個考試的開通狀態：open、off（沒開）、not_yet（還沒到開通日期）、expired（課程已結束）。"""
    if not isinstance(entry, dict) or not entry.get('on'):
        return 'off'
    today = (today or today_tw()).isoformat()
    if entry.get('open_from') and today < entry['open_from']:
        return 'not_yet'
    if entry.get('course_end') and today > entry['course_end']:
        return 'expired'
    return 'open'


def features_for(student, exam):
    """這個學生在這個考試可以用的功能（依工作人員開通的項目）。"""
    access = access_of(student)
    if access is None:
        return list(exam["features"])
    if getattr(student, 'status', None) != 'active':
        return []
    entry = access.get(exam["key"])
    if entry_state(entry) != 'open':
        return []
    chosen = entry.get('features') or []
    return [f for f in exam["features"] if f in chosen]


def exams_for(student):
    """這個學生可以用的考試：示範帳號全部開放，其他學生只看工作人員開通、而且在課程期間內的考試。
    其他頁面都透過 exams_for() / can_use() / features_for() 判斷，不用逐頁修改。"""
    return [e for e in EXAMS if e["ready"] and features_for(student, e)]


def open_levels(student, exam):
    """這個學生在這個考試開通了哪幾級（例如韓檢 [1, 2]）。沒有分級的考試回傳 None。

    有開通設定的學生看 Student.access 裡該考試的 levels；示範帳號看舊欄位
    Student.unlocked_levels（JSON，例如 {"topik": [1, 2]}，沒設定過＝全部開放）。
    沒開通的等級在單字學習區會顯示「尚未開通」，也不會出現在單字測驗與收藏裡。"""
    levels = exam.get("levels")
    if not levels:
        return None
    access = access_of(student)
    if access is not None:
        chosen = (access.get(exam["key"]) or {}).get('levels')
        return [n for n in levels if isinstance(chosen, list) and n in chosen]
    import json
    try:
        setting = json.loads(getattr(student, 'unlocked_levels', None) or '{}')
    except ValueError:
        setting = {}
    chosen = setting.get(exam["key"]) if isinstance(setting, dict) else None
    if not isinstance(chosen, list):
        return list(levels)
    return [n for n in levels if n in chosen]


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
