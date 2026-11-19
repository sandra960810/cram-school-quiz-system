"""管理員後台：登入與單字的新增、編輯、刪除（題庫的編輯在 admin_bank.py）。

網址一律在 /admin 底下，要先登入管理員密碼才能進去：
- 網站會透過 share.bat 的公開連結給外面的人看，學生又只靠網址裡的編號辨識，
  所以後台一定要有密碼，不能讓拿到連結的人改資料
- 第一次使用時要「在櫃台電腦本機」（http://127.0.0.1:5000/admin）設定密碼；
  從公開連結進來的人不能設定密碼
- 密碼只存雜湊值在 instance/admin.json（不進 git）；忘記密碼雙擊 reset_admin_password.bat
- 連續輸錯 5 次，該來源鎖 10 分鐘

單字的規則（學生的學習紀錄與收藏都綁在單字的編號上）：
- 編輯：直接改那一筆，編號不變，學生紀錄自動跟著
- 刪除：不真的刪，移到「回收區」（課程改成 TRASH:原課程），學生看不到，但紀錄都還在，
  之後可以從回收區救回
- 管理員動過的字會標 admin_locked，並記下它原本在單字檔裡的位置（src_key）。
  run.bat 每次啟動都會重新匯入單字檔，import_sheet.py 遇到這些字會跳過，
  所以後台改的內容、刪掉的字都不會被單字檔蓋回去
"""
import json
import os
import re
import secrets
import time
from functools import wraps

from flask import (Blueprint, abort, flash, redirect, render_template, request, session, url_for)
from sqlalchemy import func, or_
from werkzeug.security import check_password_hash, generate_password_hash

bp = Blueprint('admin', __name__, url_prefix='/admin')
_ = {}   # register() 放進來的主程式物件

TRASH = 'TRASH:'
LEVELS = ['不分級', '基礎級', '中級', '中高級', '進階級', '1級', '2級', '3級', '4級', '5級', '6級',   # 1～6 級：韓檢
          'N5', 'N4', 'N3', 'N2', 'N1']   # 日檢
PAGE_SIZE = 50
MAX_FAILS, LOCK_SECONDS = 5, 600
_fails = {}   # 來源 IP → [連續失敗次數, 鎖到什麼時候]


# ---------------------------------------------------------------------------
# 密碼與登入
# ---------------------------------------------------------------------------

def _admin_file():
    return os.path.join(_['app'].instance_path, 'admin.json')


def _load_admin():
    try:
        with open(_admin_file(), encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def has_password():
    return bool(_load_admin().get('password_hash'))


def _save_password(pw):
    os.makedirs(os.path.dirname(_admin_file()), exist_ok=True)
    data = _load_admin()
    data['password_hash'] = generate_password_hash(pw)
    data['version'] = secrets.token_hex(8)   # 換密碼後，舊的登入全部失效
    with open(_admin_file(), 'w', encoding='utf-8') as f:
        json.dump(data, f)
    return data['version']


def is_local_request():
    """是不是在櫃台電腦本機開的（不是經過 Cloudflare 公開連結進來的）。
    cloudflared 也是從本機連到網站，所以要看它加的標頭來分辨。"""
    if request.remote_addr not in ('127.0.0.1', '::1'):
        return False
    return not any(h in request.headers for h in ('Cf-Connecting-Ip', 'Cf-Ray', 'X-Forwarded-For'))


def client_ip():
    return request.headers.get('Cf-Connecting-Ip') or request.remote_addr or '?'


STAFF_SESSION_SECONDS = 8 * 3600   # 工作人員登入 8 小時後要重新輸入密碼（學生的登入可以維持較久）
# 原本編輯單字、題庫的後台先暫停（2026-11 改成學生審核開通）。程式與資料都保留，改成 True 就恢復
EDITOR_ENABLED = False


def logged_in():
    v = _load_admin().get('version')
    if not v or session.get('admin') != v:
        return False
    return time.time() - session.get('admin_at', 0) < STAFF_SESSION_SECONDS


def login_required(view):
    @wraps(view)
    def wrapper(*a, **kw):
        if not logged_in():
            return redirect(url_for('admin.login', next=request.full_path))
        if request.method == 'POST' and request.form.get('csrf') != session.get('admin_csrf'):
            abort(400, description='表單已過期，請重新整理頁面再送出一次')
        return view(*a, **kw)
    return wrapper


def _start_session(version):
    # 只換掉工作人員的登入資料，同一個瀏覽器裡學生的登入不受影響
    for k in ('admin', 'admin_csrf', 'admin_at'):
        session.pop(k, None)
    session.permanent = True
    session['admin'] = version
    session['admin_at'] = time.time()
    session['admin_csrf'] = secrets.token_hex(16)


@bp.app_context_processor
def _inject():
    return {'admin_csrf': session.get('admin_csrf', '')}


@bp.route('/setup', methods=['GET', 'POST'])
def setup():
    if has_password():
        return redirect(url_for('admin.login'))
    local = is_local_request()
    error = None
    if request.method == 'POST' and local:
        pw, pw2 = request.form.get('password', ''), request.form.get('password2', '')
        if len(pw) < 6:
            error = '密碼至少 6 個字'
        elif pw != pw2:
            error = '兩次輸入的密碼不一樣'
        else:
            _start_session(_save_password(pw))
            return redirect(url_for('admin.home'))
    return render_template('admin/setup.html', local=local, error=error)


@bp.route('/login', methods=['GET', 'POST'])
def login():
    if not has_password():
        return redirect(url_for('admin.setup'))
    nxt = request.args.get('next') or ''
    # 回到原本要去的頁面（後台，或工作人員要預覽的學生頁面）；不接受外部網址
    if not nxt.startswith('/') or nxt.startswith('//'):
        nxt = url_for('admin.home')
    error = None
    if request.method == 'POST':
        ip = client_ip()
        count, until = _fails.get(ip, [0, 0])
        if until > time.time():
            error = f'輸錯太多次，請 {int((until - time.time()) // 60) + 1} 分鐘後再試'
        elif check_password_hash(_load_admin()['password_hash'], request.form.get('password', '')):
            _fails.pop(ip, None)
            _start_session(_load_admin()['version'])
            return redirect(nxt)
        else:
            count += 1
            _fails[ip] = [0, time.time() + LOCK_SECONDS] if count >= MAX_FAILS else [count, 0]
            error = '密碼不對' if count < MAX_FAILS else '輸錯太多次，先鎖 10 分鐘'
    return render_template('admin/login.html', error=error)


@bp.route('/logout', methods=['POST'])
def logout():
    for k in ('admin', 'admin_csrf', 'admin_at'):
        session.pop(k, None)
    return redirect(url_for('admin.login'))


@bp.route('/password', methods=['GET', 'POST'])
@login_required
def change_password():
    error = None
    if request.method == 'POST':
        old, pw, pw2 = (request.form.get(k, '') for k in ('old', 'password', 'password2'))
        if not check_password_hash(_load_admin()['password_hash'], old):
            error = '目前的密碼不對'
        elif len(pw) < 6:
            error = '新密碼至少 6 個字'
        elif pw != pw2:
            error = '兩次輸入的新密碼不一樣'
        else:
            _start_session(_save_password(pw))
            flash('密碼已更新')
            return redirect(url_for('admin.home'))
    return render_template('admin/password.html', error=error)


# ---------------------------------------------------------------------------
# 後台首頁
# ---------------------------------------------------------------------------

def courses():
    """[(課程代碼, 考試名稱, 考試 key)]，依考試選擇頁的順序。"""
    return [(e['course'], e['name'], e['key']) for e in _['exams'].EXAMS if e['ready']]


def course_name(code):
    return next((n for c, n, _k in courses() if c == code), code)


@bp.route('/')
@login_required
def home():
    """後台首頁＝學生審核開通（accounts.py）。"""
    return redirect(url_for('admin.students'))


@bp.before_request
def _editor_paused():
    """單字、題庫編輯先暫停：進去一律回到學生審核頁。"""
    ep = request.endpoint or ''
    if not EDITOR_ENABLED and (ep.startswith('admin.vocab') or ep.startswith('admin.bank')):
        flash('編輯單字、題目的後台目前暫停使用，後台改成學生審核開通。', 'warn')
        return redirect(url_for('admin.students'))


@bp.route('/vocab/')
@login_required
def vocab_home():
    V = _['Vocabulary']
    counts = dict(_['db'].session.query(V.category, func.count(V.id)).group_by(V.category).all())
    cards = [{'course': c, 'name': n, 'exam': k, 'count': counts.get(c, 0),
              'trash': counts.get(TRASH + c, 0)} for c, n, k in courses()]
    return render_template('admin/home.html', cards=cards)


# ---------------------------------------------------------------------------
# 單字
# ---------------------------------------------------------------------------

def themes_of(course):
    """這個課程可以選的主題：官方主題，加上資料庫裡實際有、但不在官方清單的主題。"""
    V = _['Vocabulary']
    out = [(f"{t['id']} {t['name']}", f"{t['id']} {t['name']}")
           for t in _['OFFICIAL_THEMES'] if t['course'] == course]
    known = {k for k, _l in out}
    for (name,) in _['db'].session.query(V.theme).filter(V.category == course).distinct():
        oid = _['official_id_of'](name)
        if oid is None and name not in known:
            out.append((name, name))
            known.add(name)
    return out


def normalize_theme(course, value):
    """'02'、'02 環境' 都轉成官方名稱 '02 環境與自然生態'。"""
    code = (value or '').split(' ', 1)[0]
    for t in _['OFFICIAL_THEMES']:
        if t['course'] == course and t['id'] == code:
            return f"{t['id']} {t['name']}"
    return value


def src_key_of(v):
    course = v.category[len(TRASH):] if v.category.startswith(TRASH) else v.category
    return f"{course}|{v.theme}|{v.word.strip().lower()}"


def lock(v):
    """標成管理員改過：之後匯入單字檔時跳過這個字，不會被蓋回去。"""
    if not v.src_key:
        v.src_key = src_key_of(v)
    v.admin_locked = True


def usage_of(v):
    db, LP, Fav = _['db'], _['LearningProgress'], _['Favorite']
    learned = db.session.query(func.count(func.distinct(LP.student_id))).filter(LP.vocab_id == v.id).scalar()
    fav = db.session.query(func.count(Fav.id)).filter(Fav.vocab_id == v.id).scalar()
    return learned or 0, fav or 0


def duplicate_of(course, word, exclude_id=None):
    V = _['Vocabulary']
    q = V.query.filter(V.category == course, func.lower(func.trim(V.word)) == word.strip().lower())
    if exclude_id:
        q = q.filter(V.id != exclude_id)
    return q.first()


def safe_back(value):
    """「回上一頁」只接受後台裡的網址，避免被拿來導到別的網站。"""
    value = value or ''
    return value if value.startswith('/admin/') and not value.startswith('//') else ''


def _course_or_404(course):
    if course not in {c for c, _n, _k in courses()}:
        abort(404, description='沒有這個課程')
    return course


@bp.route('/vocab/<course>')
@login_required
def vocab_list(course):
    V, db = _['Vocabulary'], _['db']
    trash = request.args.get('trash') == '1'
    if not trash:
        _course_or_404(course)
    cat = TRASH + course if trash else course
    theme = request.args.get('theme', '')
    q = (request.args.get('q') or '').strip()
    page = max(1, request.args.get('page', 1, type=int))

    query = V.query.filter(V.category == cat)
    if theme:
        query = query.filter(_['theme_condition'](theme.split(' ', 1)[0]
                                                 if _['official_id_of'](theme) else theme))
    if q:
        like = f"%{q}%"
        query = query.filter(or_(V.word.ilike(like), V.meaning.ilike(like), V.meaning_en.ilike(like),
                                 V.reading.ilike(like)))
    total = query.count()
    rows = (query.order_by(func.lower(V.word), V.id)
            .offset((page - 1) * PAGE_SIZE).limit(PAGE_SIZE).all())
    learned = {}
    if rows:
        LP = _['LearningProgress']
        learned = dict(db.session.query(LP.vocab_id, func.count(func.distinct(LP.student_id)))
                       .filter(LP.vocab_id.in_([r.id for r in rows])).group_by(LP.vocab_id).all())
    pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    return render_template('admin/vocab_list.html', course=course, course_label=course_name(course),
                           courses=courses(), themes=themes_of(course), theme=theme, q=q, rows=rows,
                           total=total, page=page, pages=pages, learned=learned, trash=trash,
                           trash_count=V.query.filter(V.category == TRASH + course).count())


def _form_values(course):
    f = request.form
    vals = {k: (f.get(k) or '').strip() for k in
            ('word', 'pos', 'meaning_zh', 'meaning_en', 'sentence', 'sentence_zh', 'theme', 'level', 'reading')}
    vals['theme'] = normalize_theme(course, vals['theme'])
    vals['is_ja'] = course == 'JLPT'
    errors = []
    if not vals['word']:
        errors.append('請填單字')
    if not (vals['meaning_zh'] or vals['meaning_en']):
        errors.append('中文意思和英文解釋至少要填一個')
    if not vals['theme']:
        errors.append('請選主題')
    if vals['level'] not in LEVELS:
        vals['level'] = '不分級'
    if course == 'JLPT' and vals['reading'] and not JA_READING.fullmatch(vals['reading']):
        errors.append('「讀音」請只填假名（平假名或片假名），兩種讀法用「／」隔開，例如 あした／あす')
    for k, limit in (('word', 100), ('pos', 20), ('meaning_zh', 200), ('meaning_en', 500), ('reading', 100),
                     ('sentence', 500), ('sentence_zh', 500), ('theme', 50)):
        if len(vals[k]) > limit:
            errors.append(f'「{FIELD_NAMES[k]}」太長了（最多 {limit} 個字）')
    return vals, errors


JA_READING = re.compile(r'[ぁ-ゖァ-ヺー・／]+')
FIELD_NAMES = {'word': '單字', 'pos': '詞性', 'meaning_zh': '中文意思', 'meaning_en': '英文解釋', 'reading': '讀音',
               'sentence': '例句', 'sentence_zh': '例句中譯', 'theme': '主題'}


def _apply(v, vals):
    v.word = vals['word']
    v.pos = vals['pos'] or None
    v.meaning = vals['meaning_zh'] or vals['meaning_en']
    v.meaning_en = vals['meaning_en'] or None
    v.sentence = vals['sentence'] or None
    v.sentence_zh = vals['sentence_zh'] or None
    v.theme = vals['theme']
    v.level = vals['level']
    if v.category == 'JLPT':
        v.reading = vals.get('reading') or None
        # 日文例句要用 [寫法|讀音] 標出例句填空挖掉的地方；沒標而且例句裡有原字時自動標上
        s = v.sentence or ''
        if s and '[' not in s and v.word in s:
            mark = f'[{v.word}|{v.reading.split("／")[0]}]' if v.reading and v.reading != v.word else f'[{v.word}]'
            v.sentence = s.replace(v.word, mark, 1)


def _hints(vals):
    """不擋存檔、但提醒管理員的事。"""
    hints = []
    if vals.get('sentence') and vals.get('is_ja'):
        if '[' not in vals['sentence'] and vals['word'] not in vals['sentence']:
            hints.append('日文例句請用 [寫法|讀音] 標出「例句填空」要挖掉的地方，例如：毎朝コーヒーを[飲みます|のみます]。'
                         '沒標的話，單字測驗不會出這個字的例句填空題（其他題型照常）。')
    elif vals.get('sentence') and not _['find_cloze'](vals['word'], vals['sentence']):
        hints.append('例句裡找不到這個單字，單字測驗不會出這個字的「例句填空」題（其他題型照常）。')
    return hints


def _edit_values(v):
    zh = v.meaning if v.meaning != (v.meaning_en or '') else ''
    sentence = v.sentence or ''
    if sentence.startswith('無例句'):
        sentence = ''
    return dict(word=v.word, pos=v.pos or '', meaning_zh=zh, meaning_en=v.meaning_en or '',
                sentence=sentence, sentence_zh=v.sentence_zh or '', theme=v.theme, level=v.level,
                reading=v.reading or '', is_ja=v.category == 'JLPT')


@bp.route('/vocab/<course>/new', methods=['GET', 'POST'])
@login_required
def vocab_new(course):
    _course_or_404(course)
    V, db = _['Vocabulary'], _['db']
    vals = {'theme': request.args.get('theme', ''), 'level': '不分級'}
    errors = []
    if request.method == 'POST':
        vals, errors = _form_values(course)
        dup = vals['word'] and duplicate_of(course, vals['word'])
        if dup:
            errors.append(f'「{dup.word}」已經在這個課程裡了（主題：{dup.theme}），同一個課程不能有重複的字。')
        if not errors:
            v = V(category=course, level='不分級', theme='', word='', meaning='')
            _apply(v, vals)
            lock(v)
            db.session.add(v)
            db.session.commit()
            flash(f'已新增「{v.word}」')
            for h in _hints(vals):
                flash(h, 'warn')
            if request.form.get('again'):
                return redirect(url_for('admin.vocab_new', course=course, theme=v.theme))
            return redirect(url_for('admin.vocab_list', course=course, theme=v.theme, q=v.word))
    return render_template('admin/vocab_edit.html', course=course, course_label=course_name(course),
                           themes=themes_of(course), levels=LEVELS, vals=vals, errors=errors, v=None)


@bp.route('/vocab/<course>/<int:vocab_id>', methods=['GET', 'POST'])
@login_required
def vocab_edit(course, vocab_id):
    V, db = _['Vocabulary'], _['db']
    v = db.session.get(V, vocab_id)
    if not v or v.category != course:
        abort(404, description='找不到這個單字（可能已經在回收區）')
    errors = []
    vals = _edit_values(v)
    if request.method == 'POST':
        vals, errors = _form_values(course)
        dup = vals['word'] and duplicate_of(course, vals['word'], exclude_id=v.id)
        if dup:
            errors.append(f'「{dup.word}」已經在這個課程裡了（主題：{dup.theme}），同一個課程不能有重複的字。')
        if not errors:
            lock(v)            # 先記下原本在單字檔裡的位置，再改內容
            _apply(v, vals)
            db.session.commit()
            flash(f'已儲存「{v.word}」')
            for h in _hints(vals):
                flash(h, 'warn')
            return redirect(safe_back(request.form.get('back')) or url_for('admin.vocab_list', course=course))
    learned, fav = usage_of(v)
    return render_template('admin/vocab_edit.html', course=course, course_label=course_name(course),
                           themes=themes_of(course), levels=LEVELS, vals=vals, errors=errors, v=v,
                           learned=learned, fav=fav, hints=_hints(vals) if request.method == 'GET' else [],
                           back=safe_back(request.args.get('back') or request.form.get('back')))


@bp.route('/vocab/<course>/<int:vocab_id>/delete', methods=['POST'])
@login_required
def vocab_delete(course, vocab_id):
    V, db = _['Vocabulary'], _['db']
    v = db.session.get(V, vocab_id)
    if not v or v.category != course:
        abort(404)
    lock(v)
    v.category = TRASH + course
    db.session.commit()
    flash(f'已把「{v.word}」移到回收區（學生的紀錄都保留，隨時可以救回）')
    return redirect(safe_back(request.form.get('back')) or url_for('admin.vocab_list', course=course))


@bp.route('/vocab/<course>/<int:vocab_id>/restore', methods=['POST'])
@login_required
def vocab_restore(course, vocab_id):
    V, db = _['Vocabulary'], _['db']
    v = db.session.get(V, vocab_id)
    if not v or v.category != TRASH + course:
        abort(404)
    dup = duplicate_of(course, v.word)
    if dup:
        flash(f'不能救回：課程裡已經有「{dup.word}」了（主題：{dup.theme}）。要救回請先刪掉那一筆。', 'warn')
    else:
        v.category = course
        db.session.commit()
        flash(f'已救回「{v.word}」')
    return redirect(url_for('admin.vocab_list', course=course, trash=1))


def register(app, db, deps):
    """由 app.py 最後面呼叫。deps：Vocabulary、LearningProgress、Favorite、exams、OFFICIAL_THEMES…"""
    _.update(deps, app=app, db=db)
    if not app.secret_key:
        path = os.path.join(app.instance_path, 'secret_key.txt')
        try:
            with open(path, encoding='utf-8') as f:
                key = f.read().strip()
        except OSError:
            key = ''
        if not key:
            key = secrets.token_hex(32)
            os.makedirs(app.instance_path, exist_ok=True)
            with open(path, 'w', encoding='utf-8') as f:
                f.write(key)
        app.secret_key = key
    # 學生登入維持 30 天；工作人員另外在 logged_in() 限 8 小時
    app.config.setdefault('PERMANENT_SESSION_LIFETIME', 30 * 24 * 3600)
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    import admin_bank  # noqa: F401  題庫編輯的路由掛在同一個 bp 上，要在註冊前載入
    import accounts  # noqa: F401  學生審核開通的路由也掛在同一個 bp 上
    app.register_blueprint(bp)
