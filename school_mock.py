"""官網的免費迷你模考（約 10 分鐘）：目前只有多益（2026-11 使用者要求先做多益綜合模擬考）。

流程：/mock-test/<考試> 作答（聽力用伺服器產生的音檔，題目文字不給前端）→ 交卷由伺服器批改
→ /mock-test/result/<代碼> 先只顯示正確率和前幾題解析 → 填姓名、電話、Email 才看得到全部解析、各題型正確率與弱點分析。
填的資料會進官網諮詢名單（instance/leads.db 的 leads，mock 欄位寫成績摘要），工作人員在 /admin/leads 看得到。

題庫在 public_site/mock/<考試>.json（題目原創，格式見檔案裡的 _說明）。新增一個考試只要加 json、把 key 加進 school_site.MOCKS。
"""
import json
import os
import re
import secrets
from datetime import datetime

from flask import abort, redirect, render_template, request, send_file, session, url_for

import school_site as site

HERE = os.path.dirname(os.path.abspath(__file__))
MOCK_DIR = os.path.join(HERE, 'public_site', 'mock')
MAX_PLAYS = 2
WEAK_BELOW = 0.7   # 某題型正確率低於 70% 列為弱點


def load(key):
    """讀題庫，題號從 1 往下編，聽力每一組有全域編號 gi（音檔網址用）。"""
    if not re.fullmatch(r'[a-z0-9]+', key or ''):
        return None
    path = os.path.join(MOCK_DIR, f'{key}.json')
    if not os.path.exists(path):
        return None
    with open(path, encoding='utf-8') as f:
        data = json.load(f)
    n, gi = 0, 0
    for part in data['parts']:
        for g in part['groups']:
            g['gi'] = gi
            gi += 1
            for q in g['questions']:
                n += 1
                q['n'] = n
                q['part'] = part['key']
    data['total'] = n
    return data


def questions(data):
    for part in data['parts']:
        for g in part['groups']:
            for q in g['questions']:
                yield part, g, q


def letters(q):
    return [chr(65 + i) for i in range(len(q['options']))]


# ---------------------------------------------------------------------------
# 作答紀錄（和諮詢名單放同一個 leads.db，不進 git）
# ---------------------------------------------------------------------------

def conn():
    c = site.conn()
    c.execute("""CREATE TABLE IF NOT EXISTS mock_attempts (
        id INTEGER PRIMARY KEY AUTOINCREMENT, token TEXT UNIQUE NOT NULL, exam TEXT NOT NULL,
        created_at TEXT NOT NULL, answers TEXT NOT NULL, correct INTEGER, total INTEGER,
        lead_id INTEGER)""")
    return c


def attempt_of(token):
    if not re.fullmatch(r'[A-Za-z0-9_-]{16,64}', token or ''):
        return None
    with conn() as c:
        return c.execute('SELECT * FROM mock_attempts WHERE token=?', (token,)).fetchone()


def grade(data, answers):
    """回傳每題的結果與各題型統計。answers：{題號字串: 'A'}"""
    rows, parts = [], {}
    for part, g, q in questions(data):
        mine = answers.get(str(q['n']), '')
        ok = mine == q['answer']
        rows.append(dict(q=q, part=part, group=g, mine=mine, ok=ok))
        p = parts.setdefault(part['key'], dict(key=part['key'], name=part['name'], skill=part['skill'],
                                               correct=0, total=0))
        p['total'] += 1
        p['correct'] += ok
    for p in parts.values():
        p['rate'] = p['correct'] / p['total'] if p['total'] else 0
    return rows, list(parts.values())


def estimate(data, parts):
    """預估分數（2026-11 使用者要求）：依聽力、閱讀各自的答對率，換算成正式考試的分數範圍。
    json 的 score_scale 例如 {"聽力": [5, 495], "閱讀": [5, 495]}；題數少，只是參考。回傳 None 表示這份模考沒設定。"""
    scale = data.get('score_scale')
    if not scale:
        return None
    skills = []
    for skill, (lo, hi) in scale.items():
        ps = [p for p in parts if p['skill'] == skill]
        total = sum(p['total'] for p in ps)
        rate = sum(p['correct'] for p in ps) / total if total else 0
        skills.append(dict(name=skill, score=int(round((lo + rate * (hi - lo)) / 5) * 5), lo=lo, hi=hi))
    return dict(skills=skills, total=sum(s['score'] for s in skills),
                max=sum(s['hi'] for s in skills))


def summary(data, att, parts):
    weak = [p['name'] for p in parts if p['rate'] < WEAK_BELOW]
    pct = round(att['correct'] * 100 / att['total']) if att['total'] else 0
    est = estimate(data, parts)
    return (f"{data['title']} 正確率 {att['correct']}/{att['total']}（{pct}%）；"
            + (f"預估 {est['total']} 分；" if est else '')
            + ('弱項：' + '、'.join(weak) if weak else '各題型都在 70% 以上'))


# ---------------------------------------------------------------------------
# 頁面
# ---------------------------------------------------------------------------

@site.bp.route('/mock-test/<key>')
def mock_take(key):
    data = load(key)
    if not data:
        abort(404)
    if not session.get('site_csrf'):
        session['site_csrf'] = secrets.token_hex(16)
    return site.page('site/mock_take.html', title=f"免費{data['title']}｜10 分鐘測多益程度",
                     description=f"免費{data['title']}：聽力加閱讀共 {data['total']} 題、約 10 分鐘，交卷馬上看正確率與解析，"
                                 f"留下聯絡資料就能拿到完整弱點分析。",
                     keywords=['多益模擬考', '多益線上測驗', '免費多益測驗', '多益程度測驗', '多益考古題練習'],
                     jsonld=[site.breadcrumb(('免費迷你模考', site.abs_url('site.mock_test')),
                                             (data['title'], site.abs_url('site.mock_take', key=key)))],
                     data=data, csrf=session['site_csrf'], max_plays=MAX_PLAYS, letters=letters)


@site.bp.route('/mock-test/<key>/audio/<int:gi>/<int:si>')
def mock_audio(key, gi, si):
    """聽力音檔：文字只在伺服器上，由 edge-tts 產生（和單字發音共用 word_audio 的快取）。"""
    data = load(key)
    group = next((g for p in (data or {}).get('parts', []) for g in p['groups'] if g['gi'] == gi), None)
    if not group or not (0 <= si < len(group.get('audio', []))):
        abort(404)
    import word_audio
    voice = word_audio.VOICES.get(data.get('accent', 'US'), word_audio.VOICES['US'])
    try:
        path = word_audio.ensure_audio(group['audio'][si], voice)
    except Exception as e:   # 沒裝 edge-tts 或沒網路
        print(f'[迷你模考] 產生音檔失敗：{e!r}')
        return ('', 503)
    return send_file(path, mimetype='audio/mpeg', conditional=True, max_age=30 * 24 * 3600)


@site.bp.route('/mock-test/<key>/submit', methods=['POST'])
def mock_submit(key):
    data = load(key)
    if not data:
        abort(404)
    if request.form.get('csrf') != session.get('site_csrf'):
        abort(400, description='頁面已過期，請重新整理後再作答一次')
    if site.too_many('mock:' + site.client_ip(), limit=30):
        abort(429, description='交卷次數太多了，請稍後再試')
    answers = {}
    for _part, _g, q in questions(data):
        v = (request.form.get(f"q{q['n']}") or '').strip().upper()
        if v in letters(q):
            answers[str(q['n'])] = v
    rows, _parts = grade(data, answers)
    token = secrets.token_urlsafe(18)
    with conn() as c:
        c.execute('INSERT INTO mock_attempts (token, exam, created_at, answers, correct, total) VALUES (?,?,?,?,?,?)',
                  (token, key, datetime.now(site.TW).strftime('%Y-%m-%d %H:%M'), json.dumps(answers),
                   sum(r['ok'] for r in rows), len(rows)))
    return redirect(url_for('site.mock_result', token=token))


@site.bp.route('/mock-test/result/<token>', methods=['GET', 'POST'])
def mock_result(token):
    att = attempt_of(token)
    data = load(att['exam']) if att else None
    if not data:
        abort(404)
    rows, parts = grade(data, json.loads(att['answers']))
    unlocked = bool(att['lead_id'])
    v, errors = {}, []
    if request.method == 'POST' and not unlocked:
        if request.form.get('csrf') != session.get('site_csrf'):
            errors.append('表單已過期，請重新整理頁面再送出一次')
        elif request.form.get('website'):
            return redirect(url_for('site.mock_result', token=token))
        else:
            v, errors = validate_unlock(request.form)
            if not errors and site.too_many(site.client_ip()):
                errors.append('送出太多次了，請稍後再試，或直接加 LINE 聯絡我們')
            if not errors:
                lead_id = site.save_lead(dict(
                    name=v['name'], phone=v['phone'], email=v['email'], line_id='', identity='',
                    courses=[att['exam']] if att['exam'] in site.COURSE_MAP else [], campus=v['campus'],
                    contact_time='', message='', source=data['title']), mock=summary(data, att, parts))
                with conn() as c:
                    c.execute('UPDATE mock_attempts SET lead_id=? WHERE id=?', (lead_id, att['id']))
                return redirect(url_for('site.mock_result', token=token) + '#report')
    if not session.get('site_csrf'):
        session['site_csrf'] = secrets.token_hex(16)
    pct = round(att['correct'] * 100 / att['total']) if att['total'] else 0
    resp = site.Response(site.page(
        'site/mock_result.html', title=f"{data['title']}成績", description=f"{data['title']}成績與解析。",
        data=data, att=att, rows=rows, parts=parts, pct=pct, unlocked=unlocked, free=data.get('free_explains', 1), est=estimate(data, parts),
        weak=[p for p in parts if p['rate'] < WEAK_BELOW], v=v, errors=errors, csrf=session['site_csrf'],
        letters=letters))
    resp.headers['X-Robots-Tag'] = 'noindex, nofollow'
    resp.headers['Cache-Control'] = 'no-store'
    return resp


def validate_unlock(form):
    v = {k: (form.get(k) or '').strip()[:200] for k in ('name', 'phone', 'email', 'campus')}
    v['phone'] = re.sub(r'[\s\-()]', '', v['phone'])
    v['consent'] = form.get('consent') == 'yes'
    errors = []
    if not v['name']:
        errors.append('請填姓名')
    if not site.PHONE_RE.match(v['phone']):
        errors.append('請填正確的電話（例如 0912345678）')
    if not site.EMAIL_RE.match(v['email']):
        errors.append('請填正確的 Email')
    if v['campus'] not in [c['name'] for c in site.info()['campuses']]:
        v['campus'] = ''
    if not v['consent']:
        errors.append('請勾選同意個人資料蒐集說明')
    return v, errors
