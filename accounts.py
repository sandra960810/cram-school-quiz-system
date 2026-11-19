"""學生帳號：註冊、登入、每個頁面的權限檢查，以及工作人員審核開通（後台 /admin/students）。

流程：
1. 學生在 /register 填學號、名字、電子郵件（和原本選課報名系統同一個）、電話、校區、報名課程、密碼，
   送出後是「等待開通」（status=pending），還不能用任何功能
2. 工作人員登入後台（同一組管理員密碼），在「學生審核開通」看申請，依學生買的課勾選要開的功能、
   等級（韓檢、日檢）、開通日期與課程日期，按「開通」後學生才能用（status=active）
3. 學生用學號或電子郵件＋密碼登入（/login）。網址裡的學生編號一定要是自己的，
   不能改網址看別人的；工作人員登入時可以預覽任何學生的畫面

權限判斷都在 exams.py（access_of、features_for、exams_for、open_levels），這裡的 guard() 在每個請求前檢查：
- 網址或 API 帶的學生編號是不是登入的這個學生（或工作人員、示範帳號）
- 這個功能（背單字、單字測驗、模擬考、學發音）在目前的考試有沒有開通、是不是在課程期間
"""
import json
import re
import secrets
import time
from datetime import datetime

from flask import (Blueprint, abort, flash, g, jsonify, redirect, render_template, request, session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

import admin
from admin import bp as admin_bp, login_required as staff_required

bp = Blueprint('accounts', __name__)
_ = {}

CAMPUSES = ['台北', '桃園', '中壢', '南崁', '新竹']

# 學生報名的課程 → 對應網站上的考試（托福還沒開發，先只記錄）
COURSES = [
    {"key": "toeic", "name": "多益全方位", "exams": ["toeic"]},
    {"key": "ielts", "name": "雅思全方位", "exams": ["ielts"]},
    {"key": "toefl", "name": "托福全方位", "exams": [], "soon": True},
    {"key": "korean", "name": "韓文", "exams": ["topik"]},
    {"key": "japanese", "name": "日文", "exams": ["jlpt"]},
]
COURSE_BY_KEY = {c["key"]: c for c in COURSES}

# 後台每個考試可以開的項目：(項目代碼, 名稱, 對應的功能, 說明)。
# 日檢照櫃台的說法分成 A 單字學習與測驗、B 模考（jlpt_mock.py，N5～N1 每級多回，開哪幾回逐回勾選，存在 mock_open）
OPTIONS = {
    "ielts": [("learn", "單字學習", ["learn"], ""), ("vocab_quiz", "單字測驗", ["vocab_quiz"], ""),
              ("exam", "聽說讀寫模擬考", ["exam"], "")],
    "toeic": [("learn", "單字學習", ["learn"], ""), ("vocab_quiz", "單字測驗", ["vocab_quiz"], "")],
    # 韓檢模考：TOPIK I（初級 1～2 級）、TOPIK II（中高級 3～6 級）分開開通，和下面勾的單字等級無關
    "topik": [("learn", "單字學習", ["learn"], ""), ("vocab_quiz", "單字測驗", ["vocab_quiz"], ""),
              ("mock1", "TOPIK I 模考", ["mock1"], "初級（1～2 級）：聽力＋閱讀，滿分 200"),
              ("mock2", "TOPIK II 模考", ["mock2"], "中高級（3～6 級）：聽力＋寫作＋閱讀，滿分 300；寫作由 AI 老師批改")],
    "jlpt": [("vocab", "A 單字學習與測驗", ["learn", "vocab_quiz"], ""),
             ("mock", "B 模考", ["mock"], "N5～N1 模擬考，在下面「模考開放的回數」逐回勾選，和單字等級分開設定")],
    "basic": [("phonics", "學發音", ["phonics"], ""), ("learn", "單字學習", ["learn"], ""),
              ("vocab_quiz", "單字測驗", ["vocab_quiz"], "")],
    "general": [("learn", "單字學習", ["learn"], ""), ("vocab_quiz", "單字測驗", ["vocab_quiz"], "")],
}
LEVEL_LABELS = {"topik": lambda n: f"{n}級", "jlpt": lambda n: f"N{n}"}

STATUS_LABELS = {'pending': '等待審核', 'active': '已開通', 'rejected': '已退回', 'disabled': '已停用',
                 'demo': '示範帳號'}

# 網址開頭 → 功能。進這些頁面前會檢查目前的考試有沒有開這個功能
FEATURE_PATHS = [('/learn/', 'learn'), ('/vocab/', 'learn'), ('/vocab_themes/', 'learn'), ('/profile/', 'learn'),
                 ('/vocab-quiz/', 'vocab_quiz'), ('/api/vocab-quiz/', 'vocab_quiz'),
                 ('/exam/', 'exam'), ('/phonics/', 'phonics'), ('/jlpt-mock/', 'mock'),
                 ('/topik-mock/', ('mock1', 'mock2'))]   # 功能是一組時，開了其中一個就能進（細節在 topik_mock.py 判斷）

MAX_FAILS, LOCK_SECONDS = 8, 600
_fails = {}


# ---------------------------------------------------------------------------
# 小工具
# ---------------------------------------------------------------------------

def _json(value, default):
    try:
        data = json.loads(value or '')
    except (TypeError, ValueError):
        return default
    return data if isinstance(data, type(default)) else default


def courses_of(student):
    return [k for k in _json(getattr(student, 'courses', None), []) if k in COURSE_BY_KEY]


def course_names(student):
    return [COURSE_BY_KEY[k]["name"] for k in courses_of(student)]


def pw_tag(student):
    """登入時記下密碼雜湊的尾巴：工作人員重設密碼後，其他裝置的登入自動失效。"""
    return (student.password_hash or '')[-12:]


def current_student():
    """這個瀏覽器登入的學生（沒登入回傳 None）。"""
    if 'login_student' in g:
        return g.login_student
    st = None
    sid = session.get('student_id')
    if sid:
        st = _['db'].session.get(_['Student'], sid)
        if st and session.get('student_pw') != pw_tag(st):
            st = None
    g.login_student = st
    return st


def _csrf():
    if not session.get('form_csrf'):
        session['form_csrf'] = secrets.token_hex(16)
    return session['form_csrf']


def _check_csrf():
    if request.form.get('csrf') != session.get('form_csrf'):
        abort(400, description='表單已過期，請重新整理頁面再送出一次')


def _client_ip():
    return request.headers.get('Cf-Connecting-Ip') or request.remote_addr or '?'


def _norm_email(v):
    return (v or '').strip().lower()


def _clean_phone(v):
    return re.sub(r'[\s\-()]', '', v or '')


def _date_or_blank(v):
    v = (v or '').strip()
    if not v:
        return ''
    try:
        return datetime.strptime(v, '%Y-%m-%d').date().isoformat()
    except ValueError:
        return None


def _fmt_date(v):
    return v.replace('-', '/') if v else ''


def _safe_next(v):
    return v if v and v.startswith('/') and not v.startswith('//') else ''


def home_url(student):
    return url_for('dashboard', student_id=student.id)


# ---------------------------------------------------------------------------
# 每個請求前的權限檢查
# ---------------------------------------------------------------------------

def _deny(message, api, to):
    if api:
        return jsonify({"ok": False, "success": False, "error": message}), 403
    return redirect(to)


def guard():
    path = request.path
    if path.startswith('/static/') or path.startswith('/admin'):
        return None
    sid = (request.view_args or {}).get('student_id')
    api = path.startswith('/api/')
    if sid is None and api and request.method == 'POST':
        data = request.get_json(silent=True)
        if isinstance(data, dict):
            sid = data.get('student_id')
    if sid is None:
        return None
    try:
        sid = int(sid)
    except (TypeError, ValueError):
        return _deny('資料不正確', api, url_for('accounts.login'))
    student = _['db'].session.get(_['Student'], sid)
    if not student:
        return None   # 交給頁面本身回 404
    staff = admin.logged_in()
    if not staff and not _['exams'].is_open_account(student):
        me = current_student()
        if not me or me.id != student.id:
            return _deny('請先登入', api, url_for('accounts.login', next=request.full_path.rstrip('?')))
        if student.status != 'active':
            return _deny('帳號還沒開通', api, url_for('accounts.status'))
    # 功能有沒有開通
    feature = next((f for prefix, f in FEATURE_PATHS if path.startswith(prefix)), None)
    if feature:
        exams = _['exams']
        exam = exams.current_exam()
        allowed = exams.features_for(student, exam)
        wanted = feature if isinstance(feature, tuple) else (feature,)
        if not any(f in allowed for f in wanted):
            return _deny('這個功能還沒開通', api, url_for('dashboard', student_id=student.id, locked=exam["name"]))
    return None


def has_feature(feature):
    """樣板用：目前這個學生、這個考試有沒有開這個功能（用來藏起沒開通的按鈕）。"""
    sid = (request.view_args or {}).get('student_id')
    student = _['db'].session.get(_['Student'], sid) if sid is not None else None
    if not student:
        return True
    exams = _['exams']
    return feature in exams.features_for(student, exams.current_exam())


# ---------------------------------------------------------------------------
# 選擇考試頁上給學生看的課程資訊
# ---------------------------------------------------------------------------

def course_periods(student):
    """{考試 key: '課程期間 2026/11/20～2027/05/20'}，選擇考試頁的卡片上顯示。"""
    access = _['exams'].access_of(student)
    out = {}
    for key, entry in (access or {}).items():
        if not isinstance(entry, dict):
            continue
        a, b = _fmt_date(entry.get('course_start')), _fmt_date(entry.get('course_end'))
        if a or b:
            out[key] = f"課程期間 {a or '—'}～{b or '—'}"
    return out


def course_notes(student):
    """還不能用的課程，在選擇考試頁用一行字說明原因。"""
    exams = _['exams']
    access = exams.access_of(student)
    if access is None:
        return []
    notes = []
    for e in exams.EXAMS:
        entry = access.get(e["key"])
        state = exams.entry_state(entry)
        if state == 'not_yet':
            notes.append(f"{e['name']}：{_fmt_date(entry['open_from'])} 開通")
        elif state == 'expired':
            notes.append(f"{e['name']}：課程已在 {_fmt_date(entry['course_end'])} 結束")
    for k in courses_of(student):
        if COURSE_BY_KEY[k].get('soon'):
            notes.append(f"{COURSE_BY_KEY[k]['name']}：網站內容準備中")
    return notes


# ---------------------------------------------------------------------------
# 學生：登入、註冊、等待開通
# ---------------------------------------------------------------------------

@bp.route('/')
def index():
    me = current_student()
    if me and me.status == 'active':
        return redirect(home_url(me))
    return redirect(url_for('accounts.login'))


@bp.route('/login', methods=['GET', 'POST'])
def login():
    Student, db = _['Student'], _['db']
    # 舊的進入方式：補習班系統帶 token 進來（/login?token=…），照樣可以用，順便記住登入
    token = request.args.get('token')
    if token:
        st = Student.query.filter_by(token=token).first()
        if not st:
            return render_template('account_login.html', error='連結無效，請用學號或電子郵件登入。',
                                   csrf=_csrf(), next='', account='')
        if not _['exams'].is_open_account(st):
            session['student_id'], session['student_pw'] = st.id, pw_tag(st)
            session.permanent = True
        return redirect(home_url(st))

    nxt = _safe_next(request.values.get('next'))
    error, account = None, ''
    if request.method == 'POST':
        _check_csrf()
        account = (request.form.get('account') or '').strip()
        password = request.form.get('password') or ''
        ip = _client_ip()
        count, until = _fails.get(ip, [0, 0])
        st = None
        if account:
            st = Student.query.filter(Student.password_hash.isnot(None),
                                      (Student.student_no == account) |
                                      (db.func.lower(Student.email) == _norm_email(account))).first()
        if until > time.time():
            error = f'輸錯太多次，請 {int((until - time.time()) // 60) + 1} 分鐘後再試'
        elif st and check_password_hash(st.password_hash, password):
            _fails.pop(ip, None)
            session['student_id'], session['student_pw'] = st.id, pw_tag(st)
            session.permanent = True
            g.pop('login_student', None)
            if st.status != 'active':
                return redirect(url_for('accounts.status'))
            if nxt and re.match(rf'^/[\w-]+/{st.id}(/|$|\?)', nxt):
                return redirect(nxt)
            return redirect(home_url(st))
        else:
            count += 1
            _fails[ip] = [0, time.time() + LOCK_SECONDS] if count >= MAX_FAILS else [count, 0]
            error = '學號／電子郵件或密碼不對' if count < MAX_FAILS else '輸錯太多次，先鎖 10 分鐘'
    return render_template('account_login.html', error=error, csrf=_csrf(), next=nxt, account=account)


@bp.route('/logout', methods=['POST'])
def logout():
    for k in ('student_id', 'student_pw'):
        session.pop(k, None)
    return redirect(url_for('accounts.login'))


def _validate(form, student=None, need_password=True):
    """檢查註冊（或工作人員修改）的基本資料。回傳 (資料, 錯誤訊息清單)。"""
    Student, db = _['Student'], _['db']
    v = {
        'student_no': (form.get('student_no') or '').strip(),
        'name': (form.get('name') or '').strip(),
        'email': _norm_email(form.get('email')),
        'phone': _clean_phone(form.get('phone')),
        'campus': form.get('campus') or '',
        'courses': [k for k in form.getlist('courses') if k in COURSE_BY_KEY],
    }
    errors = []
    if not re.fullmatch(r'[A-Za-z0-9\-]{2,30}', v['student_no']):
        errors.append('學號只能有英文字母、數字（2～30 個字）')
    if not v['name'] or len(v['name']) > 50:
        errors.append('請填名字')
    if not re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+', v['email']) or len(v['email']) > 120:
        errors.append('電子郵件格式不對')
    if not re.fullmatch(r'\+?\d{8,15}', v['phone']):
        errors.append('電話請填 8～15 位數字')
    if v['campus'] not in CAMPUSES:
        errors.append('請選校區')
    if not v['courses']:
        errors.append('請至少勾一個報名課程')
    others = Student.query.filter(Student.status.notin_(('rejected',)))
    if student is not None:
        others = others.filter(Student.id != student.id)
    if v['student_no'] and others.filter(Student.student_no == v['student_no']).first():
        errors.append('這個學號已經註冊過了；忘記密碼請洽櫃台')
    if v['email'] and others.filter(db.func.lower(Student.email) == v['email']).first():
        errors.append('這個電子郵件已經註冊過了；忘記密碼請洽櫃台')
    if need_password:
        pw, pw2 = form.get('password') or '', form.get('password2') or ''
        if len(pw) < 6:
            errors.append('密碼至少 6 個字')
        elif pw != pw2:
            errors.append('兩次輸入的密碼不一樣')
        v['password'] = pw
    return v, errors


@bp.route('/register', methods=['GET', 'POST'])
def register_page():
    Student, db = _['Student'], _['db']
    values, errors = {'courses': []}, []
    if request.method == 'POST':
        _check_csrf()
        values, errors = _validate(request.form)
        if not errors:
            # 被退回過的同學號／同信箱重新申請：沿用那一筆，不會多出重複的學生
            st = Student.query.filter(Student.status == 'rejected',
                                      (Student.student_no == values['student_no']) |
                                      (db.func.lower(Student.email) == values['email'])).first()
            if not st:
                st = Student(token=secrets.token_urlsafe(24), name=values['name'])
                db.session.add(st)
            st.name, st.student_no, st.email = values['name'], values['student_no'], values['email']
            st.phone, st.campus = values['phone'], values['campus']
            st.courses = json.dumps(values['courses'])
            st.password_hash = generate_password_hash(values['password'])
            st.status, st.applied_at, st.access = 'pending', datetime.utcnow(), None
            db.session.commit()
            session['student_id'], session['student_pw'] = st.id, pw_tag(st)
            session.permanent = True
            return redirect(url_for('accounts.status'))
    return render_template('account_register.html', v=values, errors=errors, csrf=_csrf(),
                           campuses=CAMPUSES, course_list=COURSES)


@bp.route('/account/status')
def status():
    """註冊後、還沒開通（或被退回、停用）時看到的頁面。"""
    me = current_student()
    if not me:
        return redirect(url_for('accounts.login'))
    if me.status == 'active':
        return redirect(home_url(me))
    return render_template('account_status.html', me=me, courses=course_names(me), csrf=_csrf())


# ---------------------------------------------------------------------------
# 工作人員：審核開通（掛在後台 /admin 底下，用同一組管理員密碼）
# ---------------------------------------------------------------------------

TABS = [('pending', '等待審核'), ('active', '已開通'), ('other', '退回／停用／示範')]


@admin_bp.route('/students')
@staff_required
def students():
    Student = _['Student']
    tab = request.args.get('tab') or 'pending'
    q = (request.args.get('q') or '').strip()
    query = Student.query
    if tab == 'pending':
        query = query.filter(Student.status == 'pending')
    elif tab == 'active':
        query = query.filter(Student.status == 'active')
    else:
        tab = 'other'
        query = query.filter(Student.status.notin_(('pending', 'active')))
    if q:
        like = f'%{q}%'
        query = query.filter(Student.name.like(like) | Student.student_no.like(like) |
                             Student.email.like(like) | Student.phone.like(like))
    rows = query.order_by(Student.applied_at.desc(), Student.id.desc()).all()
    counts = {k: 0 for k, _l in TABS}
    for (st,) in _['db'].session.query(Student.status).all():
        counts[st if st in ('pending', 'active') else 'other'] += 1
    exams = _['exams']
    items = []
    for st in rows:
        access = exams.access_of(st) or {}
        opened = [e["name"] for e in exams.EXAMS if exams.entry_state(access.get(e["key"])) != 'off']
        items.append(dict(st=st, courses=course_names(st), opened=opened,
                          status=STATUS_LABELS.get(st.status, st.status or '')))
    return render_template('admin/students.html', items=items, tab=tab, tabs=TABS, counts=counts, q=q)


def _mock_tests(exam):
    """日檢模擬考每一級有哪幾回（看題庫檔），例如 [(5, ["N5", "N5-2", "N5-3"]), …]。其他考試回傳空清單。"""
    if exam["key"] != "jlpt":
        return []
    import jlpt_mock
    return [(lv, [jlpt_mock.tid(lv, r) for r in jlpt_mock.rounds(lv)]) for lv in exam["levels"]]


def _mock_rows(exam, entry, fresh):
    """審核頁「B 模考」底下逐回勾選的表格。還沒逐回設定過的，照舊依單字等級預先勾（和學生現在看到的一樣）。"""
    chosen = entry.get("mock_open")
    rows = []
    for lv, ids in _mock_tests(exam):
        cells = []
        for i, t in enumerate(ids, 1):
            if fresh:
                on = True
            elif isinstance(chosen, list):
                on = t in chosen
            else:
                on = "mock" in (entry.get("features") or []) and lv in (entry.get("levels") or [])
            cells.append(dict(id=t, label=f"第 {i} 回", checked=on))
        if cells:
            rows.append(dict(label=LEVEL_LABELS["jlpt"](lv), cells=cells))
    return rows


def _exam_sections(student, form_access=None):
    """審核頁每個考試的區塊：要開哪些項目、等級、日期。還沒設定過的申請，依報名課程先幫忙勾好。"""
    exams = _['exams']
    access = form_access if form_access is not None else (exams.access_of(student) or {})
    fresh = student.status == 'pending' and not access
    wanted = {x for k in courses_of(student) for x in COURSE_BY_KEY[k]["exams"]}
    today = exams.today_tw().isoformat()
    sections = []
    for e in exams.EXAMS:
        if e["key"] not in OPTIONS:
            continue
        entry = access.get(e["key"]) if isinstance(access.get(e["key"]), dict) else {}
        if fresh and e["key"] in wanted:
            entry = {"on": True, "features": [f for _k, _n, fs, _d in OPTIONS[e["key"]] for f in fs],
                     "levels": list(e.get("levels") or []), "open_from": today}
        feats = entry.get("features") or []
        options = [dict(key=k, name=n, desc=d, checked=all(f in feats for f in fs))
                   for k, n, fs, d in OPTIONS[e["key"]]]
        levels = [dict(n=n, label=LEVEL_LABELS[e["key"]](n), checked=n in (entry.get("levels") or []))
                  for n in (e.get("levels") or [])]
        sections.append(dict(exam=e, on=bool(entry.get("on")), wanted=e["key"] in wanted, options=options,
                             levels=levels, mock=_mock_rows(e, entry, fresh and e["key"] in wanted),
                             open_from=entry.get("open_from", ''),
                             course_start=entry.get("course_start", ''), course_end=entry.get("course_end", ''),
                             state=exams.entry_state(entry)))
    return sections


def _access_from_form(form):
    """把審核頁的勾選轉成 Student.access。回傳 (access, 錯誤訊息清單)。"""
    exams = _['exams']
    access, errors = {}, []
    for e in exams.EXAMS:
        key = e["key"]
        if key not in OPTIONS:
            continue
        feats = []
        for k, _n, fs, _d in OPTIONS[key]:
            if form.get(f'{key}__opt__{k}'):
                feats += fs
        levels = [n for n in (e.get("levels") or []) if form.get(f'{key}__lv__{n}')]
        dates = {}
        for field, label in (('open_from', '開通日期'), ('course_start', '課程開始日'), ('course_end', '課程結束日')):
            d = _date_or_blank(form.get(f'{key}__{field}'))
            if d is None:
                errors.append(f"{e['name']}的{label}格式不對")
                d = ''
            dates[field] = d
        on = bool(form.get(f'{key}__on'))
        if on and not feats:
            errors.append(f"{e['name']}打開了，但沒有勾任何項目")
        if on and e.get("levels") and not levels and any(f in ('learn', 'vocab_quiz') for f in feats):
            errors.append(f"{e['name']}要至少勾一個等級")
        if dates['course_start'] and dates['course_end'] and dates['course_end'] < dates['course_start']:
            errors.append(f"{e['name']}的課程結束日比開始日還早")
        tests = _mock_tests(e)
        mock_open = [t for _lv, ids in tests for t in ids if form.get(f'{key}__mock__{t}')]
        if on and tests and 'mock' in feats and not mock_open:
            errors.append(f"{e['name']}的模考要至少勾一回")
        if on or feats or any(dates.values()):
            access[key] = dict(on=on, features=feats, levels=levels, **dates)
            if tests:
                access[key]['mock_open'] = mock_open
    return access, errors


@admin_bp.route('/students/<int:sid>', methods=['GET', 'POST'])
@staff_required
def student_review(sid):
    Student, db = _['Student'], _['db']
    st = db.session.get(Student, sid)
    if not st:
        abort(404)
    errors, info, form_access = [], None, None
    if request.method == 'POST':
        action = request.form.get('action', 'save')
        if action in ('reject', 'disable', 'reopen', 'demo_off'):
            st.status = {'reject': 'rejected', 'disable': 'disabled', 'demo_off': 'disabled',
                         'reopen': ('demo' if not st.password_hash else
                                    'active' if st.approved_at else 'pending')}[action]
            st.staff_note = (request.form.get('staff_note') or '').strip()[:2000] or st.staff_note
            db.session.commit()
            flash({'reject': f'已退回 {st.name} 的申請', 'disable': f'已停用 {st.name}',
                   'demo_off': '示範帳號已停用（分享連結會看不到內容）',
                   'reopen': f'{st.name} 已恢復'}[action])
            return redirect(url_for('admin.student_review', sid=st.id))
        is_demo = st.status == 'demo'
        if not is_demo:
            info, errors = _validate(request.form, student=st, need_password=False)
            newpw = request.form.get('new_password') or ''
            if newpw and len(newpw) < 6:
                errors.append('新密碼至少 6 個字')
        form_access, more = _access_from_form(request.form)
        errors += more
        if action == 'approve' and not any(v.get('on') and v.get('features') for v in form_access.values()):
            errors.append('至少要打開一個課程才能開通')
        if not errors:
            if not is_demo:
                st.name, st.student_no, st.email = info['name'], info['student_no'], info['email']
                st.phone, st.campus, st.courses = info['phone'], info['campus'], json.dumps(info['courses'])
                if newpw:
                    st.password_hash = generate_password_hash(newpw)
                st.access = json.dumps(form_access, ensure_ascii=False)
                if action == 'approve':
                    st.status = 'active'
                    st.approved_at = st.approved_at or datetime.utcnow()
            st.staff_note = (request.form.get('staff_note') or '').strip()[:2000]
            db.session.commit()
            flash(f'已開通 {st.name}，學生登入後就能使用' if action == 'approve' else '已儲存')
            return redirect(url_for('admin.student_review', sid=st.id))
    v = info or dict(student_no=st.student_no or '', name=st.name, email=st.email or '', phone=st.phone or '',
                     campus=st.campus or '', courses=courses_of(st))
    return render_template('admin/student_review.html', st=st, v=v, errors=errors,
                           sections=_exam_sections(st, form_access), campuses=CAMPUSES, course_list=COURSES,
                           status=STATUS_LABELS.get(st.status, st.status or ''),
                           wanted_soon=[COURSE_BY_KEY[k]["name"] for k in courses_of(st)
                                        if COURSE_BY_KEY[k].get('soon')])


# ---------------------------------------------------------------------------

def register(app, db, deps):
    """由 app.py 呼叫。deps：Student、get_student、exams。"""
    _.update(deps, app=app, db=db)
    app.before_request(guard)
    app.jinja_env.globals['has_feature'] = has_feature
    app.jinja_env.globals['login_student'] = current_student
    app.register_blueprint(bp)
