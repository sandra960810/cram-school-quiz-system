"""日檢模擬考（N5～N1 每級可以有多回）：題庫載入、作答頁、批改與交卷後的正解解析。

題庫是純文字檔（格式見 jlpt_mock/README.md），一回一個檔：第 1 回是 jlpt_mock/N5.txt，第 2 回 N5-2.txt，第 3 回 N5-3.txt…
每回比照正式日檢分成三節（N1、N2 是兩節）：言語知識（文字・語彙）、言語知識（文法）・読解、聴解。
學生一節一節作答，交卷馬上看到那一節的正解與解析；三節都考過後，首頁顯示推估的總分與合格與否。

聽解的音檔由題庫裡的台詞產生（tools/make_jlpt_audio.py，edge-tts 的日語神經語音），
所以音檔內容和題目一定一致。音檔放在 static/audio/jlpt_mock/N5.mp3（第 2 回 N5-2.mp3），不進 git。

權限：功能代碼是 mock（後台「B 模考」），開哪幾回看 exams.open_mock_tests()（後台在「B 模考」底下逐回勾選）；
沒有逐回設定過的學生照舊看 exams.open_levels()（單字等級），有開的等級每一回都能考。
"""
import json
import os
import re
from datetime import datetime

from flask import Blueprint, abort, redirect, render_template, request, url_for
from markupsafe import Markup, escape

bp = Blueprint('jlpt_mock', __name__, url_prefix='/jlpt-mock')
_ = {}

ROOT = os.path.dirname(os.path.abspath(__file__))
BANK_DIR = os.path.join(ROOT, 'jlpt_mock')
AUDIO_DIR = os.path.join(ROOT, 'static', 'audio', 'jlpt_mock')
LEVELS = [5, 4, 3, 2, 1]
LEVEL_NAMES = {5: 'N5 入門', 4: 'N4 初級', 3: 'N3 中級', 2: 'N2 中高級', 1: 'N1 高級'}

# 計分比照正式日檢：N1～N3 三科各 60 分；N4、N5 的言語知識和読解合成一科 120 分。
# 正式考試用等化分數，這裡用答對比例換算，只是推估。
PASS_TOTAL = {1: 100, 2: 90, 3: 95, 4: 90, 5: 80}
KIND_NAMES = {'lang': '言語知識（文字・語彙・文法）', 'read': '読解', 'listen': '聴解',
              'langread': '言語知識（文字・語彙・文法）・読解'}


# ---------------------------------------------------------------------------
# 題庫文字檔 → 結構
# ---------------------------------------------------------------------------

def markup(text):
    """題目文字裡的標記：{漢字|よみ} 變成注音假名（ruby）；<u>、<b>、<br>、表格等 HTML 原樣保留。"""
    return Markup(re.sub(r'\{([^{}|]+)\|([^{}|]+)\}', r'<ruby>\1<rt>\2</rt></ruby>', text))


def plain(text):
    """拿掉標記，給語音合成用（{漢字|よみ} 只留漢字，HTML 標籤拿掉）。"""
    text = re.sub(r'\{([^{}|]+)\|([^{}|]+)\}', r'\1', text)
    return re.sub(r'<[^>]+>', '', text).strip()


def parse(text):
    """把題庫文字檔轉成 dict。格式錯誤會丟 ValueError（tools/check_jlpt_mock.py 會全部檢查）。"""
    test = {'sections': []}
    section = group = q = None
    for ln, raw in enumerate(text.split('\n'), 1):
        line = raw.rstrip()
        if not line.strip() or line.startswith('//'):
            continue
        head, rest = line[0], line[1:].strip()
        if line.startswith('@test'):
            level, title = [x.strip() for x in line[5:].split('｜')]
            test.update(level=int(level.lstrip('N')), title=title)
        elif line.startswith('@section'):
            key, name, minutes = [x.strip() for x in line[8:].split('｜')]
            section = {'key': key, 'name': name, 'minutes': int(minutes), 'groups': []}
            test['sections'].append(section)
            group = q = None
        elif head == '#':
            parts = [x.strip() for x in rest.split('｜')]
            flags = parts[2].split() if len(parts) > 2 else []
            group = {'title': parts[0], 'kind': parts[1], 'spoken': 'spoken' in flags, 'cont': 'cont' in flags,
                     'instr': '', 'items': []}
            if group['kind'] not in ('lang', 'read', 'listen'):
                raise ValueError(f'第 {ln} 行：題組種類要是 lang、read 或 listen')
            section['groups'].append(group)
            q = None
        elif head == '!':
            group['instr'] = (group['instr'] + ' ' + rest).strip()
        elif head == '|':
            if group['items'] and group['items'][-1]['type'] == 'passage' and q is None:
                group['items'][-1]['lines'].append(rest)
            else:
                group['items'].append({'type': 'passage', 'lines': [rest]})
                q = None
        elif head == 'Q':
            q = {'type': 'q', 'stem': rest, 'options': [], 'answer': 0, 'explain': [], 'cues': []}
            group['items'].append(q)
        elif head == '>':
            who, said = rest.split(':', 1)
            q['cues'].append({'v': who.strip(), 't': said.strip()})
        elif head in '1234' and line[1:2] == ' ':
            if int(head) != len(q['options']) + 1:
                raise ValueError(f'第 {ln} 行：選項編號沒有照順序')
            if rest.endswith('*'):
                rest = rest[:-1].rstrip()
                q['answer'] = int(head)
            q['options'].append(rest)
        elif head == '=':
            q['explain'].append(rest)
        else:
            raise ValueError(f'第 {ln} 行看不懂：{line[:30]}')
    # 編號：每一節從 1 開始連號（表單欄位用）；聽解另外有「幾番」（每個問題從 1 開始）。
    # 題組標 cont 的接著上一個題組往下數（N2、N1 聽解問題５的３番：一段話問兩題，
    # 第二題的台詞用「質問２」開頭，和前一題同一個「番」）
    for s in test['sections']:
        n = k = 0
        for g in s['groups']:
            if not g['cont']:
                k = 0
            for it in g['items']:
                if it['type'] == 'q':
                    n += 1
                    follow = bool(it['cues']) and it['cues'][0]['t'].startswith('質問２')
                    if not follow:
                        k += 1
                    it['n'], it['ban'], it['follow'] = n, k, follow
                    it['label'] = f'{k}番' + ('（質問２）' if follow else '')
        s['total'] = n
    return test


_cache = {}


def tid(level, rnd=1):
    """一回測驗的代號，也是題庫檔與音檔的檔名：第 1 回 N5，第 2 回起 N5-2、N5-3。"""
    return f'N{level}' if rnd == 1 else f'N{level}-{rnd}'


def rounds(level):
    """這一級有哪幾回（看 jlpt_mock/ 裡有哪些檔），由小到大。"""
    found = []
    for name in os.listdir(BANK_DIR):
        m = re.fullmatch(rf'N{level}(?:-(\d+))?\.txt', name)
        if m:
            found.append(int(m.group(1) or 1))
    return sorted(found)


def load(level, rnd=1):
    """讀某一級某一回的模擬考；沒有題庫檔回傳 None。檔案改過會重新讀。"""
    key = tid(level, rnd)
    path = os.path.join(BANK_DIR, key + '.txt')
    if not os.path.exists(path):
        return None
    mtime = os.path.getmtime(path)
    if _cache.get(key, (0, None))[0] != mtime:
        with open(path, encoding='utf-8') as f:
            test = parse(f.read())
        test['round'], test['id'] = rnd, key
        _cache[key] = (mtime, test)
    return _cache[key][1]


def audio_file(level, rnd=1):
    return os.path.join(AUDIO_DIR, tid(level, rnd) + '.mp3')


def listening_cues(test):
    """把聽解那一節展開成整段音檔的台詞（說話者代號＋文字，'pause' 是停頓秒數）。
    螢幕上不印選項的題型（発話表現、即時応答、概要理解）選項也會唸出來。"""
    cues = [{'v': 'n', 't': f"日本語能力試験 模擬テスト N{test['level']} 聴解。これから聴解の試験を始めます。"},
            {'v': 'pause', 't': 2}]
    for s in test['sections']:
        for g in s['groups']:
            if g['kind'] != 'listen':
                continue
            if not g['cont']:
                cues.append({'v': 'n', 't': plain(g['title']) + '。'})
            if g['instr']:
                cues.append({'v': 'n', 't': plain(g['instr'])})
            cues.append({'v': 'pause', 't': 2})
            for it in g['items']:
                if it['type'] != 'q':
                    continue
                if not it['follow']:
                    cues.append({'v': 'n', 't': f"{it['ban']}番"})
                    cues.append({'v': 'pause', 't': 1})
                for c in it['cues']:
                    cues.append({'v': c['v'], 't': plain(c['t'])})
                if g['spoken']:
                    # 選項由「不是最後說話的那個人」唸：即時応答是對方回答，発話表現輪流用男女聲
                    last = it['cues'][-1]['v'] if it['cues'] else 'n'
                    voice = 'm1' if last.startswith('f') else 'f1' if last.startswith('m') \
                        else ('f1' if it['ban'] % 2 else 'm1')
                    cues.append({'v': 'pause', 't': 1})
                    for i, opt in enumerate(it['options'], 1):
                        cues.append({'v': 'n', 't': str(i)})
                        cues.append({'v': voice, 't': plain(opt)})
                cues.append({'v': 'pause', 't': 8 if g['spoken'] else 12})
    cues.append({'v': 'n', 't': 'これで聴解の試験を終わります。'})
    return cues


# ---------------------------------------------------------------------------
# 批改與計分
# ---------------------------------------------------------------------------

def grade(section, form):
    """批改一節。回傳 (作答 {題號: 選項}, 各科 {kind: [答對, 題數]})。"""
    answers, kinds = {}, {}
    for g in section['groups']:
        for it in g['items']:
            if it['type'] != 'q':
                continue
            raw = form.get(f"q{it['n']}", '')
            given = int(raw) if raw in ('1', '2', '3', '4') else 0
            answers[str(it['n'])] = given
            k = kinds.setdefault(g['kind'], [0, 0])
            k[1] += 1
            k[0] += given == it['answer']
    return answers, kinds


def estimate(level, kinds):
    """用各科答對比例換算成日檢的分數。kinds 是 {kind: [答對, 題數]}（要三科都有才算）。"""
    if any(k not in kinds or not kinds[k][1] for k in ('lang', 'read', 'listen')):
        return None
    ratio = {k: kinds[k][0] / kinds[k][1] for k in kinds}
    if level >= 4:
        lr = (kinds['lang'][0] + kinds['read'][0]) / (kinds['lang'][1] + kinds['read'][1])
        parts = [('langread', round(lr * 120), 120, 38), ('listen', round(ratio['listen'] * 60), 60, 19)]
    else:
        parts = [(k, round(ratio[k] * 60), 60, 19) for k in ('lang', 'read', 'listen')]
    total = sum(p[1] for p in parts)
    passed = total >= PASS_TOTAL[level] and all(p[1] >= p[3] for p in parts)
    return {'parts': [dict(name=KIND_NAMES[k], score=s, full=f, floor=m, ok=s >= m) for k, s, f, m in parts],
            'total': total, 'pass_total': PASS_TOTAL[level], 'passed': passed}


# ---------------------------------------------------------------------------
# 頁面
# ---------------------------------------------------------------------------

def _context(student_id):
    """回傳 (學生, allowed)。allowed(level, rnd) 判斷這一回有沒有開通：
    後台有逐回勾選（mock_open）就照勾的；沒有就照舊看單字等級（open_levels），該級每一回都開。"""
    student = _['get_student'](student_id)
    exams = _['exams']
    exam = exams.use_exam('jlpt')
    levels = set(exams.open_levels(student, exam) or [])
    tests = exams.open_mock_tests(student, exam)

    def allowed(level, rnd=1):
        return tid(level, rnd) in tests if tests is not None else level in levels
    return student, allowed


def _latest(student_id, level, rnd):
    """這個學生在這一回每一節最近一次的作答紀錄。"""
    Attempt = _['Attempt']
    rows = Attempt.query.filter_by(student_id=student_id, level=level, rnd=rnd).order_by(Attempt.id.desc()).all()
    latest = {}
    for r in rows:
        latest.setdefault(r.section, r)
    return latest


@bp.route('/<int:student_id>')
def home(student_id):
    student, allowed = _context(student_id)
    cards = []
    for level in LEVELS:
        nums = rounds(level)
        usable = [r for r in nums if allowed(level, r)]
        # 題目還沒出的等級顯示「準備中」；有題目但一回都沒開通才顯示「尚未開通」
        card = {'level': level, 'name': LEVEL_NAMES[level], 'ready': bool(nums),
                'locked': bool(nums) and not usable, 'hidden_rounds': len(nums) - len(usable), 'rounds': []}
        for rnd in usable:
            test = load(level, rnd)
            latest = _latest(student.id, level, rnd)
            kinds = {}
            r = {'round': rnd, 'sections': [], 'started': bool(latest)}
            for s in test['sections']:
                a = latest.get(s['key'])
                r['sections'].append({'key': s['key'], 'name': s['name'], 'minutes': s['minutes'],
                                      'total': s['total'], 'attempt': a,
                                      'needs_audio': s['key'] == 'listening'
                                      and not os.path.exists(audio_file(level, rnd))})
                if a:
                    for k, v in json.loads(a.kinds or '{}').items():
                        kinds[k] = v
            r['done'] = len(latest) >= len(test['sections'])
            r['estimate'] = estimate(level, kinds) if r['done'] else None
            card['rounds'].append(r)
        # 預設展開：第一個還沒考完的那一回（都考完就展開第 1 回）
        todo = next((r for r in card['rounds'] if not r['done']), card['rounds'][0] if card['rounds'] else None)
        if todo:
            todo['open'] = True
        cards.append(card)
    return render_template('jlpt_mock_home.html', student=student, cards=cards)


def _section(level, rnd, key, allowed):
    if level not in LEVELS:
        abort(404)
    if not allowed(level, rnd):
        abort(403, description='這一回模擬考還沒開通')
    test = load(level, rnd)
    section = next((s for s in (test or {}).get('sections', []) if s['key'] == key), None)
    if not section:
        abort(404)
    return test, section


# 第 1 回的網址是 /N5/vocab（和只有一回時一樣），第 2 回起是 /N5-2/vocab
@bp.route('/<int:student_id>/N<int:level>/<key>', defaults={'rnd': 1})
@bp.route('/<int:student_id>/N<int:level>-<int:rnd>/<key>')
def take(student_id, level, rnd, key):
    student, allowed = _context(student_id)
    test, section = _section(level, rnd, key, allowed)
    audio = None
    if key == 'listening' and os.path.exists(audio_file(level, rnd)):
        audio = url_for('static', filename=f'audio/jlpt_mock/{tid(level, rnd)}.mp3',
                        v=int(os.path.getmtime(audio_file(level, rnd))))
    return render_template('jlpt_mock_test.html', student=student, test=test, section=section, review=None,
                           audio=audio, is_listening=key == 'listening', mk=markup)


@bp.route('/<int:student_id>/N<int:level>/<key>', methods=['POST'], defaults={'rnd': 1})
@bp.route('/<int:student_id>/N<int:level>-<int:rnd>/<key>', methods=['POST'])
def submit(student_id, level, rnd, key):
    student, allowed = _context(student_id)
    test, section = _section(level, rnd, key, allowed)
    answers, kinds = grade(section, request.form)
    a = _['Attempt'](student_id=student.id, level=level, rnd=rnd, section=key, answers=json.dumps(answers),
                     kinds=json.dumps(kinds), correct=sum(v[0] for v in kinds.values()), total=section['total'])
    _['db'].session.add(a)
    _['db'].session.commit()
    return redirect(url_for('jlpt_mock.result', student_id=student.id, attempt_id=a.id))


@bp.route('/<int:student_id>/result/<int:attempt_id>')
def result(student_id, attempt_id):
    student, allowed = _context(student_id)
    a = _['db'].session.get(_['Attempt'], attempt_id)
    if not a or a.student_id != student.id:
        abort(404)
    test, section = _section(a.level, a.rnd or 1, a.section, allowed)
    review = {'answers': {int(k): v for k, v in json.loads(a.answers).items()}, 'attempt': a}
    return render_template('jlpt_mock_test.html', student=student, test=test, section=section, review=review,
                           audio=None, is_listening=a.section == 'listening', mk=markup)


def register(app, db, deps):
    """掛到主程式：建立作答紀錄的資料表、註冊路由。"""
    _.update(deps, db=db)

    class JlptMockAttempt(db.Model):
        """日檢模擬考一節的作答紀錄（一節交卷一次存一筆）。"""
        id = db.Column(db.Integer, primary_key=True)
        student_id = db.Column(db.Integer, db.ForeignKey('student.id'), nullable=False)
        level = db.Column(db.Integer, nullable=False)        # 5～1
        rnd = db.Column(db.Integer, default=1)               # 第幾回
        section = db.Column(db.String(20), nullable=False)   # vocab / grammar / listening…
        answers = db.Column(db.Text)                         # {題號: 選的選項}，0 是沒作答
        kinds = db.Column(db.Text)                           # {科目: [答對, 題數]}，算總分用
        correct = db.Column(db.Integer, default=0)
        total = db.Column(db.Integer, default=0)
        created_at = db.Column(db.DateTime, default=datetime.utcnow)

    _['Attempt'] = JlptMockAttempt
    with app.app_context():
        db.create_all()
        # 原本每級只有一回，舊資料表沒有 rnd 欄：補上，舊紀錄都算第 1 回
        from sqlalchemy import text
        cols = {row[1] for row in db.session.execute(text('PRAGMA table_info(jlpt_mock_attempt)'))}
        if 'rnd' not in cols:
            db.session.execute(text('ALTER TABLE jlpt_mock_attempt ADD COLUMN rnd INTEGER DEFAULT 1'))
            db.session.commit()
    app.register_blueprint(bp)
