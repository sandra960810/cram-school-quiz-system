"""檢查 AI 學習教練（ai_tutor.py）：錯題解釋、弱點練習、學習報告、單字記憶法。

用法：python tools/check_ai_tutor.py

- 先把 instance/quiz.db 複製到暫存資料夾，整個檢查都在複本上跑，不會動到真的學生資料
- AI 換成「假的 AI 老師」：記下送給 AI 的內容、照各功能的 JSON 格式回答，所以不用金鑰、不花錢，
  檢查的是「送給 AI 的題目內容對不對、AI 回來的東西有沒有正確存檔與顯示、權限與次數限制有沒有作用」
- 加上 --real 會改用 ai_key.txt 的真金鑰，實際問一次錯題解釋、單字記憶法與出題（會花一點點費用）
全部通過會印出「全部通過」，有錯會列出哪一項失敗。
"""
import json
import os
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
REAL = '--real' in sys.argv

tmp = tempfile.mkdtemp(prefix='ai_check_')
src = os.path.join(ROOT, 'instance', 'quiz.db')
if os.path.exists(src):
    shutil.copy(src, os.path.join(tmp, 'quiz.db'))
os.environ['QUIZ_DB_URI'] = 'sqlite:///' + os.path.join(tmp, 'quiz.db').replace('\\', '/')

import app as site  # noqa: E402
import ai_tutor  # noqa: E402
import writing_bank  # noqa: E402

failures = []


def check(cond, what):
    print(('  ✓ ' if cond else '  ✗ ') + what)
    if not cond:
        failures.append(what)


# ---------------------------------------------------------------- 假的 AI 老師
calls = []


def fake_ask_json(system, message, schema, effort='high'):
    calls.append({'system': system, 'message': message, 'schema': schema, 'effort': effort})
    props = schema['properties']
    if 'why_wrong' in props:
        return {'why_wrong': '你把被否定的選項當成答案。', 'why_right': '原文明確說是另一個。',
                'trap': '先說一個再更正。', 'tip': '聽到 but 要小心。',
                'practice': {'question': 'Pick the odd one.', 'options': ['a', 'b', 'c'], 'answer': 2,
                             'explain': '因為 c。'}}, 'fake-model'
    if 'questions' in props:
        qs = [{'skill': '閱讀・是非題', 'passage': 'Bees were given away.', 'question': 'The honey was sold.',
               'options': ['TRUE', 'FALSE', 'NOT GIVEN'], 'answer': 1, 'explain': '送不是賣。'}]
        qs += [{'skill': '不熟的單字', 'passage': '', 'question': f'Question {i}', 'options':
                [f'A. right{i}', f'B. wrong{i}a', f'C. wrong{i}b', f'D. wrong{i}c'], 'answer': 0,
                'explain': f'解析{i}'} for i in range(1, 8)]
        qs.append({'skill': 'x', 'passage': '', 'question': 'bad', 'options': ['same', 'same'], 'answer': 5,
                   'explain': ''})   # 不合格：會被丟掉
        return {'focus': '針對是非題和不熟的單字。', 'questions': qs}, 'fake-model'
    if 'headline' in props:
        return {'headline': '穩定進步中', 'overview': '這是總覽。', 'strengths': ['單字量增加'],
                'weaknesses': ['是非題'], 'plan': [{'when': '第 1–3 天', 'todo': '做 AI 弱點練習'}],
                'parent_note': '請多鼓勵。'}, 'fake-model'
    if 'mnemonic' in props:
        return {'mnemonic': '口訣', 'roots': '字根', 'examples': [{'sentence': 'Example one.', 'zh': '例一'}],
                'collocations': [{'phrase': 'make a ~', 'zh': '做'}], 'confusables': []}, 'fake-model'
    raise AssertionError('沒見過的 schema')


real_ask_json = writing_bank.ask_json
if not REAL:
    writing_bank.ask_json = fake_ask_json
    writing_bank.ai_ready = lambda: True

app, db = site.app, site.db
client = app.test_client()


def post(url, body=None):
    return client.post(url, data=json.dumps(body or {}), content_type='application/json')


with app.app_context():
    S = site.Student
    stu = S(token='ai-check-1', name='AI 測試生', status='demo')
    other = S(token='ai-check-2', name='別人', status='demo')
    db.session.add_all([stu, other])
    db.session.commit()
    SID, OID = stu.id, other.id

print('1. 雅思閱讀：交卷後答錯的題目有「問 AI 老師」')
with app.app_context():
    key = site.reading_bank.answer_key('R01')
form = {f'q_{n}': ans[0] for n, ans in key.items()}
form['q_1'] = 'TRUE'        # 第 1 題正解是 FALSE
form['q_7'] = 'zzz'         # 填空題答錯
r = client.post(f'/exam/{SID}/reading/R01/submit', data=form)
check(r.status_code == 302, '閱讀交卷成功')
result_url = r.headers['Location']
html = client.get(result_url).get_data(as_text=True)
check(html.count('class="ai-slot"') == 2, '只有答錯的 2 題有 AI 按鈕')
check('ai_tutor.js' in html and 'ai_tutor.css' in html, '成績頁載入 AI 的 JS／CSS')
attempt_id = int(result_url.rstrip('/').split('/')[-1])

print('2. AI 解釋錯題：送給 AI 的內容')
calls.clear()
r = post(f'/api/ai/{SID}/explain', {'kind': 'ielts', 'section': 'reading', 'test_key': 'R01', 'qno': 1,
                                     'attempt_id': attempt_id})
d = r.get_json()
check(r.status_code == 200 and d['ok'], '解釋成功')
if not REAL:
    msg = calls[0]['message'] if calls else ''
    check('The London hotel originally sold the honey' in msg, '題目內容是伺服器從題庫找的')
    check('學生的答案：TRUE' in msg and '正解（可接受的寫法）：FALSE' in msg, '附上學生答案與正解')
    check('given away to guests' in msg, '附上原文段落')
    check(calls[0]['effort'] == 'low', 'Claude 用 low effort（回得快）')
    check(d['result']['practice']['answer'] == 2 and d['cached'] is False, '小練習格式正確、第一次不是快取')
calls.clear()
r = post(f'/api/ai/{SID}/explain', {'kind': 'ielts', 'section': 'reading', 'test_key': 'R01', 'qno': 1,
                                     'attempt_id': attempt_id})
check(r.get_json()['cached'] is True and not calls, '同一題同一個錯誤答案第二次用快取，不再呼叫 AI')
r = post(f'/api/ai/{SID}/explain', {'kind': 'ielts', 'section': 'reading', 'test_key': 'R01', 'qno': 2,
                                     'attempt_id': attempt_id})
check(r.status_code == 404, '答對的題目不能問（不浪費額度）')
r = post(f'/api/ai/{OID}/explain', {'kind': 'ielts', 'section': 'reading', 'test_key': 'R01', 'qno': 7,
                                     'attempt_id': attempt_id})
check(r.status_code == 404, '別人的作答紀錄查不到')
r = post(f'/api/ai/{SID}/explain', {'kind': 'ielts', 'section': 'reading', 'test_key': '../x', 'qno': 1})
check(r.status_code == 404, '不存在的試卷回 404')
r = post(f'/api/ai/{SID}/explain', {'kind': 'ielts', 'section': 'reading', 'test_key': 'R01', 'qno': 7})
check(r.status_code == 200, '錯題本（沒帶 attempt_id）也能問')
html = client.get(f'/exam/{SID}/mistakes').get_data(as_text=True)
check(html.count('class="ai-slot"') == 2, '錯題本每一題都有 AI 按鈕')

print('3. 雅思聽力')
with app.app_context():
    lkey = site.listening_bank.answer_key('L01')
form = {f'q_{n}': ans[0] for n, ans in lkey.items()}
form['q_11'] = 'A'
r = client.post(f'/exam/{SID}/listening-bank/L01/submit', data=form)
lid = int(r.headers['Location'].rstrip('/').split('/')[-1])
check(client.get(r.headers['Location']).get_data(as_text=True).count('class="ai-slot"') == 1, '聽力成績頁答錯 1 題有按鈕')
calls.clear()
r = post(f'/api/ai/{SID}/explain', {'kind': 'ielts', 'section': 'listening', 'test_key': 'L01', 'qno': 11,
                                     'attempt_id': lid})
check(r.status_code == 200, '聽力解釋成功')
if not REAL:
    check('private estate' in calls[0]['message'] and 'royal hunting ground' in calls[0]['message'],
          '附上選項與錄音前後文')

print('4. 日檢、韓檢模擬考檢討頁')
r = client.post(f'/jlpt-mock/{SID}/N5/vocab', data={})
jl = client.get(r.headers['Location'])
jhtml = jl.get_data(as_text=True)
check(jl.status_code == 200 and 'class="ai-slot"' in jhtml, '日檢檢討頁有 AI 按鈕')
jid = int(r.headers['Location'].rstrip('/').split('/')[-1])
calls.clear()
r = post(f'/api/ai/{SID}/explain', {'kind': 'jlpt', 'attempt_id': jid, 'n': 1})
check(r.status_code == 200, '日檢解釋成功')
if not REAL:
    check('學生選：（沒有作答）' in calls[0]['message'] and '正解：' in calls[0]['message'], '日檢附上正解與學生作答')
r = client.post(f'/topik-mock/{SID}/t1/reading', data={})
th = client.get(r.headers['Location'])
check(th.status_code == 200 and 'class="ai-slot"' in th.get_data(as_text=True), '韓檢檢討頁有 AI 按鈕')
tid = int(r.headers['Location'].rstrip('/').split('/')[-1])
with app.app_context():
    a = db.session.get(site.topik_mock._['Attempt'], tid)
    first_n = int(next(iter(json.loads(a.answers))))
r = post(f'/api/ai/{SID}/explain', {'kind': 'topik', 'attempt_id': tid, 'n': first_n})
check(r.status_code == 200, '韓檢解釋成功')

print('5. 背單字神器：答錯的字問 AI')
client.set_cookie('exam', 'ielts')
with app.app_context():
    words = site.Vocabulary.query.filter_by(category='IELTS').limit(6).all()
    wids = [w.id for w in words]
for i, w in enumerate(wids):
    post('/api/update_progress', {'student_id': SID, 'vocab_id': w, 'status': 'familiar' if i % 2 else 'unfamiliar'})
r = client.get(f'/vocab-quiz/{SID}/start?scope=all&n=5&type=spell')
check(r.status_code == 200 and 'ai_tutor.js' in r.get_data(as_text=True), '單字測驗頁載入 AI 的 JS')
with app.app_context():
    VA = site.vocab_quiz._['Attempt']
    qa = VA.query.filter_by(student_id=SID).order_by(VA.id.desc()).first()
    qs = json.loads(qa.questions)
post('/api/vocab-quiz/submit', {'attempt_id': qa.id, 'student_id': SID, 'answers': ['wrongg'] + [q['answer'] for q in qs[1:]]})
calls.clear()
r = post(f'/api/ai/{SID}/explain', {'kind': 'vocab', 'attempt_id': qa.id, 'index': 0})
check(r.status_code == 200, '單字解釋成功')
if not REAL:
    check('學生的答案：wrongg' in calls[0]['message'] and qs[0]['word'] in calls[0]['message'], '附上要考的字與學生拼的')
r = post(f'/api/ai/{SID}/explain', {'kind': 'vocab', 'attempt_id': qa.id, 'index': 1})
check(r.status_code == 404, '答對的字不能問')

print('6. 弱點分析與 AI 弱點練習')
with app.app_context():
    stu = db.session.get(S, SID)
    with app.test_request_context(f'/ai/{SID}/practice?exam=ielts'):
        prof = ai_tutor.weak_profile(stu, site.exams.EXAM_BY_KEY['ielts'])
areas = [w['area'] for w in prof['weak']]
check(prof['has_data'] and any('不熟的單字' in a for a in areas), '弱點包含不熟的單字')
check(any(s['label'] == '最近一次閱讀' and s['value'] == f'{len(key) - 2}/{len(key)}' for s in prof['stats']),
      '最近一次閱讀分數由程式算出')
html = client.get(f'/ai/{SID}/practice?exam=ielts').get_data(as_text=True)
check('你的弱點分析' in html and '依我的弱點出 8 題' in html, '練習首頁顯示弱點與出題按鈕')
calls.clear()
r = post(f'/api/ai/{SID}/practice/new?exam=ielts')
d = r.get_json()
check(r.status_code == 200 and d['ok'], '出題成功')
if not REAL:
    check('不熟的單字' in calls[0]['message'] and 'The London hotel' in calls[0]['message'],
          '出題時把弱點與實際錯題交給 AI')
take = client.get(d['url'])
thtml = take.get_data(as_text=True)
pid = int(d['url'].rstrip('/').split('/')[-1])
with app.app_context():
    row = db.session.get(ai_tutor._['AiPractice'], pid)
    stored = json.loads(row.questions)
if not REAL:
    check(len(stored) == 8, '不合格的題目被丟掉，留下 8 題')
    check(stored[0]['options'] == ['TRUE', 'FALSE', 'NOT GIVEN'] and stored[0]['answer'] == 1, '是非題選項順序不變')
    check(all(not o.startswith('A.') for q in stored for o in q['options']), '拿掉 AI 加的 A. B. 前綴')
    check('解析1' not in thtml and '"answer"' not in thtml, '作答頁不會洩漏答案與解析')
picks = [q['answer'] for q in stored]
picks[0] = 0
r = post(f'/api/ai/{SID}/practice/{pid}/submit', {'answers': picks})
d = r.get_json()
check(d['correct'] == len(stored) - 1, '伺服器批改：答錯一題')
r = post(f'/api/ai/{SID}/practice/{pid}/submit', {'answers': [q['answer'] for q in stored]})
check(r.get_json()['correct'] == len(stored) - 1, '交過的卷不能重交改分數')
check(client.get(f'/ai/{OID}/practice/{pid}').status_code == 404, '別人的練習看不到')

print('7. AI 學習報告')
r = post(f'/api/ai/{SID}/report?exam=ielts')
check(r.status_code == 200, '產生報告成功')
html = client.get(f'/ai/{SID}/report?exam=ielts').get_data(as_text=True)
if not REAL:
    check('穩定進步中' in html and '請多鼓勵' in html and '第 1–3 天' in html, '報告頁顯示 AI 寫的內容')
check('學過的單字' in html and '列印' in html, '報告頁有程式算的數據與列印按鈕')

print('8. AI 單字記憶法')
calls.clear()
r = post(f'/api/ai/{SID}/word/{wids[0]}')
check(r.status_code == 200 and r.get_json()['ok'], '記憶法成功')
r = post(f'/api/ai/{OID}/word/{wids[0]}')
check(r.get_json()['cached'] is True and len(calls) <= 1, '同一個字別的學生用快取')
html = client.get(f'/learn/{SID}/theme/{site.theme_key_of(words[0])}/word/{wids[0]}').get_data(as_text=True)
check('AI 記憶法' in html and 'ai_tutor.js' in html, '單字卡有 AI 記憶法按鈕')

print('9. 主選單、沒有金鑰、次數上限')
html = client.get(f'/dashboard/{SID}/ielts').get_data(as_text=True)
check('學習報告' in html and 'AI 學習教練' not in html, '主選單上方有學習報告，不另開 AI 區')
for url in (f'/vocab-quiz/{SID}', f'/exam/{SID}', f'/jlpt-mock/{SID}', f'/topik-mock/{SID}'):
    page = client.get(url).get_data(as_text=True)
    check('/ai/%d/practice' % SID in page, f'{url} 裡有 AI 弱點練習入口')
for ek in ('toeic', 'jlpt', 'topik', 'basic', 'general'):
    r1 = client.get(f'/ai/{SID}/practice?exam={ek}')
    r2 = client.get(f'/ai/{SID}/report?exam={ek}')
    check(r1.status_code == 200 and r2.status_code == 200, f'{ek} 的 AI 練習與報告頁打得開')
if not REAL:
    writing_bank.ai_ready = lambda: False
    r = post(f'/api/ai/{SID}/word/{wids[1]}')
    check(r.status_code == 503 and 'set_ai_key.bat' in r.get_json()['error'], '沒有金鑰時說明要設定金鑰')
    check('AI 老師還沒設定' in client.get(f'/ai/{SID}/practice').get_data(as_text=True), '練習頁提示還沒設定')
    writing_bank.ai_ready = lambda: True
    ai_tutor.DAILY_LIMIT = 1
    r = post(f'/api/ai/{SID}/word/{wids[2]}')
    check(r.status_code == 503 and '明天再來' in r.get_json()['error'], '超過每日次數會擋下')
    r = post(f'/api/ai/{SID}/word/{wids[0]}')
    check(r.status_code == 200, '已經有快取的不受次數限制')
    ai_tutor.DAILY_LIMIT = 60

print('10. 出題結果的檢查（clean_questions）')
cq = ai_tutor.clean_questions([
    {'question': 'q', 'options': ['x', 'y', 'z', 'w'], 'answer': 3},
    {'question': 'q', 'options': ['YES', 'NO', 'NOT GIVEN'], 'answer': 2},
    {'question': '', 'options': ['a', 'b'], 'answer': 0},
    {'question': 'q', 'options': ['a'], 'answer': 0},
    {'question': 'q', 'options': ['a', 'b'], 'answer': -1},
    {'question': 'q', 'options': 'ab', 'answer': 'x'},
])
check(len(cq) == 2 and cq[0]['options'][cq[0]['answer']] == 'w' and cq[1]['answer'] == 2,
      '打散選項後答案仍指向同一個選項；不合格的丟掉')

if not REAL:
    print(f'11. 每月次數限制（雅思寫作、口說、韓檢寫作、學習報告每項每月 {ai_tutor.MONTHLY_LIMIT} 次）')
    L = ai_tutor.MONTHLY_LIMIT
    real_grade_all = writing_bank.grade_all
    writing_bank.grade_all = lambda test, essays: {'tasks': {}, 'overall': 6.0, 'model': 'fake-model'}
    with app.app_context():
        subs = [site.WritingSubmission(student_id=SID, test_key='W01', task1='a', task2='b') for _ in range(L + 1)]
        db.session.add_all(subs)
        db.session.commit()
        sub_ids = [x.id for x in subs]
    codes = [client.post(f'/exam/{SID}/writing/result/{i}/grade').status_code for i in sub_ids]
    check(codes[:L] == [200] * L and codes[L] == 429, f'雅思寫作批改第 {L + 1} 次擋下（429）')
    with app.app_context():
        check(ai_tutor.monthly_left(SID, 'writing') == 0, '本月剩 0 次')
        last = db.session.get(site.WritingSubmission, sub_ids[L])
        check(last.ai_status == 'error' and f'{L} 次' in (last.ai_error or ''), '超過的那份記下原因，頁面看得到')
        check(ai_tutor.monthly_left(SID, 'speaking') == L, '口說次數分開算')
    html = client.get(f'/exam/{SID}/writing/result/{sub_ids[L]}').get_data(as_text=True)
    check('quota-note' in html, '寫作成績頁顯示本月剩幾次')
    # 學習報告：第 7 項已經用掉 1 次
    codes = [post(f'/api/ai/{SID}/report?exam=ielts&again=1').status_code for _ in range(L)]
    check(codes[-1] == 429 and codes.count(200) == L - 1, f'學習報告每月 {L} 次，超過擋下')
    with app.app_context():
        old = ai_tutor._['AiUsage'].query.filter_by(student_id=SID, feature='report').all()
        for u in old:
            u.created_at = ai_tutor.month_start_utc() - site.timedelta(minutes=1)
        db.session.commit()
        check(ai_tutor.monthly_left(SID, 'report') == L, '上個月的次數不算（每月 1 號恢復）')
    import admin
    real_logged_in = admin.logged_in
    admin.logged_in = lambda: True
    with app.test_request_context():
        staff_left = ai_tutor.monthly_left(SID, 'writing')
    admin.logged_in = real_logged_in
    check(staff_left is None, '工作人員不限次數')
    writing_bank.grade_all = real_grade_all

    print('12. 免費額度用完自動改用付費金鑰')
    saved = (writing_bank.ai_config, writing_bank.paid_config, writing_bank._gemini_json,
             writing_bank._claude_json, writing_bank.PAID_LOG)
    used = []

    def free_gemini(key, *a, **k):
        used.append(('gemini', key))
        raise writing_bank.FreeQuotaError('Gemini 免費額度暫時用完了')

    def paid_claude(key, *a, **k):
        used.append(('claude', key))
        return '{"ok": 1}', writing_bank.CLAUDE_MODEL
    writing_bank.ai_config = lambda: ('gemini', 'AIza-free')
    writing_bank._gemini_json, writing_bank._claude_json = free_gemini, paid_claude
    writing_bank.PAID_LOG = os.path.join(tmp, 'paid_log.txt')
    writing_bank.paid_config = lambda: ('claude', 'sk-ant-paid')
    data, model = real_ask_json('sys', 'msg', {'type': 'object', 'properties': {}})
    check(data == {'ok': 1} and used == [('gemini', 'AIza-free'), ('claude', 'sk-ant-paid')],
          '免費的回 429 時改用付費金鑰再問一次')
    check(model == 'claude-sonnet-5-5', '付費的是中階模型 Claude Sonnet 5.5')
    check(os.path.exists(writing_bank.PAID_LOG), '改用付費的次數記在 ai_paid_log.txt')
    writing_bank.paid_config = lambda: (None, '')
    try:
        real_ask_json('sys', 'msg', {'type': 'object', 'properties': {}})
        check(False, '沒有付費金鑰時照舊顯示額度用完')
    except RuntimeError as e:
        check('額度' in str(e), '沒有付費金鑰時照舊顯示額度用完')

    class E429(Exception):
        code = 429
    check(isinstance(writing_bank.gemini_exc(E429('x')), writing_bank.FreeQuotaError), 'Gemini 429 會轉成額度用完')
    (writing_bank.ai_config, writing_bank.paid_config, writing_bank._gemini_json,
     writing_bank._claude_json, writing_bank.PAID_LOG) = saved

shutil.rmtree(tmp, ignore_errors=True)
print()
if failures:
    print(f'有 {len(failures)} 項沒通過：')
    for f in failures:
        print('  - ' + f)
    sys.exit(1)
print('全部通過')
