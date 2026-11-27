"""官網的免費迷你模考（10～15 分鐘）：多益、雅思、日檢、韓檢（2026-11 使用者要求；日檢、韓檢不分級，測完給預估級數）。

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

from flask import abort, jsonify, redirect, render_template, request, send_file, session, url_for

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
    cols = [r[1] for r in c.execute('PRAGMA table_info(mock_attempts)')]
    if 'ai_report' not in cols:   # AI 弱點診斷（JSON，產生一次就存起來，重開不再呼叫 AI）
        c.execute("ALTER TABLE mock_attempts ADD COLUMN ai_report TEXT DEFAULT ''")
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


def _half(x):
    """四捨五入到 0.5（雅思 Band 的算法：.25 進到 .5、.75 進到整數）。"""
    return int(x * 2 + 0.5) / 2


def estimate(data, parts, rows=()):
    """預估成績（2026-11 使用者要求：交卷要有預估分數；日檢、韓檢不分級，測完給大概的級數和分數）。
    題數少，只是參考。依題庫 json 的設定有三種算法，回傳 None 表示這份模考沒設定：
    - score_scale（多益）：{"聽力": [5, 495], "閱讀": [5, 495]}，各技能答對率換算成分數、取 5 的倍數
    - band_scale（雅思）：[[答對率下限, Band], …] 由高到低，聽力、閱讀各查一次，總分取平均（進位到 0.5）
    - level_scale（日檢、韓檢）：每題有 lv（N5…N1／1…6），由最簡單的級數往上看，
      該級答對率達 pass（預設 0.6）就算有這一級的程度，遇到沒過的就停；另外給 100 分制的得分
    回傳 label／big／small／chips 給成績頁，brief 給諮詢名單的成績摘要，levels 是各級正確率（只有 level_scale 有）。"""
    name = data.get('name', '')
    skills = {}
    for p in parts:
        k = skills.setdefault(p['skill'], [0, 0])
        k[0] += p['correct']
        k[1] += p['total']
    rate = {k: (c / t if t else 0) for k, (c, t) in skills.items()}
    if data.get('score_scale'):
        sk = [dict(name=k, score=int(round((lo + rate.get(k, 0) * (hi - lo)) / 5) * 5), hi=hi)
              for k, (lo, hi) in data['score_scale'].items()]
        total = sum(x['score'] for x in sk)
        return dict(label=f'預估{name}分數', big=str(total), small=f" / {sum(x['hi'] for x in sk)}",
                    chips=[f"{x['name']} {x['score']}" for x in sk], brief=f'預估 {total} 分', levels=[],
                    note='預估分數依各部分答對率換算，迷你模考題數少，只是程度參考，不代表正式考試成績。')
    if data.get('band_scale'):
        table = data['band_scale']
        bands = {k: next((b for lo, b in table if r >= lo), table[-1][1]) for k, r in rate.items()}
        overall = _half(sum(bands.values()) / len(bands)) if bands else 0
        return dict(label=f'預估{name} Band', big=f'{overall:.1f}', small=' / 9',
                    chips=[f'{k} {b:.1f}' for k, b in bands.items()], brief=f'預估 Band {overall:.1f}', levels=[],
                    note='預估 Band 依聽力、閱讀的答對率換算，不含寫作與口說；迷你模考題數少，只是程度參考，不代表正式考試成績。')
    cfg = data.get('level_scale')
    if cfg:
        per = {}
        for r in rows:
            lv = r['q'].get('lv')
            if lv is None:
                continue
            k = per.setdefault(str(lv), [0, 0])
            k[0] += r['ok']
            k[1] += 1
        need, got, levels = cfg.get('pass', 0.6), None, []
        stopped = False
        for lv in cfg['levels']:            # 由簡單到難
            c, t = per.get(str(lv['key']), (0, 0))
            rt = c / t if t else 0
            levels.append(dict(name=lv['name'], correct=c, total=t, rate=rt))
            if not stopped and t and rt >= need:
                got = lv
            else:
                stopped = True
        total = sum(t for _c, t in per.values())
        score = round(sum(c for c, _t in per.values()) * 100 / total) if total else 0
        big = got['name'] if got else cfg.get('below', '入門')
        return dict(label=cfg.get('label', f'預估{name}程度'), big=big, small=(got or {}).get('note', ''),
                    chips=[f'得分 {score} / 100'], brief=f'預估程度 {big}、得分 {score}/100', levels=levels,
                    note=cfg.get('note', '預估級數是由簡單到難，看每一級的題目有沒有答對六成；迷你模考題數少，只是程度參考，不代表正式考試成績。'))
    return None


def summary(data, att, parts, rows=()):
    weak = [p['name'] for p in parts if p['rate'] < WEAK_BELOW]
    pct = round(att['correct'] * 100 / att['total']) if att['total'] else 0
    est = estimate(data, parts, rows)
    return (f"{data['title']} 正確率 {att['correct']}/{att['total']}（{pct}%）；"
            + (f"{est['brief']}；" if est else '')
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
    name, skills = data['name'], data.get('skills_text', '聽力加閱讀')
    return site.page('site/mock_take.html', title=f"免費{data['title']}｜{data['minutes']} 分鐘測{name}程度",
                     description=f"免費{data['title']}：{skills}共 {data['total']} 題、約 {data['minutes']} 分鐘，"
                                 f"交卷馬上看正確率，留下聯絡資料就能看{data.get('est_text', '預估分數')}與完整弱點分析。",
                     keywords=data.get('keywords') or [f'{name}模擬考', f'{name}線上測驗', f'免費{name}測驗', f'{name}程度測驗'],
                     jsonld=[site.breadcrumb(('免費迷你模考', site.abs_url('site.mock_test')),
                                             (data['title'], site.abs_url('site.mock_take', key=key)))],
                     data=data, csrf=session['site_csrf'], max_plays=MAX_PLAYS, letters=letters)


def speaker(data, line):
    """句子開頭寫「男：」「女：」就換成 json 的 voices 裡對應的聲音（對話題男女不同聲），回傳 (要唸的文字, 語音)。"""
    import word_audio
    voice = word_audio.VOICES.get(data.get('accent', 'US'), word_audio.VOICES['US'])
    m = re.match(r'^(男|女)：\s*', line)
    if m:
        return line[m.end():], (data.get('voices') or {}).get(m.group(1), voice)
    return line, voice


@site.bp.route('/mock-test/<key>/audio/<int:gi>/<int:si>')
def mock_audio(key, gi, si):
    """聽力音檔：文字只在伺服器上，由 edge-tts 產生（和單字發音共用 word_audio 的快取）。"""
    data = load(key)
    group = next((g for p in (data or {}).get('parts', []) for g in p['groups'] if g['gi'] == gi), None)
    if not group or not (0 <= si < len(group.get('audio', []))):
        abort(404)
    import word_audio
    text, voice = speaker(data, group['audio'][si])
    try:
        path = word_audio.ensure_audio(text, voice)
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
                    contact_time='', message='', source=data['title']), mock=summary(data, att, parts, rows))
                with conn() as c:
                    c.execute('UPDATE mock_attempts SET lead_id=? WHERE id=?', (lead_id, att['id']))
                return redirect(url_for('site.mock_result', token=token) + '#report')
    if not session.get('site_csrf'):
        session['site_csrf'] = secrets.token_hex(16)
    pct = round(att['correct'] * 100 / att['total']) if att['total'] else 0
    resp = site.Response(site.page(
        'site/mock_result.html', title=f"{data['title']}成績", description=f"{data['title']}成績與解析。",
        data=data, att=att, rows=rows, parts=parts, pct=pct, unlocked=unlocked, free=data.get('free_explains', 1), est=estimate(data, parts, rows),
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


# ---------------------------------------------------------------------------
# AI 弱點診斷（2026-11 使用者要求官網強調「AI 即時評分與解析、弱點診斷・個人化進步建議」）
# 填完資料解鎖後，成績頁用 JS 呼叫這裡；數字由程式算好，AI 只依錯題寫診斷與建議。
# 結果存在 mock_attempts.ai_report，同一份成績只呼叫一次 AI；AI 沒設定或失敗時頁面照舊顯示題庫寫好的弱點分析。
# ---------------------------------------------------------------------------

AI_SCHEMA = {'type': 'object', 'additionalProperties': False,
             'required': ['summary', 'strengths', 'weaknesses', 'plan'],
             'properties': {
                 'summary': {'type': 'string', 'description': '對考生說的總評，2–3 句，提到預估成績代表的程度'},
                 'strengths': {'type': 'array', 'items': {'type': 'string'}, 'description': '1–2 個做得好的地方，每個一句'},
                 'weaknesses': {'type': 'array', 'description': '2–3 個最需要加強的弱點，依錯題歸納',
                                'items': {'type': 'object', 'additionalProperties': False, 'required': ['area', 'why', 'how'],
                                          'properties': {'area': {'type': 'string', 'description': '弱點名稱，10 字內'},
                                                         'why': {'type': 'string', 'description': '從哪幾題看出來、錯在哪裡，1–2 句'},
                                                         'how': {'type': 'string', 'description': '具體的練習方法，1–2 句'}}}},
                 'plan': {'type': 'array', 'items': {'type': 'string'}, 'description': '接下來兩週的讀書建議，3 點，每點一句'}}}

AI_SYSTEM = """你是語言補習班的考試分析老師，替剛做完「迷你模考」的考生寫弱點診斷。
規則：
- 全部用繁體中文（台灣用語），語氣親切、具體，像老師當面講解。
- 只根據提供的成績與錯題分析，不要編造考生沒有做的題目或分數。
- 迷你模考題數少，提到程度時要說「大約」「參考」，不要保證考試結果。
- 不要推銷特定課程、不要提價格；最後可以建議找老師討論讀書計畫。"""

AI_DAILY_CAP = 300   # 整個官網一天最多呼叫 AI 幾次，避免被刷爆費用（快取的不算）


def ai_message(data, att, rows, parts):
    est = estimate(data, parts, rows)
    lines = [f"考試：{data['title']}（共 {att['total']} 題，答對 {att['correct']} 題）"]
    if est:
        lines.append(f"程式算的預估：{est['brief']}")
        for lv in est.get('levels') or []:
            lines.append(f"  {lv['name']} 程度的題目：{lv['correct']}/{lv['total']}")
    lines.append('各題型正確率：' + '、'.join(f"{p['name']} {p['correct']}/{p['total']}" for p in parts))
    wrong = [r for r in rows if not r['ok']]
    lines.append(f'錯題（{len(wrong)} 題）：' if wrong else '全部答對。')
    for r in wrong:
        q = r['q']
        opts = q['options']
        mine = opts[ord(r['mine']) - 65] if r['mine'] else '（沒作答）'
        right = opts[ord(q['answer']) - 65]
        stem = q.get('q') or '聽錄音選出最適當的回應'
        if q.get('q') is None and r['group'].get('audio'):
            stem += '（錄音：' + ' '.join(r['group']['audio'])[:200] + '）'
            mine = f"({r['mine']})" if r['mine'] else mine
            right = f"({q['answer']})"
        lv = (f"［{q['lv']}級］" if str(q['lv']).isdigit() else f"［{q['lv']}］") if q.get('lv') else ''
        lines.append(f"- 第 {q['n']} 題{lv}{r['part']['name']}：{stem[:160]}｜考生選：{mine[:60]}｜正解：{right[:60]}｜解析：{q['explain'][:160]}")
    return '\n'.join(lines)


def ai_used_today():
    today = datetime.now(site.TW).strftime('%Y-%m-%d')
    with conn() as c:
        return c.execute("SELECT COUNT(*) FROM mock_attempts WHERE ai_report LIKE ?", (f'%"day": "{today}"%',)).fetchone()[0]


@site.bp.route('/mock-test/result/<token>/ai', methods=['POST'])
def mock_ai(token):
    att = attempt_of(token)
    data = load(att['exam']) if att else None
    if not data or not att['lead_id']:
        abort(404)
    if att['ai_report']:
        return jsonify(ok=True, report=json.loads(att['ai_report']))
    import writing_bank
    if not writing_bank.ai_ready():
        return jsonify(ok=False, reason='AI 診斷暫時無法使用')
    if site.too_many('mockai:' + site.client_ip(), limit=10) or ai_used_today() >= AI_DAILY_CAP:
        return jsonify(ok=False, reason='使用的人太多了，請稍後再重新整理頁面')
    rows, parts = grade(data, json.loads(att['answers']))
    try:
        report, model = writing_bank.ask_json(AI_SYSTEM, ai_message(data, att, rows, parts), AI_SCHEMA,
                                              effort='low', light=True)
        report = dict(summary=str(report.get('summary', ''))[:600],
                      strengths=[str(x)[:200] for x in report.get('strengths', [])][:3],
                      weaknesses=[dict(area=str(w.get('area', ''))[:40], why=str(w.get('why', ''))[:300],
                                       how=str(w.get('how', ''))[:300]) for w in report.get('weaknesses', [])][:4],
                      plan=[str(x)[:200] for x in report.get('plan', [])][:4],
                      day=datetime.now(site.TW).strftime('%Y-%m-%d'))
    except Exception as e:   # AI 沒回、格式不對：頁面改顯示題庫寫好的弱點分析
        print(f'[迷你模考] AI 弱點診斷失敗：{e!r}')
        return jsonify(ok=False, reason='AI 診斷暫時無法使用')
    with conn() as c:
        c.execute('UPDATE mock_attempts SET ai_report=? WHERE id=?', (json.dumps(report, ensure_ascii=False), att['id']))
    return jsonify(ok=True, report=report)
