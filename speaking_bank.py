"""原創雅思口說題庫：載入、考官台詞與 AI 老師批改。

題庫放在 speaking/<測驗代號>/test.json，格式比照正式口說考試（約 11–14 分鐘）：
- Part 1 訪談：考官先確認姓名，接著 3 個日常話題，每個 3–4 題
- Part 2 題卡：1 分鐘準備（可做筆記）、說 1–2 分鐘，2 分鐘一到考官就喊停，最後 1 個收尾問題
- Part 3 討論：延伸 Part 2 主題的 2 個抽象議題，每個 3 題

AI 老師沿用寫作區的設定（writing_bank.ai_config）：
- Google Gemini：直接「聽」錄音檔，自己做語音辨識（逐字稿）後評分，發音也是真的聽過才給分
- Anthropic Claude：Claude 不能直接聽音檔，所以改用瀏覽器（Edge）的語音辨識產生逐字稿再評分；
  發音只能從辨識結果推估，頁面會註明
兩家都依官方四項標準評分：Fluency and Coherence、Lexical Resource、
Grammatical Range and Accuracy、Pronunciation。總分在 Python 端計算。
"""
import json
import os
import re

import writing_bank
from writing_bank import ai_config, ai_ready, ai_label, round_band, gemini_models, _gemini_error

BASE = os.path.dirname(os.path.abspath(__file__))
BANK_DIR = os.path.join(BASE, 'speaking')
AUDIO_DIR = os.path.join(BASE, 'instance', 'speaking_audio')

CRITERIA = [('fc', 'Fluency and Coherence', '流暢度與連貫性'),
            ('lr', 'Lexical Resource', '詞彙資源'),
            ('gra', 'Grammatical Range and Accuracy', '文法範圍與正確性'),
            ('p', 'Pronunciation', '發音')]

# 每題作答的上限秒數（到了會自動停止錄音並進下一題，比照考官打斷）
LIMITS = {'id': 25, 'p1': 45, 'p2': 120, 'p2f': 40, 'p3': 90}
PREP_SECONDS = 60
AUDIO_TYPES = {'audio/webm': 'webm', 'audio/ogg': 'ogg', 'audio/mp4': 'm4a', 'audio/mpeg': 'mp3',
               'audio/wav': 'wav', 'audio/aac': 'aac', 'audio/x-m4a': 'm4a'}
INLINE_LIMIT = 14 * 1024 * 1024     # Gemini 單次請求上限 20MB（含 base64 膨脹），超過就改走上傳


# ---------------------------------------------------------------- 載入

def list_tests():
    path = os.path.join(BANK_DIR, 'tests.json')
    if not os.path.exists(path):
        return []
    with open(path, encoding='utf-8') as f:
        tests = json.load(f)
    return [t for t in tests if os.path.exists(os.path.join(BANK_DIR, t['key'], 'test.json'))]


def load_test(key):
    """載入一份口說測驗，並展開成考官逐句的流程 steps；找不到回傳 None。"""
    if not re.fullmatch(r'[A-Za-z0-9_-]+', key or ''):
        return None
    path = os.path.join(BANK_DIR, key, 'test.json')
    if not os.path.exists(path):
        return None
    with open(path, encoding='utf-8') as f:
        t = json.load(f)
    t['key'] = key
    t['steps'] = build_steps(t)
    t['questions'] = {s['qid']: s for s in t['steps'] if s.get('qid')}
    return t


def build_steps(t):
    """把題庫展開成考官的台詞順序。每一步：考官說 say；有 qid 的步驟要錄音作答。"""
    steps = [{'qid': 'p1-0', 'part': 1, 'kind': 'id', 'topic': 'Introduction',
              'say': "Good morning. This is a practice IELTS Speaking test. "
                     "Can you tell me your full name, please?",
              'text': 'Can you tell me your full name, please?', 'limit': LIMITS['id']}]
    n = 0
    for i, topic in enumerate(t['part1']):
        for j, q in enumerate(topic['questions']):
            n += 1
            say = q
            if j == 0:
                lead = ("Thank you. Now, in this first part of the test, I'd like to ask you some questions "
                        "about yourself. Let's talk about " if i == 0 else "Now let's move on to talk about ")
                say = f"{lead}{topic['topic'].lower()}. {q}"
            steps.append({'qid': f'p1-{n}', 'part': 1, 'kind': 'p1', 'topic': topic['topic'],
                          'say': say, 'text': q, 'limit': LIMITS['p1']})
    c = t['part2']
    steps.append({'part': 2, 'kind': 'card', 'topic': c['topic'],
                  'say': "Thank you. Now I'm going to give you a topic, and I'd like you to talk about it for one to "
                         "two minutes. Before you talk, you'll have one minute to think about what you're going to say. "
                         "You can make some notes if you wish. Here is your topic. " + c['cue'],
                  'prep': PREP_SECONDS})
    steps.append({'qid': 'p2', 'part': 2, 'kind': 'p2', 'topic': c['topic'],
                  'say': "All right? Remember, you have one to two minutes for this, so don't worry if I stop you. "
                         "I'll tell you when the time is up. Can you start speaking now, please?",
                  'text': c['cue'], 'card': c, 'limit': LIMITS['p2']})
    for k, q in enumerate(c.get('followups', []), 1):
        steps.append({'qid': f'p2f-{k}', 'part': 2, 'kind': 'p2f', 'topic': c['topic'],
                      'say': ("Thank you. " if k == 1 else '') + q, 'text': q, 'limit': LIMITS['p2f']})
    n = 0
    for i, theme in enumerate(t['part3']):
        for j, q in enumerate(theme['questions']):
            n += 1
            say = q
            if j == 0:
                lead = (f"Thank you. We've been talking about {c['topic'].lower()}, and I'd like to discuss with you "
                        f"one or two more general questions related to this. Let's consider first of all "
                        if i == 0 else "Now let's talk about ")
                say = f"{lead}{theme['theme'].lower()}. {q}"
            steps.append({'qid': f'p3-{n}', 'part': 3, 'kind': 'p3', 'topic': theme['theme'],
                          'say': say, 'text': q, 'limit': LIMITS['p3']})
    steps.append({'part': 3, 'kind': 'end', 'say': 'Thank you. That is the end of the speaking test.'})
    return steps


# ---------------------------------------------------------------- 錄音檔

def audio_ext(mime):
    base = (mime or '').split(';')[0].strip().lower()
    return AUDIO_TYPES.get(base)


def audio_mime(filename):
    ext = filename.rsplit('.', 1)[-1].lower()
    for mime, e in AUDIO_TYPES.items():
        if e == ext:
            return mime
    return 'application/octet-stream'


def sub_dir(sub_id):
    return os.path.join(AUDIO_DIR, str(int(sub_id)))


def overall_band(result):
    """口說總分：四項平均後依雅思規則進位。"""
    bands = [result['criteria'][k]['band'] for k, _, _ in CRITERIA]
    return round_band(sum(bands) / len(bands))


# ---------------------------------------------------------------- AI 老師

SYSTEM_PROMPT = """You are a senior, certified IELTS Speaking examiner acting as a strict teacher at a Taiwanese cram school. You assess one complete practice Speaking test (Part 1 interview, Part 2 long turn, Part 3 discussion) against the four official public band descriptors: Fluency and Coherence, Lexical Resource, Grammatical Range and Accuracy, Pronunciation.

Assessment principles — be rigorous, never generous:
- Assess only what the candidate actually said. Do not reward what they "probably meant".
- Each criterion receives a WHOLE band from 0 to 9. A band is awarded only when the performance fully meets that band's descriptor across the whole test; if it falls between two bands, award the LOWER one.
- The name question at the start (p1-0) is an identity check only; do not assess it.
- Fluency and Coherence: frequent long pauses, self-correction, repetition or slow speech lowers the band; band 7 needs speech at length without noticeable effort; overuse of fillers ("um", "you know", "like") and mechanical connectors ("firstly, secondly") cannot exceed 6. Part 1 answers that are only one word or one short sentence, and a Part 2 talk that stops well before one minute (check the stated duration), must be penalised; a Part 2 talk under 30 seconds cannot exceed 5 for fluency.
- Lexical Resource: range, precision, collocation, idiomatic language and paraphrase. Repeating words from the question does not show range. Band 7+ needs less common and idiomatic items used with awareness of style.
- Grammatical Range and Accuracy: band 7 needs a range of complex structures with frequent error-free sentences; band 6 mixes simple and complex forms with errors that rarely impede communication; frequent basic errors (tense, agreement, articles, plurals) mean band 5 or below.
- Pronunciation: intelligibility, individual sounds, word stress, sentence stress, intonation, connected speech, and how much L1 accent (Mandarin) strains the listener. Band 7+ needs sustained flexible use of features with only occasional lapses.
- Answers that sound memorised or off-topic earn little credit. Silence or no answer counts against fluency and against the amount of language available for the other criteria.
- Do not inflate scores to encourage the student. Encouragement belongs in the comments, not in the band.

Write all comments for a Taiwanese student in Traditional Chinese (繁體中文, Taiwan usage). Quote the student's own English words exactly as evidence. Corrections and model answers must be in English.
"""

CRIT_SCHEMA = writing_bank.CRIT_SCHEMA


def _schema(with_transcripts):
    keys = [k for k, _, _ in CRITERIA]
    props = {
        'criteria': {'type': 'object', 'properties': {k: CRIT_SCHEMA for k in keys},
                     'required': keys, 'additionalProperties': False},
        'summary': {'type': 'string', 'description': '整體評語，3–5 句，繁體中文'},
        'errors': {
            'type': 'array', 'description': '最重要的文法與用字錯誤，最多 10 個',
            'items': {'type': 'object',
                      'properties': {'original': {'type': 'string'}, 'correction': {'type': 'string'},
                                     'explain': {'type': 'string'}},
                      'required': ['original', 'correction', 'explain'], 'additionalProperties': False},
        },
        'pronunciation': {
            'type': 'array', 'description': '最需要改的發音問題，最多 8 個（字或片語、問題、怎麼練）',
            'items': {'type': 'object',
                      'properties': {'item': {'type': 'string'}, 'issue': {'type': 'string'},
                                     'tip': {'type': 'string'}},
                      'required': ['item', 'issue', 'tip'], 'additionalProperties': False},
        },
        'next_steps': {'type': 'array', 'items': {'type': 'string'}, 'description': '要升一級最該先改的 3 件事，繁體中文'},
        'model_answer': {
            'type': 'object', 'description': '挑學生表現最弱的一題（Part 2 或 Part 3 優先），示範 Band 7 水準的英文回答',
            'properties': {'qid': {'type': 'string'}, 'text': {'type': 'string'}},
            'required': ['qid', 'text'], 'additionalProperties': False,
        },
    }
    required = ['criteria', 'summary', 'errors', 'pronunciation', 'next_steps', 'model_answer']
    if with_transcripts:
        props = {'transcripts': {
            'type': 'array', 'description': '每一段錄音的逐字稿，照實記下考生說的話',
            'items': {'type': 'object', 'properties': {'qid': {'type': 'string'}, 'text': {'type': 'string'}},
                      'required': ['qid', 'text'], 'additionalProperties': False}}, **props}
        required = ['transcripts'] + required
    return {'type': 'object', 'properties': props, 'required': required, 'additionalProperties': False}


def _question_line(q, ans):
    line = f"[{q['qid']}] Part {q['part']}"
    if q['kind'] == 'p2':
        line += f" long turn. Cue card: {q['text']}"
        card = q.get('card') or {}
        if card.get('points'):
            line += ' You should say: ' + '; '.join(card['points']) + '; ' + card.get('final', '')
    else:
        line += f" ({q['topic']}). Examiner: {q['text']}"
    line += f"\nAnswer duration: {ans.get('seconds', 0)} seconds."
    return line


def _blank_answers(answers):
    return all(not a.get('file') and not (a.get('transcript') or '').strip() for a in answers)


def _ask_gemini(key, test, answers):
    from google import genai
    from google.genai import errors, types
    client = genai.Client(api_key=key)
    total = sum(os.path.getsize(a['path']) for a in answers if a.get('path'))
    contents = [types.Part.from_text(text=(
        f"IELTS Speaking practice test: {test['title']}. Below is each examiner question followed by the candidate's "
        "recorded answer. First transcribe every recording verbatim (keep hesitations such as 'um', 'uh', false starts "
        "and repetitions; write (...) for a pause longer than about 2 seconds; write (no answer) if the recording is "
        "silent). Then assess the whole test strictly on the four criteria, listening carefully to pronunciation."))]
    for a in answers:
        q = test['questions'][a['qid']]
        contents.append(types.Part.from_text(text=_question_line(q, a)))
        if not a.get('path'):
            contents.append(types.Part.from_text(text='(no recording — the candidate did not answer)'))
            continue
        mime = audio_mime(a['path'])
        try:
            if total > INLINE_LIMIT:
                f = client.files.upload(file=a['path'], config={'mime_type': mime})
                contents.append(types.Part.from_uri(file_uri=f.uri, mime_type=mime))
            else:
                with open(a['path'], 'rb') as fh:
                    contents.append(types.Part.from_bytes(data=fh.read(), mime_type=mime))
        except errors.APIError as e:
            raise RuntimeError(_gemini_error(e))
        except Exception as e:
            raise RuntimeError(f'上傳錄音到 Gemini 失敗，請確認這台電腦有網路。（{type(e).__name__}）')
    contents.append(types.Part.from_text(text='Now give the transcripts and your assessment in the required JSON format.'))
    config = types.GenerateContentConfig(system_instruction=SYSTEM_PROMPT, response_mime_type='application/json',
                                         response_json_schema=_schema(True), max_output_tokens=24000)
    last = None
    for model in gemini_models():
        try:
            resp = client.models.generate_content(model=model, contents=contents, config=config)
        except errors.APIError as e:
            if e.code == 404:
                last = e
                continue
            if e.code == 400 and 'mime' in str(e).lower():
                raise RuntimeError('Gemini 不接受這個瀏覽器的錄音格式，請改用 Edge 或 Chrome 重新錄一次。')
            raise RuntimeError(_gemini_error(e))
        except Exception as e:
            raise RuntimeError(f'連不上 Gemini，請確認這台電腦有網路。（{type(e).__name__}）')
        text = resp.text or ''
        if not text:
            reason = str(resp.candidates[0].finish_reason or '') if resp.candidates else ''
            if 'MAX_TOKENS' in reason:
                raise RuntimeError('AI 回覆太長被截斷，請再按一次批改。')
            raise RuntimeError('Gemini 沒有回覆批改內容（可能被安全機制擋下），請再按一次批改。')
        return text, model
    raise RuntimeError('找不到可用的 Gemini 模型，請通知維護人員更新 GEMINI_MODELS。' + (f'（{last}）' if last else ''))


def _ask_claude(key, test, answers):
    import anthropic
    lines = [f"IELTS Speaking practice test: {test['title']}.",
             "Claude cannot hear audio, so each answer below is a transcript produced by the browser's automatic "
             "speech recognition (no punctuation, and recognition errors are possible). Judge Pronunciation "
             "cautiously from evidence such as words the recogniser clearly misheard; say in the reason that this "
             "band is an estimate from the transcript only.", '']
    for a in answers:
        q = test['questions'][a['qid']]
        lines += [_question_line(q, a), 'Candidate (speech-recognition transcript):',
                  '"""', (a.get('transcript') or '').strip() or '(no answer)', '"""', '']
    lines.append('Assess the whole test strictly on the four criteria.')
    client = anthropic.Anthropic(api_key=key, timeout=300)
    try:
        resp = client.beta.messages.create(
            model=writing_bank.CLAUDE_MODEL, max_tokens=16000,
            betas=['server-side-fallback-2026-07-01'], fallbacks='default',
            system=SYSTEM_PROMPT,
            output_config={'effort': 'high', 'format': {'type': 'json_schema', 'schema': _schema(False)}},
            messages=[{'role': 'user', 'content': '\n'.join(lines)}],
        )
    except anthropic.AuthenticationError:
        raise RuntimeError('API 金鑰無效，請重新雙擊 set_ai_key.bat 設定正確的金鑰。')
    except anthropic.PermissionDeniedError:
        raise RuntimeError('這把金鑰沒有使用權限（可能帳戶尚未儲值）。')
    except anthropic.RateLimitError:
        raise RuntimeError('AI 老師現在太忙（請求次數超過上限），請過一分鐘再按一次批改。')
    except anthropic.APIConnectionError:
        raise RuntimeError('連不上 AI 服務，請確認這台電腦有網路。')
    except anthropic.APIStatusError as e:
        raise RuntimeError(f'AI 服務回報錯誤（{e.status_code}），請稍後再試。')
    if resp.stop_reason == 'refusal':
        raise RuntimeError('AI 老師無法批改這次的內容。')
    if resp.stop_reason == 'max_tokens':
        raise RuntimeError('AI 回覆太長被截斷，請再按一次批改。')
    return next((b.text for b in resp.content if b.type == 'text'), ''), writing_bank.CLAUDE_MODEL


def grade(test, answers):
    """批改一次口說測驗。answers：[{qid, seconds, path?, transcript?}]。
    回傳 dict（criteria、summary…，再加上 transcripts、overall、model、provider）。失敗丟 RuntimeError。"""
    provider, key = ai_config()
    if not key:
        raise RuntimeError('AI 老師還沒設定：請在櫃台電腦雙擊 set_ai_key.bat 輸入 API 金鑰。')
    if _blank_answers(answers):
        raise RuntimeError('這次沒有任何錄音或辨識到的內容，無法批改。請確認麥克風有收到聲音後再考一次。')
    if provider == 'claude' and not any((a.get('transcript') or '').strip() for a in answers):
        raise RuntimeError('目前的 AI 老師是 Claude，它聽不到錄音，需要瀏覽器的語音辨識逐字稿；'
                           '這次沒有辨識到文字。請改用 Edge 重新考一次，或改設定 Gemini 金鑰（可以直接聽錄音）。')
    ask = _ask_gemini if provider == 'gemini' else _ask_claude
    text, model = ask(key, test, answers)
    try:
        data = json.loads(text)
        for k, _, _ in CRITERIA:
            data['criteria'][k]['band'] = max(0, min(9, int(data['criteria'][k]['band'])))
    except (ValueError, KeyError, TypeError):
        raise RuntimeError('AI 回覆的格式不正確，請再按一次批改。')
    for k in ('errors', 'pronunciation', 'next_steps'):
        data.setdefault(k, [])
    data.setdefault('summary', '')
    data.setdefault('model_answer', {'qid': '', 'text': ''})
    if provider == 'gemini':
        data['transcripts'] = {t['qid']: t['text'] for t in data.get('transcripts', []) if isinstance(t, dict)}
    else:
        data['transcripts'] = {a['qid']: a.get('transcript', '') for a in answers}
    data['transcript_source'] = 'gemini' if provider == 'gemini' else 'browser'
    data['overall'] = overall_band(data)
    data['model'] = model
    data['provider'] = provider
    return data
