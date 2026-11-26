"""AI 學習教練：錯題解釋、弱點練習、學習報告、單字記憶法。

四個功能都用寫作 AI 老師的同一把金鑰與呼叫方式（writing_bank.ask_json，依金鑰開頭自動選 Gemini 或 Claude），
沒有設定金鑰時頁面照常打開，只是按鈕會說「AI 老師還沒設定」。

1. AI 解釋錯題 POST /api/ai/<學生id>/explain
   雅思聽力／閱讀成績頁與錯題本、日檢／韓檢模擬考檢討頁、背單字神器的成績頁，每一題答錯的下面有「問 AI 老師」。
   題目、選項、正解、學生答案、原文都由伺服器自己從題庫與作答紀錄找出來（不收前端傳的題目內容），
   AI 依「這個學生選了什麼」解釋為什麼錯、正解為什麼對、下次怎麼判斷，再附一題同類型的小練習。
   同一題同一個錯誤答案的解釋大家共用（AiCache），第二個人按就不用再花錢、也是馬上出來。

2. AI 弱點練習 /ai/<學生id>/practice
   weak_profile() 在 Python 端統計學生的弱點（雅思各題型的錯誤率、錯題本、寫作／口說 AI 評語、
   不熟的單字、背單字神器各題型答對率、日檢／韓檢模擬考各科答對率），交給 AI 依這些弱點出一份練習題，
   作答後伺服器批改（AiPractice）。統計數字由程式算，不讓 AI 自己編。

3. AI 學習報告 /ai/<學生id>/report
   給家長與工作人員看：數字（學過幾個字、測驗成績…）由程式算好，AI 只負責寫評語、強弱項與兩週計畫。
   同一個學生同一個考試一天一份（重新產生會覆蓋）。

4. AI 單字記憶法 POST /api/ai/<學生id>/word/<單字id>
   單字卡上的「AI 記憶法」：記憶口訣、更多例句、常用搭配、容易混淆的字。同一個字大家共用。

費用控制：每個學生每天最多 DAILY_LIMIT 次真的呼叫 AI（用快取的不算）；工作人員登入時不限。
頁面一定要保留「AI 產生的內容可能有錯，以老師講解為準」的提示。
"""
import json
import random
import re
from datetime import datetime, timedelta

from flask import Blueprint, abort, jsonify, render_template, request, url_for
from markupsafe import Markup

import exams
import listening_bank
import reading_bank
import writing_bank

bp = Blueprint('ai_tutor', __name__)
_ = {}   # register() 放進來的主程式物件

DAILY_LIMIT = 60          # 每個學生每天最多真的呼叫幾次 AI
PRACTICE_SIZE = 8         # 一份弱點練習幾題
EFFORT = 'low'            # Claude 的思考程度：短回答用 low，回得快也比較省

TYPE_ZH = {'tfng': '是非題（TRUE／FALSE／NOT GIVEN）', 'ynng': '觀點題（YES／NO／NOT GIVEN）',
           'mcq': '單選題', 'matching': '配對題', 'headings': '段落標題題', 'gapfill': '填空題', 'map': '地圖題'}
SECTION_ZH = {'listening': '聽力', 'reading': '閱讀', 'writing': '寫作', 'speaking': '口說'}
VOCAB_TYPE_ZH = {'spell': '拼寫', 'dictate': '聽寫', 'cloze': '例句填空', 'meaning': '選意思', 'word': '選單字'}
JLPT_KIND_ZH = {'lang': '言語知識（文字・語彙・文法）', 'read': '讀解', 'listen': '聽解'}
TOPIK_KIND_ZH = {'listen': '聽力', 'read': '閱讀', 'write': '寫作'}
LANG_NAME = {None: '英文', 'ja': '日文', 'ko': '韓文'}

COMMON_RULES = """You are a patient, precise tutor at a Taiwanese cram school.
Write every explanation for a Taiwanese student in Traditional Chinese (繁體中文, Taiwan usage), short and concrete.
Keep target-language material (English / Japanese / Korean sentences, options, quotes) in that language.
Never invent facts about the test material: rely only on the question, the answer key, the official explanation and the source text you are given.
If the given material is not enough to be sure, say so briefly instead of guessing.
Do not use emoji."""


# ---------------------------------------------------------------------------
# 小工具
# ---------------------------------------------------------------------------

def plain(html):
    """題庫裡的 HTML（<b>、<br>）轉成純文字給 AI 看。"""
    s = re.sub(r'<br\s*/?>', '\n', str(html or ''))
    s = re.sub(r'<[^>]+>', '', s)
    return s.replace('&nbsp;', ' ').replace('&amp;', '&').strip()


def _norm_given(text):
    return ' '.join(str(text or '').strip().casefold().split())[:120]


def today_start_utc():
    """台灣今天 0 點（換成 UTC，資料庫存的是 UTC）。"""
    tw = datetime.utcnow() + timedelta(hours=8)
    return datetime(tw.year, tw.month, tw.day) - timedelta(hours=8)


def used_today(student_id):
    Cache, Practice = _['AiCache'], _['AiPractice']
    since = today_start_utc()
    return (Cache.query.filter(Cache.student_id == student_id, Cache.created_at >= since).count()
            + Practice.query.filter(Practice.student_id == student_id, Practice.created_at >= since).count())


def _staff():
    import admin
    return admin.logged_in()


def check_quota(student_id):
    """超過今天的次數上限就丟 RuntimeError。"""
    if not _staff() and used_today(student_id) >= DAILY_LIMIT:
        raise RuntimeError(f'今天已經問 AI 老師 {DAILY_LIMIT} 次了，明天再來，或請老師幫你看。')


def ask(student_id, system, message, schema):
    """呼叫 AI（數次限制、金鑰檢查都在這裡）。回傳 (dict, 模型名稱)，失敗丟 RuntimeError。"""
    if not writing_bank.ai_ready():
        raise RuntimeError('AI 老師還沒設定：請在櫃台電腦雙擊 set_ai_key.bat 輸入 API 金鑰。')
    check_quota(student_id)
    return writing_bank.ask_json(system, message, schema, effort=EFFORT)


def cached(key, student_id, kind, build):
    """有快取就用快取；沒有就呼叫 build() 產生並存起來。回傳 (dict, 是否來自快取)。"""
    Cache, db = _['AiCache'], _['db']
    hit = Cache.query.filter_by(key=key).first()
    if hit:
        return json.loads(hit.result), True
    data = build()
    row = Cache.query.filter_by(key=key).first()     # 同時有兩個人按：留先寫進去的那份
    if row:
        return json.loads(row.result), True
    db.session.add(Cache(key=key, kind=kind, student_id=student_id, model=data.get('model', ''),
                         result=json.dumps(data, ensure_ascii=False)))
    db.session.commit()
    return data, False


def _obj(props, required=None):
    return {'type': 'object', 'properties': props, 'required': required or list(props),
            'additionalProperties': False}


STR = {'type': 'string'}
STR_LIST = {'type': 'array', 'items': STR}


# ---------------------------------------------------------------------------
# 1. AI 解釋錯題：從題庫找出題目內容
# ---------------------------------------------------------------------------

def _gap_text(text, qno):
    """填空句：要問的空格換成 ____，其他空格換成 ……"""
    text = re.sub(r'\{%d\}' % qno, '____', text)
    text = re.sub(r'\{ex:([^}]*)\}', r'\1', text)
    return re.sub(r'\{\d+\}', '……', text)


def ielts_question(section, test_key, qno):
    """雅思聽力／閱讀某一題的完整內容（給 AI 看），找不到回傳 None。"""
    if section == 'listening':
        if not listening_bank.load_test(test_key):
            return None
        parts = listening_bank._part_files(test_key)
    elif section == 'reading':
        if not reading_bank.load_test(test_key):
            return None
        parts = reading_bank._passage_files(test_key)
    else:
        return None
    for p in parts:
        q = next((x for x in p['questions'] if x['no'] == qno), None)
        if not q:
            continue
        out = {'section': section, 'test_key': test_key, 'qno': qno, 'part': p['no'],
               'answers': q['answers'], 'explain': plain(q.get('explain')), 'quote': q.get('quote', ''),
               'type': '', 'instruction': '', 'prompt': '', 'options': []}
        for g in p['groups']:
            line = None
            item = next((it for it in g.get('items', []) if it.get('no') == qno), None)
            if item:
                line = item.get('stem') or item.get('text') or ''
            else:
                tag = '{%d}' % qno
                for r in g.get('rows', []):
                    if tag in r.get('text', ''):
                        line = _gap_text(r['text'], qno)
                for s in g.get('sections', []):
                    for ln in s.get('lines', []):
                        if tag in ln:
                            line = (s.get('heading', '') + '：' if s.get('heading') else '') + _gap_text(ln, qno)
            if line is None:
                continue
            out['type'] = g['type']
            out['instruction'] = plain(g.get('instruction', '')) + ' ' + plain(g.get('limit', ''))
            out['prompt'] = line
            opts = (item or {}).get('options') or g.get('options') or {}
            if isinstance(opts, dict):
                out['options'] = [f'{k}. {v}' for k, v in opts.items()]
            elif opts:
                out['options'] = [str(o) for o in opts]
            if g['type'] in ('tfng', 'ynng'):
                out['options'] = reading_bank.JUDGE_OPTIONS[g['type']]
            if g['type'] == 'map':
                out['instruction'] += '（地圖題：AI 看不到地圖，只能依錄音原文說明）'
            break
        out['context'] = _source_context(section, p, q.get('quote', ''))
        return out
    return None


def _source_context(section, part, quote):
    """原文裡和這一題有關的段落：閱讀是引句所在的段落，聽力是引句前後幾句台詞。"""
    key = re.sub(r'\W+', ' ', quote or '').strip().lower()[:40]
    if section == 'reading':
        for para in part.get('paragraphs', []):
            if key and key in re.sub(r'\W+', ' ', para['text']).lower():
                return (f"Paragraph {para['label']}: " if para.get('label') else '') + para['text']
        return ''
    cues = [c for c in part.get('cues', []) if c['v'] not in ('pause', 'narrator')]
    for i, c in enumerate(cues):
        if key and key[:25] in re.sub(r'\W+', ' ', c['t']).lower():
            return '\n'.join(f"{x['v']}: {x['t']}" for x in cues[max(0, i - 3):i + 4])
    return ''


def _mock_item(section, n):
    """在模擬考的一節裡找第 n 題，連同前面最近的一篇文章。"""
    for g in section['groups']:
        passage = []
        for it in g['items']:
            if it['type'] == 'passage':
                passage = it['lines']
            elif it['type'] == 'q' and it.get('n') == n:
                return g, it, passage
    return None, None, None


def _mock_payload(exam_key, student, data):
    """日檢（jlpt）／韓檢（topik）模擬考答錯的一題。"""
    mod = _['jlpt_mock'] if exam_key == 'jlpt' else _['topik_mock']
    Attempt = mod._['Attempt']
    try:
        a = _['db'].session.get(Attempt, int(data.get('attempt_id')))
        n = int(data.get('n'))
    except (TypeError, ValueError):
        return None
    if not a or a.student_id != student.id:
        return None
    if exam_key == 'jlpt':
        test = mod.load(a.level, a.rnd or 1)
        title = f'日檢 N{a.level} 模擬考'
    else:
        test = mod.load(a.test, a.rnd or 1)
        title = f'TOPIK {"I" * a.test} 模擬考'
    section = next((s for s in (test or {}).get('sections', []) if s['key'] == a.section), None)
    if not section:
        return None
    g, it, passage = _mock_item(section, n)
    if not it:
        return None
    given = int(json.loads(a.answers or '{}').get(str(n), 0) or 0)
    if given == it['answer']:
        return None
    text = lambda s: plain(mod.plain(s) if isinstance(s, str) else s)  # noqa: E731
    lines = [f'{title}・{section["name"]}・第 {n} 題（{g["title"]}）']
    if g.get('instr'):
        lines.append('題目說明：' + text(g['instr']))
    if passage:
        lines.append('文章：\n' + '\n'.join(text(x) for x in passage if isinstance(x, str)))
    if it.get('cues'):
        lines.append('聽力原文：\n' + '\n'.join(f"{c['v']}: {text(c['t'])}" for c in it['cues']))
    lines.append('題目：' + text(it['stem']))
    lines.append('選項：\n' + '\n'.join(f'{i}. {text(o) if isinstance(o, str) else "（圖表）"}'
                                      for i, o in enumerate(it['options'], 1)))
    lines.append(f'正解：{it["answer"]}')
    lines.append(f'學生選：{given if given else "（沒有作答）"}')
    if it.get('explain'):
        lines.append('題庫解析：' + text(' '.join(it['explain'])))
    lang = 'ja' if exam_key == 'jlpt' else 'ko'
    return {'cache': f'explain:{exam_key}:{mod.tid(a.level if exam_key == "jlpt" else a.test, a.rnd or 1)}:'
                     f'{a.section}:{n}:{given}',
            'message': '\n'.join(lines), 'lang': lang,
            'given': str(given) if given else '', 'answer': str(it['answer'])}


def explain_payload(student, data):
    """依前端送來的「哪一題」找出要給 AI 看的內容。回傳 dict 或 None（找不到這題、或這題其實答對了）。"""
    kind = data.get('kind')
    if kind == 'ielts':
        section, test_key = data.get('section'), str(data.get('test_key') or '')
        try:
            qno = int(data.get('qno'))
        except (TypeError, ValueError):
            return None
        q = ielts_question(section, test_key, qno)
        if not q:
            return None
        given = None
        if data.get('attempt_id'):
            A = _['TestAttempt']
            a = _['db'].session.get(A, int(data['attempt_id'])) if str(data['attempt_id']).isdigit() else None
            if a and a.student_id == student.id and a.test_key == test_key and a.section == section:
                row = _['TestAnswer'].query.filter_by(attempt_id=a.id, qno=qno).first()
                if row:
                    if row.is_correct:
                        return None
                    given = row.given or ''
        if given is None:
            m = _['TestMistake'].query.filter_by(student_id=student.id, test_key=test_key,
                                                 section=section, qno=qno).first()
            if not m:
                return None
            given = m.last_given or ''
        lines = [f'IELTS {"Listening" if section == "listening" else "Academic Reading"} '
                 f'（{test_key}，{"Part" if section == "listening" else "Passage"} {q["part"]}），第 {qno} 題',
                 f'題型：{TYPE_ZH.get(q["type"], q["type"])}',
                 '題目說明：' + q['instruction'].strip(),
                 '題目：' + q['prompt']]
        if q['options']:
            lines.append('選項：\n' + '\n'.join(q['options']))
        lines += ['正解（可接受的寫法）：' + ' / '.join(q['answers']),
                  '學生的答案：' + (given or '（空白）')]
        if q['quote']:
            lines.append('原文關鍵句：' + q['quote'])
        if q['context']:
            lines.append(('錄音前後文' if section == 'listening' else '原文段落') + '：\n' + q['context'])
        if q['explain']:
            lines.append('題庫解析：' + q['explain'])
        return {'cache': f'explain:ielts:{section}:{test_key}:{qno}:{_norm_given(given)}',
                'message': '\n'.join(lines), 'lang': None, 'given': given, 'answer': ' / '.join(q['answers'])}
    if kind in ('jlpt', 'topik'):
        return _mock_payload(kind, student, data)
    if kind == 'vocab':
        Attempt, Answer = _['vocab_quiz']._['Attempt'], _['vocab_quiz']._['Answer']
        try:
            a = _['db'].session.get(Attempt, int(data.get('attempt_id')))
            i = int(data.get('index'))
        except (TypeError, ValueError):
            return None
        if not a or a.student_id != student.id:
            return None
        qs = json.loads(a.questions or '[]')
        if not 0 <= i < len(qs):
            return None
        q = qs[i]
        rows = Answer.query.filter_by(attempt_id=a.id).order_by(Answer.id).all()
        if len(rows) == len(qs):
            if rows[i].is_correct:
                return None
            given = rows[i].given or ''
        else:                                   # 交卷還在存：先用前端送的答案
            given = str(data.get('given') or '')[:100]
        v = _['db'].session.get(_['Vocabulary'], q['vocab_id'])
        lang = 'ja' if q.get('ja') else ('ko' if a.course == 'TOPIK' else None)
        lines = [f'單字測驗（{LANG_NAME[lang]}單字），題型：{VOCAB_TYPE_ZH.get(q["type"], q["type"])}',
                 f'要考的字：{q["word"]}' + (f'（讀音 {q["reading"]}）' if q.get('reading') else ''),
                 f'詞性：{q.get("pos", "")}　中文意思：{v.meaning if v else q.get("meaning", "")}']
        if v and v.sentence:
            lines.append(f'課本例句：{_["clean_sentence"](v.sentence)}　{v.sentence_zh or ""}')
        if q['type'] == 'cloze':
            lines.append(f'題目：例句填空 {q.get("before", "")}____{q.get("after", "")}，正解 {q["answer"]}')
        if q.get('choices'):
            lines.append('選項：' + ' ／ '.join(q['choices']) + f'，正解 {q["answer"]}')
        lines.append('學生的答案：' + (given or '（不會，按了看答案）'))
        return {'cache': f'explain:vocab:{q["vocab_id"]}:{q["type"]}:{_norm_given(given)}',
                'message': '\n'.join(lines), 'lang': lang, 'given': given, 'answer': q['answer']}
    return None


EXPLAIN_SCHEMA = _obj({
    'why_wrong': {'type': 'string', 'description': '學生的答案為什麼錯（針對他實際寫／選的答案；空白就說明該怎麼找到答案），2–4 句'},
    'why_right': {'type': 'string', 'description': '正解為什麼對，指出原文或規則的根據，2–4 句'},
    'trap': {'type': 'string', 'description': '這題的陷阱或學生可能的誤解，1–2 句'},
    'tip': {'type': 'string', 'description': '下次遇到同類題目的判斷方法，1–2 句'},
    'practice': _obj({
        'question': {'type': 'string', 'description': '一題同類型、考同一個觀念的新小題（自己寫，不要抄原題）'},
        'options': {'type': 'array', 'items': STR, 'description': '3 或 4 個選項'},
        'answer': {'type': 'integer', 'description': '正確選項的索引，從 0 開始'},
        'explain': {'type': 'string', 'description': '這題小練習的解析，繁體中文 1–2 句'},
    }),
})

EXPLAIN_SYSTEM = COMMON_RULES + """
Task: a student got one question wrong. Explain the mistake for THIS student's actual answer.
- why_wrong: diagnose the specific wrong answer (e.g. heard a distractor that was later corrected, wrong word form, misspelling, confused NOT GIVEN with FALSE, mixed up similar kana).
- why_right: show the evidence for the key, quoting the source text when it exists.
- practice: write ONE new short multiple-choice question that tests the same skill or the same word, with its own answer index (0-based) and explanation. Options in the target language.
"""


def _clean_practice(p):
    """AI 給的小練習：選項數量、答案索引不合理就拿掉。"""
    try:
        opts = [str(o) for o in p['options']][:5]
        ans = int(p['answer'])
        if len(opts) >= 2 and 0 <= ans < len(opts) and p.get('question'):
            return {'question': str(p['question']), 'options': opts, 'answer': ans,
                    'explain': str(p.get('explain', ''))}
    except (KeyError, TypeError, ValueError):
        pass
    return None


# ---------------------------------------------------------------------------
# 2. 弱點分析（Python 統計，不靠 AI）
# ---------------------------------------------------------------------------

def _ielts_types(section, test_key, cache):
    """{題號: 題型}"""
    k = (section, test_key)
    if k not in cache:
        cache[k] = {}
        parts = (listening_bank._part_files(test_key) if section == 'listening'
                 else reading_bank._passage_files(test_key))
        for p in parts:
            for g in p['groups']:
                nos = [it['no'] for it in g.get('items', [])]
                for r in g.get('rows', []):
                    nos += [int(x) for x in re.findall(r'\{(\d+)\}', r.get('text', ''))]
                for s in g.get('sections', []):
                    for ln in s.get('lines', []):
                        nos += [int(x) for x in re.findall(r'\{(\d+)\}', ln)]
                for n in nos:
                    cache[k][n] = g['type']
    return cache[k]


def weak_profile(student, exam):
    """學生在這個考試的弱點統計。回傳 dict：
    stats（給畫面顯示的數字）、weak（弱點清單，給畫面與 AI）、examples（實際錯題，給 AI 參考）、words（不熟的字）。"""
    sid = student.id
    db = _['db']
    course = exam['course']
    prof = {'exam': exam['key'], 'exam_name': exam['name'], 'lang': exam.get('lang'),
            'stats': [], 'weak': [], 'examples': [], 'words': [], 'has_data': False}

    # ---- 單字：學了多少、不熟的字
    V, LP = _['Vocabulary'], _['LearningProgress']
    rows = (db.session.query(LP.status, V).join(V, V.id == LP.vocab_id)
            .filter(LP.student_id == sid, V.category == course).order_by(LP.last_reviewed.desc()).all())
    seen = set()
    fam = unf = 0
    weak_words = []
    for status, v in rows:
        k = v.word.lower()
        if k in seen:
            continue
        seen.add(k)
        if status == 'familiar':
            fam += 1
        else:
            unf += 1
            if len(weak_words) < 20:
                weak_words.append(v)
    prof['stats'].append({'label': '學過的單字', 'value': fam + unf, 'unit': '字'})
    prof['stats'].append({'label': '熟／不熟', 'value': f'{fam}／{unf}', 'unit': ''})
    if fam + unf:
        prof['has_data'] = True

    # ---- 背單字神器：各題型答對率、答錯的字
    vq = _['vocab_quiz']._
    QA, QAns = vq['Attempt'], vq['Answer']
    course_cond = (QA.course == course) if course != 'IELTS' else ((QA.course == course) | (QA.course.is_(None)))
    answers = (db.session.query(QAns, QA).join(QA, QA.id == QAns.attempt_id)
               .filter(QA.student_id == sid, course_cond, QA.finished_at.isnot(None))
               .order_by(QAns.id.desc()).limit(400).all())
    if answers:
        prof['has_data'] = True
        by_type = {}
        wrong_ids = []
        for ans, _a in answers:
            t = by_type.setdefault(ans.qtype, [0, 0])
            t[1] += 1
            t[0] += bool(ans.is_correct)
            if not ans.is_correct and ans.vocab_id not in wrong_ids:
                wrong_ids.append(ans.vocab_id)
        right = sum(v[0] for v in by_type.values())
        total = sum(v[1] for v in by_type.values())
        prof['stats'].append({'label': '背單字神器答對率', 'value': round(right * 100 / total), 'unit': '%'})
        for qt, (r, n) in sorted(by_type.items(), key=lambda x: x[1][0] / x[1][1]):
            if n >= 3 and r / n < 0.75:
                prof['weak'].append({'area': f'單字・{VOCAB_TYPE_ZH.get(qt, qt)}', 'detail': f'答對 {r}/{n}（{round(r * 100 / n)}%）',
                                     'rate': r / n})
        for vid in wrong_ids[:15]:
            v = db.session.get(V, vid)
            if v and v.word.lower() not in {w.word.lower() for w in weak_words}:
                weak_words.insert(0, v)
    prof['words'] = [{'word': v.word, 'reading': v.reading or '', 'pos': v.pos or '', 'meaning': v.meaning}
                     for v in weak_words[:20]]
    if prof['words']:
        prof['weak'].append({'area': '不熟的單字', 'detail': '、'.join(w['word'] for w in prof['words'][:8])
                             + ('…' if len(prof['words']) > 8 else ''), 'rate': 0.5})

    if exam['key'] == 'ielts':
        _ielts_profile(student, prof)
    elif exam['key'] == 'jlpt':
        _mock_profile(student, prof, 'jlpt')
    elif exam['key'] == 'topik':
        _mock_profile(student, prof, 'topik')
    prof['weak'].sort(key=lambda w: w['rate'])
    return prof


def _ielts_profile(student, prof):
    db = _['db']
    A, Ans = _['TestAttempt'], _['TestAnswer']
    retired = _['RETIRED_TEST_KEYS']
    attempts = (A.query.filter_by(student_id=student.id).filter(A.finished_at.isnot(None))
                .filter(A.test_key.notin_(retired)).order_by(A.finished_at.desc()).limit(20).all())
    type_cache, by_type = {}, {}
    for a in attempts:
        prof['has_data'] = True
        types = _ielts_types(a.section, a.test_key, type_cache)
        for r in Ans.query.filter_by(attempt_id=a.id).all():
            t = by_type.setdefault((a.section, types.get(r.qno, '')), [0, 0])
            t[1] += 1
            t[0] += bool(r.is_correct)
    for sec in ('listening', 'reading'):
        last = next((a for a in attempts if a.section == sec), None)
        if last:
            prof['stats'].append({'label': f'最近一次{SECTION_ZH[sec]}', 'value': f'{last.correct}/{last.total}',
                                  'unit': '題'})
    for (sec, t), (r, n) in by_type.items():
        if n >= 3 and r / n < 0.8:
            prof['weak'].append({'area': f'{SECTION_ZH[sec]}・{TYPE_ZH.get(t, t)}', 'detail': f'答對 {r}/{n}（{round(r * 100 / n)}%）',
                                 'rate': r / n})
    # 錯題本裡還沒訂正的題目，挑最近的 6 題給 AI 參考
    M = _['TestMistake']
    ms = (M.query.filter_by(student_id=student.id, corrected=False).filter(M.test_key.notin_(retired))
          .order_by(M.last_wrong_at.desc()).limit(6).all())
    for m in ms:
        q = ielts_question(m.section, m.test_key, m.qno)
        if q:
            prof['examples'].append(f'[{SECTION_ZH[m.section]} {TYPE_ZH.get(q["type"], q["type"])}] {q["prompt"]}'
                                    f' — 學生答 {m.last_given or "（空白）"}，正解 {" / ".join(q["answers"])}')
    # 寫作、口說：最近一次 AI 批改的分數與要改進的地方
    for sec, Model in (('writing', _['WritingSubmission']), ('speaking', _['SpeakingSubmission'])):
        sub = (Model.query.filter_by(student_id=student.id, ai_status='done')
               .order_by(Model.submitted_at.desc()).first())
        if not sub or not sub.ai_result:
            continue
        prof['has_data'] = True
        prof['stats'].append({'label': f'最近一次{SECTION_ZH[sec]}', 'value': sub.overall, 'unit': 'Band'})
        try:
            res = json.loads(sub.ai_result)
        except ValueError:
            continue
        steps = []
        if sec == 'writing':
            for t in (res.get('tasks') or {}).values():
                steps += t.get('next_steps', [])[:2]
        else:
            steps += res.get('next_steps', [])[:3]
        if steps:
            prof['weak'].append({'area': f'{SECTION_ZH[sec]}（AI 老師上次的建議）', 'detail': '；'.join(map(str, steps[:3])),
                                 'rate': (sub.overall or 0) / 9})


def _mock_profile(student, prof, exam_key):
    mod = _['jlpt_mock'] if exam_key == 'jlpt' else _['topik_mock']
    A = mod._['Attempt']
    rows = A.query.filter_by(student_id=student.id).order_by(A.id.desc()).limit(30).all()
    if not rows:
        return
    prof['has_data'] = True
    kinds, wrong_examples = {}, []
    for a in rows:
        if a.section == 'writing':
            continue
        if exam_key == 'jlpt':
            for k, (r, n) in json.loads(a.kinds or '{}').items():
                t = kinds.setdefault(k, [0, 0])
                t[0] += r
                t[1] += n
            test = mod.load(a.level, a.rnd or 1)
            label = f'N{a.level}'
        else:
            t = kinds.setdefault(a.section, [0, 0])
            t[0] += a.correct or 0
            t[1] += a.total or 0
            test = mod.load(a.test, a.rnd or 1)
            label = f'TOPIK {"I" * a.test}'
        if len(wrong_examples) >= 6 or not test:
            continue
        section = next((s for s in test['sections'] if s['key'] == a.section), None)
        given = json.loads(a.answers or '{}')
        for g in (section or {}).get('groups', []):
            for it in g['items']:
                if it['type'] == 'q' and int(given.get(str(it['n']), 0) or 0) != it['answer'] \
                        and len(wrong_examples) < 6 and isinstance(it['options'][0], str):
                    wrong_examples.append(f'[{label} {g["title"]}] {plain(mod.plain(it["stem"]))} — 正解 '
                                          f'{plain(mod.plain(it["options"][it["answer"] - 1]))}')
    names = JLPT_KIND_ZH if exam_key == 'jlpt' else {'listening': '聽力', 'reading': '閱讀'}
    for k, (r, n) in kinds.items():
        if not n:
            continue
        prof['stats'].append({'label': f'模擬考{names.get(k, k)}答對率', 'value': round(r * 100 / n), 'unit': '%'})
        if r / n < 0.8:
            prof['weak'].append({'area': f'模擬考・{names.get(k, k)}', 'detail': f'答對 {r}/{n}（{round(r * 100 / n)}%）',
                                 'rate': r / n})
    prof['examples'] += wrong_examples


def profile_text(prof):
    """把弱點統計寫成給 AI 看的文字。"""
    lines = [f'考試：{prof["exam_name"]}（目標語言：{LANG_NAME[prof["lang"]]}）']
    lines += [f'- {s["label"]}：{s["value"]}{s["unit"]}' for s in prof['stats']]
    if prof['weak']:
        lines.append('弱點（錯誤率高的排前面）：')
        lines += [f'- {w["area"]}：{w["detail"]}' for w in prof['weak']]
    if prof['words']:
        lines.append('不熟或答錯的單字：' + '；'.join(
            f'{w["word"]}{"（" + w["reading"] + "）" if w["reading"] else ""} {w["pos"]} {w["meaning"]}'
            for w in prof['words']))
    if prof['examples']:
        lines.append('最近答錯的題目：')
        lines += [f'- {e}' for e in prof['examples']]
    if not prof['has_data']:
        lines.append('（這位學生還沒有作答紀錄）')
    return '\n'.join(lines)


# ---------------------------------------------------------------------------
# 2. AI 弱點練習：出題與批改
# ---------------------------------------------------------------------------

PRACTICE_SCHEMA = _obj({
    'focus': {'type': 'string', 'description': '這份練習針對哪些弱點，對學生說的話，繁體中文 1–2 句'},
    'questions': {'type': 'array', 'items': _obj({
        'skill': {'type': 'string', 'description': '這題練的弱點，用上面弱點清單的名稱，例如「閱讀・是非題」「不熟的單字」'},
        'passage': {'type': 'string', 'description': '閱讀短文或對話（需要時才寫，40–90 字；不需要就給空字串）'},
        'question': {'type': 'string', 'description': '題目'},
        'options': {'type': 'array', 'items': STR, 'description': '3 或 4 個選項，不要加 A. B. 這類前綴'},
        'answer': {'type': 'integer', 'description': '正確選項的索引，從 0 開始'},
        'explain': {'type': 'string', 'description': '解析：為什麼對、其他選項為什麼錯，繁體中文 2–3 句'},
    })},
})

PRACTICE_SYSTEM = COMMON_RULES + """
Task: write a short targeted practice set for one student, based on the weakness report you are given.
- Write exactly {n} multiple-choice questions. Spread them over the weakest areas first (most questions for the lowest accuracy), and use the student's own weak words where vocabulary is weak.
- Every question must be original (do not copy the questions from the report) and must have exactly one defensible answer.
- For IELTS TRUE/FALSE/NOT GIVEN or YES/NO/NOT GIVEN practice, give a short passage and use exactly those three options in that order.
- For vocabulary items, test meaning in context (a sentence with a blank, or choosing the right word), not just translation.
- Level: match the exam ({exam}). Questions, passages and options in the target language ({lang}); explanations in Traditional Chinese.
- If the student has no records yet, write a mixed diagnostic set at a typical level for this exam.
"""

JUDGE = (['TRUE', 'FALSE', 'NOT GIVEN'], ['YES', 'NO', 'NOT GIVEN'])


def clean_questions(raw, rng=random):
    """檢查 AI 出的題：選項 2–5 個、答案索引有效、選項不重複；不合格的題目丟掉。
    AI 常把正解放在第一個，所以把選項順序打散（是非題的 TRUE／FALSE／NOT GIVEN 保持原順序）。"""
    out = []
    for q in raw or []:
        try:
            opts = [re.sub(r'^\s*[A-Da-d][\.\)．、]\s*', '', str(o)).strip() for o in q['options']]
            ans = int(q['answer'])
            question = str(q['question']).strip()
        except (KeyError, TypeError, ValueError):
            continue
        if not question or not 2 <= len(opts) <= 5 or not 0 <= ans < len(opts) \
                or len({o.lower() for o in opts}) != len(opts) or not all(opts):
            continue
        right = opts[ans]
        if [o.upper() for o in opts] not in JUDGE:
            rng.shuffle(opts)
        out.append({'skill': str(q.get('skill', '')).strip(), 'passage': str(q.get('passage', '')).strip(),
                    'question': question, 'options': opts, 'answer': opts.index(right),
                    'explain': str(q.get('explain', '')).strip()})
    return out


def make_practice(student, exam):
    prof = weak_profile(student, exam)
    system = PRACTICE_SYSTEM.format(n=PRACTICE_SIZE, exam=exam['name'] + ' ' + exam['en'],
                                    lang=LANG_NAME[exam.get('lang')])
    data, model = ask(student.id, system, profile_text(prof) + f'\n\n請出 {PRACTICE_SIZE} 題。', PRACTICE_SCHEMA)
    questions = clean_questions(data.get('questions'))
    if len(questions) < 3:
        raise RuntimeError('AI 出的題目格式不正確，請再按一次。')
    return prof, str(data.get('focus', '')), questions, model


# ---------------------------------------------------------------------------
# 3. AI 學習報告
# ---------------------------------------------------------------------------

REPORT_SCHEMA = _obj({
    'headline': {'type': 'string', 'description': '一句話總結這位學生目前的狀況（20 字內）'},
    'overview': {'type': 'string', 'description': '學習狀況總覽，3–4 句，給家長看得懂'},
    'strengths': {'type': 'array', 'items': STR, 'description': '做得好的地方，2–3 點'},
    'weaknesses': {'type': 'array', 'items': STR, 'description': '最需要加強的地方，2–3 點，要具體'},
    'plan': {'type': 'array', 'items': _obj({'when': STR, 'todo': STR}),
             'description': '接下來兩週的練習計畫，3–4 項（when 例如「第 1–3 天」）。只能建議網站上有的功能：單字庫滑卡、背單字神器、模擬考、錯題本、AI 弱點練習'},
    'parent_note': {'type': 'string', 'description': '給家長的一段話：孩子的努力、家長可以怎麼陪伴，2–3 句'},
})

REPORT_SYSTEM = COMMON_RULES + """
Task: write a study progress report about one student for parents and cram-school staff.
- Use only the numbers in the data. Do not invent scores, dates or activities that are not in the data.
- If there is little data, say honestly that the student has just started and suggest how to begin.
- Be encouraging but honest; be specific (name the weak question types or words).
"""


def make_report(student, exam):
    prof = weak_profile(student, exam)
    data, model = ask(student.id, REPORT_SYSTEM, f'學生：{student.name}\n' + profile_text(prof), REPORT_SCHEMA)
    data['model'] = model
    data['stats'] = prof['stats']
    data['weak'] = [{'area': w['area'], 'detail': w['detail']} for w in prof['weak']]
    data['made_at'] = (datetime.utcnow() + timedelta(hours=8)).strftime('%Y/%m/%d %H:%M')
    return data


# ---------------------------------------------------------------------------
# 4. AI 單字記憶法
# ---------------------------------------------------------------------------

WORD_SCHEMA = _obj({
    'mnemonic': {'type': 'string', 'description': '幫台灣學生記住這個字的口訣或聯想（字根字首、諧音、拆字或畫面），繁體中文 1–2 句，要真的和字的拼法或讀音有關'},
    'roots': {'type': 'string', 'description': '字根字首或漢字組成的說明；沒有就給空字串'},
    'examples': {'type': 'array', 'items': _obj({'sentence': STR, 'zh': STR}),
                 'description': '2 個新的例句（和課本例句不同、程度符合考試），附中文翻譯'},
    'collocations': {'type': 'array', 'items': _obj({'phrase': STR, 'zh': STR}),
                     'description': '2–3 個常用搭配詞'},
    'confusables': {'type': 'array', 'items': _obj({'word': STR, 'diff': STR}),
                    'description': '0–2 個容易混淆的字和差別（繁體中文）'},
})

WORD_SYSTEM = COMMON_RULES + """
Task: help a student remember one vocabulary item for the {exam} exam. Target language: {lang}.
The mnemonic must be genuinely linked to the spelling, roots, kanji or sound of the word; never make up a false etymology.
"""


def make_word_help(student, v, exam):
    lang = exam.get('lang')
    msg = (f'單字：{v.word}' + (f'（讀音 {v.reading}）' if v.reading else '') + f'\n詞性：{v.pos or ""}\n'
           f'中文意思：{v.meaning}\n' + (f'英文解釋：{v.meaning_en}\n' if v.meaning_en else '')
           + (f'課本例句：{_["clean_sentence"](v.sentence)}' if v.sentence else ''))
    data, model = ask(student.id, WORD_SYSTEM.format(exam=exam['name'], lang=LANG_NAME[lang]), msg, WORD_SCHEMA)
    data['model'] = model
    return data


# ---------------------------------------------------------------------------
# 路由
# ---------------------------------------------------------------------------

def _student(student_id):
    return _['get_student'](student_id)


def _api_student():
    sid = (request.view_args or {}).get('student_id')
    return _student(sid)


def _fail(msg, code=400):
    return jsonify({'ok': False, 'error': msg}), code


def _exam_for(student):
    exam = exams.current_exam()
    if not exams.can_use(student, exam['key']):
        usable = exams.exams_for(student)
        if not usable:
            abort(403, description='還沒有開通任何考試')
        exam = exams.use_exam(usable[0]['key'])
    return exam


@bp.route('/api/ai/<int:student_id>/explain', methods=['POST'])
def api_explain(student_id):
    student = _api_student()
    data = request.get_json(silent=True) or {}
    p = explain_payload(student, data)
    if not p:
        return _fail('找不到這一題的錯誤紀錄', 404)
    system = EXPLAIN_SYSTEM + f'\nTarget language of this item: {LANG_NAME[p["lang"]]}.'

    def build():
        res, model = ask(student.id, system, p['message'], EXPLAIN_SCHEMA)
        res['practice'] = _clean_practice(res.get('practice') or {})
        res['model'] = model
        return res
    try:
        res, hit = cached(p['cache'], student.id, 'explain', build)
    except RuntimeError as e:
        return _fail(str(e), 503)
    return jsonify({'ok': True, 'cached': hit, 'result': res})


@bp.route('/api/ai/<int:student_id>/word/<int:vocab_id>', methods=['POST'])
def api_word(student_id, vocab_id):
    student = _api_student()
    v = _['db'].session.get(_['Vocabulary'], vocab_id)
    if not v or v.category.startswith('TRASH:'):
        return _fail('找不到這個字', 404)
    exam = next((e for e in exams.EXAMS if e['course'] == v.category), exams.current_exam())
    try:
        res, hit = cached(f'word:{v.category}:{v.word.lower()}', student.id, 'word',
                          lambda: make_word_help(student, v, exam))
    except RuntimeError as e:
        return _fail(str(e), 503)
    return jsonify({'ok': True, 'cached': hit, 'result': res})


@bp.route('/ai/<int:student_id>/practice')
def practice_home(student_id):
    student = _student(student_id)
    exam = _exam_for(student)
    prof = weak_profile(student, exam)
    P = _['AiPractice']
    history = (P.query.filter_by(student_id=student.id, exam=exam['key'])
               .order_by(P.id.desc()).limit(8).all())
    return render_template('ai_practice.html', student=student, prof=prof, history=history, practice=None,
                           ai_ready=writing_bank.ai_ready(), ai_label=writing_bank.ai_label(),
                           left=max(0, DAILY_LIMIT - used_today(student.id)))


@bp.route('/api/ai/<int:student_id>/practice/new', methods=['POST'])
def practice_new(student_id):
    student = _student(student_id)
    exam = _exam_for(student)
    try:
        prof, focus, questions, model = make_practice(student, exam)
    except RuntimeError as e:
        return _fail(str(e), 503)
    P = _['AiPractice']
    row = P(student_id=student.id, exam=exam['key'], focus=focus,
            weak=json.dumps([w['area'] for w in prof['weak']], ensure_ascii=False),
            questions=json.dumps(questions, ensure_ascii=False), total=len(questions), model=model)
    _['db'].session.add(row)
    _['db'].session.commit()
    return jsonify({'ok': True, 'url': url_for('ai_tutor.practice_take', student_id=student.id, pid=row.id)})


def _practice(student, pid):
    row = _['db'].session.get(_['AiPractice'], pid)
    if not row or row.student_id != student.id:
        abort(404, description='找不到這份練習')
    return row


def public_questions(questions):
    """作答前給前端的題目：不含答案與解析。"""
    return [{k: q[k] for k in ('skill', 'passage', 'question', 'options')} for q in questions]


@bp.route('/ai/<int:student_id>/practice/<int:pid>')
def practice_take(student_id, pid):
    student = _student(student_id)
    row = _practice(student, pid)
    exams.use_exam(row.exam) if row.exam in exams.EXAM_BY_KEY else None
    questions = json.loads(row.questions)
    review = None
    if row.finished_at:
        review = {'answers': json.loads(row.answers or '[]'), 'questions': questions}
    return render_template('ai_practice.html', student=student, practice=row, prof=None, history=None,
                           questions=public_questions(questions), review=review,
                           ai_ready=True, ai_label=writing_bank.ai_label(), left=None)


def grade_practice(questions, given):
    """批改：given 是每題選的索引（-1 或 None 是沒作答）。回傳 (答對題數, 正規化後的答案)。"""
    out = []
    for i, q in enumerate(questions):
        g = given[i] if i < len(given) else None
        out.append(g if isinstance(g, int) and 0 <= g < len(q['options']) else -1)
    return sum(1 for q, g in zip(questions, out) if g == q['answer']), out


@bp.route('/api/ai/<int:student_id>/practice/<int:pid>/submit', methods=['POST'])
def practice_submit(student_id, pid):
    student = _api_student()
    row = _practice(student, pid)
    questions = json.loads(row.questions)
    if not row.finished_at:
        data = request.get_json(silent=True) or {}
        given = data.get('answers')
        if not isinstance(given, list):
            return _fail('資料不正確')
        row.correct, answers = grade_practice(questions, given)
        row.answers = json.dumps(answers)
        row.finished_at = datetime.utcnow()
        _['db'].session.commit()
    return jsonify({'ok': True, 'correct': row.correct, 'total': row.total,
                    'answers': json.loads(row.answers or '[]'),
                    'key': [{'answer': q['answer'], 'explain': q['explain']} for q in questions]})


def _report_key(student, exam):
    return f'report:{student.id}:{exam["key"]}:{(datetime.utcnow() + timedelta(hours=8)).strftime("%Y%m%d")}'


@bp.route('/ai/<int:student_id>/report')
def report_page(student_id):
    student = _student(student_id)
    exam = _exam_for(student)
    Cache = _['AiCache']
    # 最近一份報告（今天的或以前的）
    row = (Cache.query.filter(Cache.key.like(f'report:{student.id}:{exam["key"]}:%'))
           .order_by(Cache.id.desc()).first())
    report = json.loads(row.result) if row else None
    prof = weak_profile(student, exam)
    return render_template('ai_report.html', student=student, report=report, prof=prof,
                           ai_ready=writing_bank.ai_ready(), ai_label=writing_bank.ai_label())


@bp.route('/api/ai/<int:student_id>/report', methods=['POST'])
def api_report(student_id):
    student = _api_student()
    exam = _exam_for(student)
    Cache, db = _['AiCache'], _['db']
    key = _report_key(student, exam)
    try:
        data = make_report(student, exam)
    except RuntimeError as e:
        return _fail(str(e), 503)
    Cache.query.filter_by(key=key).delete()      # 同一天重新產生：覆蓋
    db.session.add(Cache(key=key, kind='report', student_id=student.id, model=data.get('model', ''),
                         result=json.dumps(data, ensure_ascii=False)))
    db.session.commit()
    return jsonify({'ok': True})


# ---------------------------------------------------------------------------
# 掛到主程式
# ---------------------------------------------------------------------------

def ai_slot(kind, **ref):
    """樣板用：{{ ai_slot('ielts', section='reading', test_key=..., qno=...) }} 產生「問 AI 老師」按鈕的位置，
    static/ai_tutor.js 會把它變成按鈕。"""
    payload = json.dumps(dict(ref, kind=kind), ensure_ascii=False)
    sid = (request.view_args or {}).get('student_id', '')
    return Markup('<div class="ai-slot" data-sid="%s" data-ai="%s"></div>') % (sid, payload)


def register(app, db, deps):
    _.update(deps, db=db)

    class AiCache(db.Model):
        """AI 回覆的快取：錯題解釋、單字記憶法（大家共用），學習報告（每人每天一份）。"""
        id = db.Column(db.Integer, primary_key=True)
        key = db.Column(db.String(300), unique=True, nullable=False)
        kind = db.Column(db.String(20))
        student_id = db.Column(db.Integer)        # 第一次請 AI 產生的學生（算每日次數用）
        model = db.Column(db.String(60))
        result = db.Column(db.Text)
        created_at = db.Column(db.DateTime, default=datetime.utcnow)

    class AiPractice(db.Model):
        """一份 AI 依弱點出的練習題。"""
        id = db.Column(db.Integer, primary_key=True)
        student_id = db.Column(db.Integer, db.ForeignKey('student.id'), nullable=False)
        exam = db.Column(db.String(20))
        focus = db.Column(db.Text)                # AI 說這份練習針對什麼
        weak = db.Column(db.Text)                 # 出題時的弱點清單（JSON）
        questions = db.Column(db.Text)            # 題目、選項、答案、解析（JSON）
        answers = db.Column(db.Text)              # 學生選的索引（JSON）
        total = db.Column(db.Integer, default=0)
        correct = db.Column(db.Integer)
        model = db.Column(db.String(60))
        created_at = db.Column(db.DateTime, default=datetime.utcnow)
        finished_at = db.Column(db.DateTime)

    _.update(AiCache=AiCache, AiPractice=AiPractice)
    with app.app_context():
        db.create_all()
    app.jinja_env.globals['ai_slot'] = ai_slot
    app.register_blueprint(bp)
