"""展示模式：給主管或外部人員看的線上展示版用。

只有在環境變數 DEMO_MODE=1 時才會啟動（櫃台電腦平常執行 run.bat 不受影響）。
展示模式會：

- 每一頁最上方加一條「展示版」提示
- 首頁 / 直接導向展示學生的主介面 /dashboard/1
- 準備一位假學生「展示學生」，並先學過一些單字，主介面和單字測驗區才有內容可看
- 不接任何 AI 金鑰：寫作與口說的「AI 老師批改」改成回傳一份預先寫好的範例批改，
  並清楚標示這不是針對該次作答的真實評分

線上主機（Render）的設定寫在 render.yaml。
"""
import os
import random

from markupsafe import Markup

DEMO = os.environ.get('DEMO_MODE') == '1'
DEMO_STUDENT_ID = 1

BANNER = Markup(
    '<div style="position:sticky;top:0;z-index:9999;background:#fff4d6;color:#7a5200;'
    'border-bottom:1px solid #f0d58c;padding:8px 16px;font-size:14px;text-align:center;'
    'font-family:system-ui,-apple-system,\'Microsoft JhengHei\',sans-serif;line-height:1.5">'
    '<b>展示版</b>：這是給主管瀏覽用的展示網站，學生資料是假的，AI 老師批改顯示的是範例結果。'
    '作答紀錄不會保存到補習班的正式系統。</div>'
)

DEMO_NOTE = ('【展示版範例】這是預先寫好的示範批改，不是 AI 針對這次作答的真實評分；'
             '正式版會由 AI 老師逐份批改。')


# ---------------------------------------------------------------- 範例批改

def _writing_sample(task):
    from writing_bank import CRITERIA, task_band
    bands = {'ta': 6, 'tr': 6, 'cc': 6, 'lr': 6, 'gra': 5}
    reasons = {
        'ta': '有描述主要趨勢，但缺少明確的 overview，數據比較不夠完整。',
        'tr': '有回應題目並表明立場，但論點展開不足，例子偏籠統。',
        'cc': '段落分明，連接詞使用正確但重複（however、moreover 出現多次）。',
        'lr': '詞彙大致足夠，偶有搭配不自然，少量拼字錯誤。',
        'gra': '能使用部分複雜句，但時態與主詞動詞一致的錯誤影響閱讀。',
    }
    criteria = {k: {'band': bands[k], 'reason': reasons[k]} for k, _, _ in CRITERIA[task['no']]}
    data = {
        'criteria': criteria,
        'summary': DEMO_NOTE + ' 整體結構清楚，看得出有練過雅思寫作的段落安排；'
                   '主要失分在論點展開與文法正確性，修正後有機會到 6.5。',
        'errors': [
            {'original': 'The number of people who use bicycle have increased.',
             'correction': 'The number of people who use bicycles has increased.',
             'explain': '主詞是 The number（單數），動詞要用 has；bicycle 在這裡要用複數。'},
            {'original': 'In my opinion, I think that…',
             'correction': 'In my opinion, …',
             'explain': 'In my opinion 和 I think 意思重複，擇一即可。'},
            {'original': 'It can make people more convenient.',
             'correction': 'It can make life more convenient for people.',
             'explain': 'convenient 形容事物，不能形容人。'},
        ],
        'next_steps': ['每段開頭先寫一句主題句，後面用具體例子支撐',
                       '交卷前固定檢查主詞與動詞單複數',
                       'Task 1 一定要寫 overview，點出最明顯的兩個趨勢'],
        'model_paragraph': ('Overall, the most striking feature is the steady rise in cycling, '
                            'while car use declined over the same period.' if task['no'] == 1 else
                            'Admittedly, online learning offers flexibility; however, it cannot fully replace '
                            'the immediate feedback and motivation that face-to-face classes provide.'),
    }
    data['band'] = task_band(data)
    data['model'] = '展示版範例'
    return data


def _speaking_sample(test, answers):
    from speaking_bank import CRITERIA, overall_band
    bands = {'fc': 6, 'lr': 6, 'gra': 5, 'p': 6}
    reasons = {
        'fc': '回答大致流暢，但 Part 2 後半有較多停頓與重複。',
        'lr': '日常話題詞彙足夠，抽象議題時用字較為重複。',
        'gra': '以簡單句為主，過去式使用不穩定。',
        'p': '整體清楚易懂，少數字重音位置錯誤。',
    }
    data = {
        'criteria': {k: {'band': bands[k], 'reason': reasons[k]} for k, _, _ in CRITERIA},
        'summary': DEMO_NOTE + ' 回答有切題，願意延伸說明；若能多用連接詞串起想法、'
                   '並穩定使用過去式，分數可以再往上。',
        'errors': [
            {'original': 'Last year I go to Japan with my family.',
             'correction': 'Last year I went to Japan with my family.',
             'explain': '講過去的經驗要用過去式。'},
            {'original': 'It is very interesting for me.',
             'correction': 'I find it really interesting.',
             'explain': '更自然的說法，也能展現詞彙變化。'},
        ],
        'pronunciation': [
            {'item': 'comfortable', 'issue': '唸成四個音節 com-for-ta-ble',
             'tip': '重音在第一音節，唸成三個音節 COMF-ta-ble'},
            {'item': 'environment', 'issue': '重音放在最後',
             'tip': '重音在第二音節 en-VI-ron-ment'},
        ],
        'next_steps': ['Part 2 準備時寫下 3–4 個關鍵字，照順序講完',
                       '練習用 because / so / which 把短句接成長句',
                       '每天跟讀 5 分鐘，注意字重音'],
        'model_answer': {'qid': answers[0]['qid'] if answers else '',
                         'text': 'I live in a flat in the city centre. What I like most is how convenient it is; '
                                 'there is a metro station just around the corner.'},
    }
    data['transcripts'] = {a['qid']: a.get('transcript', '') for a in answers}
    data['transcript_source'] = 'browser'
    data['overall'] = overall_band(data)
    data['model'] = '展示版範例'
    data['provider'] = 'demo'
    return data


# ---------------------------------------------------------------- 假資料

def _seed(db, models):
    """展示學生先學過一些單字（每次啟動檢查，已經有就不重複）。"""
    Student, Vocabulary, LearningProgress = models['Student'], models['Vocabulary'], models['LearningProgress']
    student = db.session.get(Student, DEMO_STUDENT_ID)
    if not student:
        student = Student(id=DEMO_STUDENT_ID, token='demo', name='展示學生', enrolled_course='IELTS')
        db.session.add(student)
    else:
        student.name = '展示學生'
    db.session.commit()
    if LearningProgress.query.filter_by(student_id=student.id).count() >= 50:
        return
    rng = random.Random(2026)
    themes = [t for (t,) in db.session.query(Vocabulary.theme)
              .filter(Vocabulary.category == student.enrolled_course).distinct().order_by(Vocabulary.theme)]
    for i, theme in enumerate(themes[:6]):
        words = Vocabulary.query.filter_by(category=student.enrolled_course, theme=theme).order_by(Vocabulary.id).all()
        take = words[:max(5, len(words) * (60 - i * 8) // 100)]
        for v in take:
            status = 'familiar' if rng.random() < 0.7 else 'unfamiliar'
            if not LearningProgress.query.filter_by(student_id=student.id, vocab_id=v.id).first():
                db.session.add(LearningProgress(student_id=student.id, vocab_id=v.id, status=status))
    db.session.commit()


# ---------------------------------------------------------------- 掛上 app

def setup(app, db, models):
    if not DEMO:
        return
    import writing_bank
    import speaking_bank
    from flask import redirect

    # AI 老師：不接金鑰，改成範例批改
    for mod in (writing_bank, speaking_bank):
        mod.ai_ready = lambda: True
        mod.ai_label = lambda: '展示版範例批改（未連接 AI）'
        mod.ai_config = lambda: ('demo', '')

    original_grade_task = writing_bank.grade_task

    def grade_task(task, essay):
        if writing_bank.count_words(essay) == 0:
            return original_grade_task(task, essay)    # 空白卷照原本規則
        return _writing_sample(task)
    writing_bank.grade_task = grade_task

    def grade(test, answers):
        return _speaking_sample(test, answers)
    speaking_bank.grade = grade

    @app.route('/')
    def demo_home():
        return redirect(f'/dashboard/{DEMO_STUDENT_ID}')

    @app.after_request
    def add_banner(resp):
        if resp.mimetype == 'text/html' and not resp.direct_passthrough:
            html = resp.get_data(as_text=True)
            i = html.find('<body')
            if i != -1:
                j = html.find('>', i)
                html = html[:j + 1] + str(BANNER) + html[j + 1:]
                resp.set_data(html)
        return resp

    with app.app_context():
        _seed(db, models)
