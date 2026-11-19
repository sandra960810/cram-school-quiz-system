"""韓檢 TOPIK 模擬考（TOPIK I、TOPIK II 各有多回）：題庫載入、作答頁、批改、級數判定、寫作 AI 批改。

題庫是純文字檔（格式見 topik_mock/README.md），一回一個檔：TOPIK I 第 1 回是 topik_mock/TOPIK1.txt，
第 2 回起 TOPIK1-2.txt、TOPIK1-3.txt…；TOPIK II 是 TOPIK2.txt、TOPIK2-2.txt…
比照正式 TOPIK：
- TOPIK I：듣기 30 題（40 分鐘）＋읽기 40 題（60 分鐘），各 100 分，總分 200；80 分以上 1 級、140 分以上 2 級
- TOPIK II：듣기 50 題（60 分鐘）＋쓰기 4 題（50 分鐘）＋읽기 50 題（70 分鐘），各 100 分，總分 300；
  120／150／190／230 分以上分別是 3／4／5／6 級
選擇題每題的配分寫在題庫裡（TOPIK I 是 2～4 分，TOPIK II 每題 2 分）。
寫作 51、52 各 10 分（㉠㉡ 各 5 分）、53 題 30 分、54 題 50 分，交卷後由 AI 老師批改
（沿用雅思寫作的金鑰設定與呼叫方式 writing_bank.ask_json），分數在 Python 端加總，不讓 AI 自己算。

和日檢模擬考（jlpt_mock.py）一樣：一節交一次卷，交卷後同一頁變成檢討，看得到正解、自己選的和中文解析、聽力台詞。

聽力音檔由題庫台詞產生（tools/make_topik_audio.py，edge-tts 的韓語神經語音），放在 static/audio/topik_mock/
（TOPIK1.mp3、TOPIK1-2.mp3…），不進 git。

權限：TOPIK I 是功能 mock1、TOPIK II 是 mock2（後台審核頁「TOPIK I 模考」「TOPIK II 模考」）；
開哪幾回在審核頁「模考開放的回數」逐回勾選（access 的 mock_open，和日檢共用 exams.open_mock_tests），
沒有逐回設定過的學生，有開 mock1／mock2 就是該級每一回都能考。
"""
import json
import os
import re
from datetime import datetime

from flask import Blueprint, abort, jsonify, redirect, render_template, request, url_for
from markupsafe import Markup

bp = Blueprint('topik_mock', __name__, url_prefix='/topik-mock')
_ = {}

ROOT = os.path.dirname(os.path.abspath(__file__))
BANK_DIR = os.path.join(ROOT, 'topik_mock')
AUDIO_DIR = os.path.join(ROOT, 'static', 'audio', 'topik_mock')
TESTS = [1, 2]
TEST_NAMES = {1: 'TOPIK I（初級：1～2 級）', 2: 'TOPIK II（中高級：3～6 級）'}
ROMAN = {1: 'I', 2: 'II'}
FULL = {1: 200, 2: 300}
# 級數門檻（分數由高到低）
LEVELS = {1: [(140, 2), (80, 1)], 2: [(230, 6), (190, 5), (150, 4), (120, 3)]}
# 寫作配分：51、52 是 ㉠㉡ 兩格各 5 分；53、54 依官方三個評分範疇
WRITING_PARTS = {
    'blanks': [('a', '㉠', 5), ('b', '㉡', 5)],
    'graph': [('content', '內容與任務完成', 7), ('structure', '文章結構', 7), ('language', '語言使用', 16)],
    'essay': [('content', '內容與任務完成', 12), ('structure', '文章結構', 12), ('language', '語言使用', 26)],
}
# 53、54 的建議字數（含空格）
LENGTH = {'graph': (200, 300), 'essay': (600, 700)}


def feature_of(test_no):
    return f'mock{test_no}'


def level_of(test_no, total):
    """依總分判定級數，未達最低門檻回傳 0。"""
    for floor, lv in LEVELS[test_no]:
        if total >= floor:
            return lv
    return 0


# ---------------------------------------------------------------------------
# 題庫文字檔 → 結構
# ---------------------------------------------------------------------------

def mk(text):
    """題庫裡的 HTML（<u>、<b>、<br>、表格、公告框）原樣顯示；題庫是自己寫的，不是學生輸入。"""
    return Markup(text)


def plain(text):
    """拿掉 HTML，給語音合成與 AI 老師用。"""
    text = re.sub(r'<br\s*/?>|</tr>|</p>|</div>', '\n', text)
    text = re.sub(r'</t[dh]>', ' | ', text)
    text = re.sub(r'<[^>]+>', '', text)
    return re.sub(r'[ \t]+', ' ', text).strip()


def _chart(raw, ln):
    try:
        c = json.loads(raw)
        assert c['type'] in ('line', 'bar') and c['x'] and c['series']
        return c
    except Exception as e:
        raise ValueError(f'第 {ln} 行：圖表 JSON 格式錯誤（{e}）')


def parse(text):
    """把題庫文字檔轉成 dict。格式錯誤丟 ValueError（tools/check_topik_mock.py 會全部檢查）。"""
    test = {'sections': []}
    section = group = q = None
    for ln, raw in enumerate(text.split('\n'), 1):
        line = raw.rstrip()
        if not line.strip() or line.startswith('//'):
            continue
        head, rest = line[0], line[1:].strip()
        if line.startswith('@test'):
            no, title = [x.strip() for x in line[5:].split('｜')]
            test.update(no=int(no), title=title)
        elif line.startswith('@section'):
            parts = [x.strip() for x in line[8:].split('｜')]
            key, name, minutes = parts[:3]
            # 第 4 欄是第一題的題號（TOPIK I 的閱讀接著聽力從 31 號開始）
            section = {'key': key, 'name': name, 'minutes': int(minutes), 'groups': [],
                       'start': int(parts[3]) if len(parts) > 3 else 1}
            test['sections'].append(section)
            group = q = None
        elif head == '#':
            parts = [x.strip() for x in rest.split('｜')]
            flags = parts[2].split() if len(parts) > 2 else []
            pts = next((int(f[4:]) for f in flags if f.startswith('pts=')), None)
            group = {'title': parts[0], 'kind': parts[1], 'shared': 'shared' in flags, 'pic': 'pic' in flags,
                     'pts': pts, 'instr': '', 'items': []}
            if group['kind'] not in ('listen', 'read', 'write'):
                raise ValueError(f'第 {ln} 行：題組種類要是 listen、read 或 write')
            section['groups'].append(group)
            q = None
        elif head == '!':
            group['instr'] = (group['instr'] + ' ' + rest).strip()
        elif head == '|' or head == '~':
            entry = _chart(rest[1:].strip() if head == '|' else rest, ln) if (head == '~' or rest.startswith('~')) \
                else rest
            if q is not None and q['type'] == 'w':
                q['prompt'].append(entry)
            elif group['items'] and group['items'][-1]['type'] == 'passage' and q is None:
                group['items'][-1]['lines'].append(entry)
            else:
                group['items'].append({'type': 'passage', 'lines': [entry]})
                q = None
        elif head == 'Q':
            m = re.match(r'Q(?:\[(\d)\])?\s*(.*)$', line)
            pts = int(m.group(1)) if m.group(1) else group['pts']
            if not pts:
                raise ValueError(f'第 {ln} 行：沒有配分（題組加 pts=2，或寫成 Q[3]）')
            q = {'type': 'q', 'stem': m.group(2), 'points': pts, 'options': [], 'answer': 0, 'explain': [],
                 'cues': []}
            group['items'].append(q)
        elif head == 'W':
            no, wtype, pts = [x.strip() for x in rest.split('｜')]
            if wtype not in WRITING_PARTS:
                raise ValueError(f'第 {ln} 行：寫作題型要是 blanks、graph 或 essay')
            q = {'type': 'w', 'n': int(no), 'wtype': wtype, 'points': int(pts), 'prompt': [], 'models': [],
                 'explain': []}
            group['items'].append(q)
        elif head == 'A':
            q['models'].append(rest)
        elif head == '>':
            who, said = rest.split(':', 1)
            q['cues'].append({'v': who.strip(), 't': said.strip()})
        elif head in '1234' and line[1:2] == ' ':
            if int(head) != len(q['options']) + 1:
                raise ValueError(f'第 {ln} 行：選項編號沒有照順序')
            if rest.endswith('*'):
                rest = rest[:-1].rstrip()
                q['answer'] = int(head)
            q['options'].append(_chart(rest[1:], ln) if rest.startswith('~') else rest)
        elif head == '=':
            q['explain'].append(rest)
        else:
            raise ValueError(f'第 {ln} 行看不懂：{line[:30]}')
    # 題號：比照正式考卷。TOPIK I 聽力 1～30、閱讀 31～70；TOPIK II 聽力 1～50、寫作 51～54（寫在 W 行）、閱讀 1～50
    for s in test['sections']:
        n = s['start'] - 1
        for g in s['groups']:
            qs = [it for it in g['items'] if it['type'] == 'q']
            for it in qs:
                n += 1
                it['n'] = n
            g['first'] = qs[0]['n'] if qs else None
        s['questions'] = [it for g in s['groups'] for it in g['items'] if it['type'] in ('q', 'w')]
        s['total'] = len(s['questions'])
        s['full'] = sum(it['points'] for it in s['questions'])
    return test


_cache = {}


def tid(test_no, rnd=1):
    """一回測驗的代號，也是題庫檔與音檔的檔名：第 1 回 TOPIK1，第 2 回起 TOPIK1-2、TOPIK1-3。"""
    return f'TOPIK{test_no}' if rnd == 1 else f'TOPIK{test_no}-{rnd}'


def rounds(test_no):
    """TOPIK I（1）或 TOPIK II（2）有哪幾回（看 topik_mock/ 裡有哪些檔），由小到大。"""
    found = []
    for name in os.listdir(BANK_DIR):
        m = re.fullmatch(rf'TOPIK{test_no}(?:-(\d+))?\.txt', name)
        if m:
            found.append(int(m.group(1) or 1))
    return sorted(found)


def load(test_no, rnd=1):
    """讀某一級某一回的模擬考；沒有題庫檔回傳 None。檔案改過會重新讀。"""
    key = tid(test_no, rnd)
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


def audio_file(test_no, rnd=1):
    return os.path.join(AUDIO_DIR, tid(test_no, rnd) + '.mp3')


def _range_words(title):
    """「[1~4] 다음을…」→「1번부터 4번까지. 다음을…」（給旁白唸）。"""
    m = re.match(r'\[(\d+)~(\d+)\]\s*(.*)', title)
    if m:
        return f'{m.group(1)}번부터 {m.group(2)}번까지. {m.group(3)}'
    return re.sub(r'^\[(\d+)\]\s*', r'\1번. ', title)


def repeats(test_no, n):
    """這一題的錄音播幾次：TOPIK I 每題兩次；TOPIK II 1～20 番一次、21 番以後兩次。"""
    return 2 if test_no == 1 or n >= 21 else 1


def listening_cues(test):
    """把聽力那一節展開成整段音檔的台詞（說話者代號＋文字，'pause' 是停頓秒數）。"""
    no = test['no']
    name = '토픽 원' if no == 1 else '토픽 투'
    rnd = test.get('round', 1)
    title = f'한국어능력시험 모의고사 제{rnd}회' if rnd > 1 else '한국어능력시험 모의고사'
    cues = [{'v': 'n', 't': f'{title}, {name} 듣기 시험을 시작하겠습니다.'}, {'v': 'pause', 't': 2}]
    for s in test['sections']:
        if s['key'] != 'listening':
            continue
        for g in s['groups']:
            qs = [it for it in g['items'] if it['type'] == 'q']
            cues.append({'v': 'n', 't': plain(_range_words(g['title']))})
            cues.append({'v': 'pause', 't': 2})
            blocks = [(qs[0]['n'], qs[0]['cues'], len(qs))] if g['shared'] else [(q['n'], q['cues'], 1) for q in qs]
            for n, said, count in blocks:
                if not g['shared']:
                    cues.append({'v': 'n', 't': f'{n}번.'})
                    cues.append({'v': 'pause', 't': 1})
                for i in range(repeats(no, n)):
                    if i:
                        cues.append({'v': 'pause', 't': 2})
                    cues.extend({'v': c['v'], 't': plain(c['t'])} for c in said)
                # 作答時間：一般題 10～12 秒，兩題一組的長篇多一點
                cues.append({'v': 'pause', 't': (12 if no == 2 else 10) + (8 * (count - 1))})
    cues.append({'v': 'n', 't': '이것으로 듣기 시험을 마치겠습니다.'})
    return cues


# ---------------------------------------------------------------------------
# 批改與計分
# ---------------------------------------------------------------------------

def grade(section, form):
    """批改選擇題的一節。回傳 (作答 {題號: 選項}, 答對題數, 得分)。"""
    answers, correct, score = {}, 0, 0
    for it in section['questions']:
        raw = form.get(f"q{it['n']}", '')
        given = int(raw) if raw in ('1', '2', '3', '4') else 0
        answers[str(it['n'])] = given
        if given == it['answer']:
            correct += 1
            score += it['points']
    return answers, correct, score


def writing_fields(section):
    """寫作的作答欄位：51a、51b、52a、52b、53、54。"""
    out = []
    for it in section['questions']:
        if it['wtype'] == 'blanks':
            out += [f"{it['n']}{k}" for k, _, _ in WRITING_PARTS['blanks']]
        else:
            out.append(str(it['n']))
    return out


def count_chars(text):
    """韓檢寫作的字數：原稿紙一格一字，空格也算，換行不算。"""
    return len((text or '').replace('\r', '').replace('\n', ''))


SYSTEM_PROMPT = """You are a senior TOPIK II writing rater (한국어능력시험 쓰기 채점위원) acting as a strict teacher at a Taiwanese cram school. Mark the four writing answers (questions 51–54) against the official TOPIK II writing scoring categories. Be rigorous, never generous.

Scoring:
- Q51 and Q52: each blank (㉠, ㉡) is scored 0–5.
  5 = fits the context and the sentence before/after it exactly, with correct grammar and the right register (Q51 is a practical text such as a notice, so formal 합쇼체 "-습니다/-ㅂ니다" endings are expected; Q52 is an expository text, so written 해라체 "-ㄴ다/-는다/-다" endings are expected).
  3–4 = the meaning fits but there are grammar, spelling or register errors (e.g. "-아요" endings, a missing connective ending that the blank needs).
  1–2 = only partly related to the context.
  0 = blank, irrelevant, or simply copies a nearby sentence.
  Other wordings than the reference answers are fine if they fit the context.
- Q53 (30 points): content and task completion 0–7 (all key information from the data described accurately: the survey intro, the trend with correct figures and comparison, both reasons, the outlook; no personal opinions), structure 0–7 (logical order, cohesive devices), language use 0–16 (range and accuracy of grammar and vocabulary, written 해라체 style; spoken style or 합쇼체 lowers this).
- Q54 (50 points): content and task completion 0–12 (answers all three guiding questions with relevant, developed ideas; a clear position), structure 0–12 (introduction–body–conclusion, paragraphing, logical flow and connectives), language use 0–26 (range, accuracy and appropriateness of grammar and vocabulary, written 해라체 style).
- Length: Q53 should be 200–300 characters and Q54 600–700 characters, counting spaces. Clearly shorter answers must lose points in content (an answer under half the minimum cannot get more than half of the content points). Text copied from the question earns no credit. Titles should not be written.
- Do not inflate scores to encourage the student. Encouragement belongs in the comments, not in the score.

Write all comments for a Taiwanese student in Traditional Chinese (繁體中文, Taiwan usage). Quote the student's Korean exactly when pointing to evidence. Corrections and rewrites must be in Korean.
"""

_BLANK = {'type': 'object',
          'properties': {'score': {'type': 'integer', 'description': '0 到 5 分'},
                         'comment': {'type': 'string', 'description': '為什麼是這個分數（繁體中文）'}},
          'required': ['score', 'comment'], 'additionalProperties': False}


def _long(maxes):
    props = {k: {'type': 'integer', 'description': f'0 到 {m} 分'} for k, _, m in maxes}
    props['comment'] = {'type': 'string', 'description': '三個範疇的評語與扣分原因（繁體中文，引用原文）'}
    return {'type': 'object', 'properties': props, 'required': list(props), 'additionalProperties': False}


def _schema():
    return {
        'type': 'object',
        'properties': {
            'q51': {'type': 'object', 'properties': {'a': _BLANK, 'b': _BLANK}, 'required': ['a', 'b'],
                    'additionalProperties': False},
            'q52': {'type': 'object', 'properties': {'a': _BLANK, 'b': _BLANK}, 'required': ['a', 'b'],
                    'additionalProperties': False},
            'q53': _long(WRITING_PARTS['graph']),
            'q54': _long(WRITING_PARTS['essay']),
            'summary': {'type': 'string', 'description': '整體評語，3–5 句，繁體中文'},
            'errors': {
                'type': 'array', 'description': '最重要的語言錯誤，最多 10 個',
                'items': {'type': 'object',
                          'properties': {'original': {'type': 'string'}, 'correction': {'type': 'string'},
                                         'explain': {'type': 'string'}},
                          'required': ['original', 'correction', 'explain'], 'additionalProperties': False}},
            'next_steps': {'type': 'array', 'items': {'type': 'string'}, 'description': '最該先改進的 3 件事，繁體中文'},
        },
        'required': ['q51', 'q52', 'q53', 'q54', 'summary', 'errors', 'next_steps'],
        'additionalProperties': False,
    }


def _prompt_text(item):
    import writing_bank
    out = []
    for p in item['prompt']:
        out.append('THE GRAPH (exact data the student saw):\n' + writing_bank.chart_as_text(p) if isinstance(p, dict)
                   else plain(p))
    return '\n'.join(out)


def _user_message(section, essays):
    parts = ['TOPIK II 쓰기 (writing), questions 51–54. Mark all four answers.', '']
    for g in section['groups']:
        for it in g['items']:
            if it['type'] != 'w':
                continue
            parts += [f"=== Question {it['n']} ({it['points']} points) ===", plain(g['title']), _prompt_text(it)]
            parts.append('Reference answer(s) (other wordings can also be correct):')
            parts += ['  ' + m for m in it['models']]
            if it['wtype'] == 'blanks':
                for k, mark, _ in WRITING_PARTS['blanks']:
                    ans = essays.get(f"{it['n']}{k}", '').strip()
                    parts.append(f'STUDENT ANSWER {mark}: """{ans or "(blank)"}"""')
            else:
                ans = essays.get(str(it['n']), '').strip()
                lo, hi = LENGTH[it['wtype']]
                parts.append(f'STUDENT ANSWER ({count_chars(ans)} characters including spaces; required {lo}–{hi}):')
                parts += ['"""', ans or '(blank)', '"""']
            parts.append('')
    return '\n'.join(parts)


def total_from(result):
    """把 AI 給的各項分數（已經限制在範圍內）加總成 100 分制的寫作分數，順便算每題小計。"""
    total = 0
    for no, kind in ((51, 'blanks'), (52, 'blanks'), (53, 'graph'), (54, 'essay')):
        item = result[f'q{no}']
        sub = 0
        for k, _, m in WRITING_PARTS[kind]:
            if kind == 'blanks':
                item[k]['score'] = max(0, min(m, int(item[k]['score'])))
                sub += item[k]['score']
            else:
                item[k] = max(0, min(m, int(item[k])))
                sub += item[k]
        item['total'] = sub
        total += sub
    result['total'] = total
    return total


def grade_writing(section, essays):
    """請 AI 老師批改四題寫作，回傳 dict（各題分數、評語、total）。全部空白時直接給 0 分不呼叫 AI。"""
    import writing_bank
    if not any((essays.get(f) or '').strip() for f in writing_fields(section)):
        blank = {'score': 0, 'comment': '沒有作答。'}
        empty = lambda kind: {**{k: 0 for k, _, _ in WRITING_PARTS[kind]}, 'comment': '沒有作答。'}
        result = {'q51': {'a': dict(blank), 'b': dict(blank)}, 'q52': {'a': dict(blank), 'b': dict(blank)},
                  'q53': empty('graph'), 'q54': empty('essay'), 'summary': '四題都沒有作答，正式考試寫作是 0 分。',
                  'errors': [], 'next_steps': [], 'model': ''}
        total_from(result)
        return result
    data, model = writing_bank.ask_json(SYSTEM_PROMPT, _user_message(section, essays), _schema())
    try:
        total_from(data)
    except (KeyError, TypeError, ValueError):
        raise RuntimeError('AI 回覆的格式不正確，請再按一次批改。')
    data.setdefault('errors', [])
    data.setdefault('next_steps', [])
    data['model'] = model
    return data


# ---------------------------------------------------------------------------
# 頁面
# ---------------------------------------------------------------------------

def _context(student_id):
    """回傳 (學生, feats, allowed)。allowed(test_no, rnd) 判斷這一回有沒有開通：
    要開了 mock1／mock2，而且後台有逐回勾選（mock_open）時要勾到這一回；沒逐回設定過就是該級每一回都開。"""
    student = _['get_student'](student_id)
    exams = _['exams']
    exam = exams.use_exam('topik')
    feats = set(exams.features_for(student, exam))
    tests = exams.open_mock_tests(student, exam)

    def allowed(test_no, rnd=1):
        return feature_of(test_no) in feats and (tests is None or tid(test_no, rnd) in tests)
    return student, feats, allowed


def _latest(student_id, test_no, rnd=1):
    Attempt = _['Attempt']
    rows = Attempt.query.filter_by(student_id=student_id, test=test_no, rnd=rnd).order_by(Attempt.id.desc()).all()
    latest = {}
    for r in rows:
        latest.setdefault(r.section, r)
    return latest


def summary(test, latest):
    """全部科目都交過後的總分與級數。寫作還沒批改時 total 不含寫作、pending=True。"""
    parts, total, pending = [], 0, False
    for s in test['sections']:
        a = latest.get(s['key'])
        score = a.score if a else None
        if s['key'] == 'writing' and a and score is None:
            pending = True
        parts.append({'name': s['name'], 'score': score, 'full': s['full']})
        total += score or 0
    if any(p['score'] is None and not (pending and p['name'] == '쓰기') for p in parts):
        return None
    no = test['no']
    lv = level_of(no, total)
    nxt = next(((f, l) for f, l in reversed(LEVELS[no]) if total < f), None)
    return {'parts': parts, 'total': total, 'full': FULL[no], 'level': lv, 'pending': pending,
            'next': nxt, 'floors': list(reversed(LEVELS[no]))}


@bp.route('/<int:student_id>')
def home(student_id):
    student, feats, allowed = _context(student_id)
    cards = []
    for no in TESTS:
        nums = rounds(no)
        usable = [r for r in nums if allowed(no, r)]
        # 題目還沒出顯示「準備中」；有題目但一回都沒開通才顯示「尚未開通」
        card = {'no': no, 'name': TEST_NAMES[no], 'roman': ROMAN[no], 'ready': bool(nums),
                'locked': bool(nums) and not usable, 'hidden_rounds': len(nums) - len(usable), 'rounds': [],
                'full': FULL[no], 'floors': list(reversed(LEVELS[no]))}
        for rnd in usable:
            test = load(no, rnd)
            latest = _latest(student.id, no, rnd)
            r = {'round': rnd, 'started': bool(latest),
                 'sections': [{'key': s['key'], 'name': s['name'], 'minutes': s['minutes'], 'total': s['total'],
                               'full': s['full'], 'attempt': latest.get(s['key']),
                               'needs_audio': s['key'] == 'listening' and not os.path.exists(audio_file(no, rnd))}
                              for s in test['sections']],
                 'summary': summary(test, latest)}
            card['rounds'].append(r)
        # 預設展開：第一個還沒考完的那一回（都考完就展開第 1 回）
        todo = next((r for r in card['rounds'] if not r['summary']), card['rounds'][0] if card['rounds'] else None)
        if todo:
            todo['open'] = True
        cards.append(card)
    return render_template('topik_mock_home.html', student=student, cards=cards)


def _section(test_no, rnd, key, allowed):
    if test_no not in TESTS:
        abort(404)
    if not allowed(test_no, rnd):
        abort(403, description='這一回模擬考還沒開通')
    test = load(test_no, rnd)
    section = next((s for s in (test or {}).get('sections', []) if s['key'] == key), None)
    if not section:
        abort(404)
    return test, section


def _render(student, test, section, review=None, attempt=None):
    if section['key'] == 'writing':
        import writing_bank
        essays = json.loads(attempt.answers) if attempt else {}
        ai = json.loads(attempt.ai) if attempt and attempt.ai else None
        return render_template('topik_mock_write.html', student=student, test=test, section=section,
                               attempt=attempt, essays=essays, ai=ai, mk=mk, parts=WRITING_PARTS, lengths=LENGTH,
                               chart=writing_bank.chart_svg, count_chars=count_chars,
                               ai_ready=writing_bank.ai_ready(), ai_label=writing_bank.ai_label())
    audio = None
    no = test['no']
    rnd = test['round']
    if section['key'] == 'listening' and not review and os.path.exists(audio_file(no, rnd)):
        audio = url_for('static', filename=f'audio/topik_mock/{tid(no, rnd)}.mp3',
                        v=int(os.path.getmtime(audio_file(no, rnd))))
    import writing_bank
    return render_template('topik_mock_test.html', student=student, test=test, section=section, review=review,
                           audio=audio, is_listening=section['key'] == 'listening', mk=mk,
                           chart=writing_bank.chart_svg, repeats=repeats)


# 第 1 回的網址是 /t1/listening（和只有一回時一樣），第 2 回起是 /t1-2/listening
@bp.route('/<int:student_id>/t<int:test_no>/<key>', defaults={'rnd': 1})
@bp.route('/<int:student_id>/t<int:test_no>-<int:rnd>/<key>')
def take(student_id, test_no, rnd, key):
    student, feats, allowed = _context(student_id)
    test, section = _section(test_no, rnd, key, allowed)
    return _render(student, test, section)


@bp.route('/<int:student_id>/t<int:test_no>/<key>', methods=['POST'], defaults={'rnd': 1})
@bp.route('/<int:student_id>/t<int:test_no>-<int:rnd>/<key>', methods=['POST'])
def submit(student_id, test_no, rnd, key):
    student, feats, allowed = _context(student_id)
    test, section = _section(test_no, rnd, key, allowed)
    Attempt = _['Attempt']
    if key == 'writing':
        essays = {f: (request.form.get(f'w{f}') or '')[:5000] for f in writing_fields(section)}
        a = Attempt(student_id=student.id, test=test_no, rnd=rnd, section=key, answers=json.dumps(essays, ensure_ascii=False),
                    correct=0, total=section['total'], score=None, full=section['full'])
    else:
        answers, correct, score = grade(section, request.form)
        a = Attempt(student_id=student.id, test=test_no, rnd=rnd, section=key, answers=json.dumps(answers), correct=correct,
                    total=section['total'], score=score, full=section['full'])
    _['db'].session.add(a)
    _['db'].session.commit()
    return redirect(url_for('topik_mock.result', student_id=student.id, attempt_id=a.id))


def _attempt(student, attempt_id):
    a = _['db'].session.get(_['Attempt'], attempt_id)
    if not a or a.student_id != student.id:
        abort(404)
    return a


@bp.route('/<int:student_id>/result/<int:attempt_id>')
def result(student_id, attempt_id):
    student, feats, allowed = _context(student_id)
    a = _attempt(student, attempt_id)
    test, section = _section(a.test, a.rnd or 1, a.section, allowed)
    review = {'answers': {int(k): v for k, v in json.loads(a.answers).items()}, 'attempt': a} \
        if a.section != 'writing' else None
    return _render(student, test, section, review=review, attempt=a)


@bp.route('/<int:student_id>/grade/<int:attempt_id>', methods=['POST'])
def grade_ai(student_id, attempt_id):
    """寫作交卷後請 AI 老師批改（結果存進資料庫，重開頁面不會重複扣費）。"""
    student, feats, allowed = _context(student_id)
    a = _attempt(student, attempt_id)
    test, section = _section(a.test, a.rnd or 1, a.section, allowed)
    if a.section != 'writing':
        abort(400)
    if a.ai:
        return jsonify(ok=True, cached=True)
    try:
        data = grade_writing(section, json.loads(a.answers))
    except RuntimeError as e:
        return jsonify(ok=False, error=str(e)), 502
    a.ai = json.dumps(data, ensure_ascii=False)
    a.score = data['total']
    _['db'].session.commit()
    return jsonify(ok=True, score=a.score)


def register(app, db, deps):
    """掛到主程式：建立作答紀錄的資料表、註冊路由。"""
    _.update(deps, db=db)

    class TopikMockAttempt(db.Model):
        """韓檢模擬考一節的作答紀錄（一節交卷一次存一筆）。"""
        id = db.Column(db.Integer, primary_key=True)
        student_id = db.Column(db.Integer, db.ForeignKey('student.id'), nullable=False)
        test = db.Column(db.Integer, nullable=False)         # 1＝TOPIK I、2＝TOPIK II
        rnd = db.Column(db.Integer, default=1)               # 第幾回
        section = db.Column(db.String(20), nullable=False)   # listening / reading / writing
        answers = db.Column(db.Text)                         # 選擇題 {題號: 選項}（0 是沒作答）；寫作 {欄位: 內容}
        correct = db.Column(db.Integer, default=0)
        total = db.Column(db.Integer, default=0)             # 題數
        score = db.Column(db.Integer)                        # 得分；寫作在 AI 批改前是 None
        full = db.Column(db.Integer, default=100)
        ai = db.Column(db.Text)                              # 寫作的 AI 批改結果（JSON）
        created_at = db.Column(db.DateTime, default=datetime.utcnow)

    _['Attempt'] = TopikMockAttempt
    with app.app_context():
        db.create_all()
        # 原本每級只有一回，舊資料表沒有 rnd 欄：補上，舊紀錄都算第 1 回
        from sqlalchemy import text
        cols = {row[1] for row in db.session.execute(text('PRAGMA table_info(topik_mock_attempt)'))}
        if 'rnd' not in cols:
            db.session.execute(text('ALTER TABLE topik_mock_attempt ADD COLUMN rnd INTEGER DEFAULT 1'))
            db.session.commit()
    app.register_blueprint(bp)
