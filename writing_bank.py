"""原創雅思寫作題庫（學術組）：載入、圖表繪製與 AI 老師批改。

題庫放在 writing/<測驗代號>/，task1.json 是圖表題（圖表資料直接寫在 JSON 裡，
由這裡畫成 SVG，所以圖表與給 AI 老師看的數據必定一致），task2.json 是論說文。

AI 老師依雅思寫作四項評分標準批改，支援兩家 AI：
- Google Gemini（有免費額度，金鑰 AIza 開頭；Google 新版金鑰是 AQ. 開頭，也算 Gemini）
- Anthropic Claude（付費，金鑰 sk-ant- 開頭）
金鑰從環境變數 GEMINI_API_KEY／ANTHROPIC_API_KEY 或專案資料夾裡的 ai_key.txt 讀取，
依金鑰開頭自動判斷是哪一家（ai_key.txt 不進 git，在櫃台電腦雙擊 set_ai_key.bat 設定）。
兩家用同一套評分規則與輸出格式；沒有金鑰時作文照樣存檔，只是不批改。
"""
import json
import math
import os
import re
from concurrent.futures import ThreadPoolExecutor

from markupsafe import Markup, escape

import bank_store

BASE = os.path.dirname(os.path.abspath(__file__))
BANK_DIR = os.path.join(BASE, 'writing')
KEY_FILE = os.path.join(BASE, 'ai_key.txt')
# 備用的付費金鑰（set_ai_paid_key.bat 設定，不進 git）：免費的 Gemini 額度用完（429）時自動改用這把
PAID_KEY_FILE = os.path.join(BASE, 'ai_key_paid.txt')
PAID_LOG = os.path.join(BASE, 'instance', 'ai_paid_log.txt')

SECTION = 'writing'
# 2026-11 使用者要求用中階、便宜一點的模型（Sonnet 5.5：每百萬 token 輸入 2、輸出 10 美元，Opus 5.5 的一半）
CLAUDE_MODEL = 'claude-sonnet-5-5'
# 錯題解釋、AI 練習題、單字記憶法這類簡單的短回答用最便宜的 Haiku（價格約 Sonnet 的 1/20）；批改與學習報告維持 Sonnet
CLAUDE_LIGHT_MODEL = 'claude-haiku-5-5'
# Gemini 免費額度可用的模型，依序嘗試（Google 會汰換舊模型，前一個找不到就換下一個）。
# 想指定模型可以設環境變數 GEMINI_MODEL。
GEMINI_MODELS = ['gemini-flash-latest', 'gemini-2.5-flash']

CRITERIA = {
    1: [('ta', 'Task Achievement', '任務達成'),
        ('cc', 'Coherence and Cohesion', '連貫與銜接'),
        ('lr', 'Lexical Resource', '詞彙資源'),
        ('gra', 'Grammatical Range and Accuracy', '文法範圍與正確性')],
    2: [('tr', 'Task Response', '任務回應'),
        ('cc', 'Coherence and Cohesion', '連貫與銜接'),
        ('lr', 'Lexical Resource', '詞彙資源'),
        ('gra', 'Grammatical Range and Accuracy', '文法範圍與正確性')],
}


# ---------------------------------------------------------------- 載入

def list_tests():
    return [t for t in bank_store.tests('writing') if _task_files(t['key'])]


def _task_files(key):
    out = [t for t in (bank_store.read('writing', key, f'task{n}.json') for n in (1, 2)) if t]
    return out if len(out) == 2 else []


def load_test(key):
    """載入一份寫作測驗；找不到回傳 None。"""
    if not re.fullmatch(r'[A-Za-z0-9_-]+', key or '') or bank_store.is_draft('writing', key):
        return None
    tasks = _task_files(key)
    if not tasks:
        return None
    meta = bank_store.read('writing', key, 'meta.json', {})
    for t in tasks:
        t['paragraphs'] = [p for p in t['prompt'].split('\n') if p.strip()]
        if t.get('chart'):
            t['chart_svg'] = chart_svg(t['chart'])
    return {'key': key, 'title': meta.get('title', key), 'module': meta.get('module', 'Academic'),
            'tasks': tasks, 'minutes': sum(t['minutes'] for t in tasks)}


def count_words(text):
    """與考場相同的算法：以空白分隔的字串都算一個字。"""
    return len(re.findall(r'\S+', text or ''))


# ---------------------------------------------------------------- 圖表

PALETTE = ['#1f4e79', '#c0504d', '#4f9a3c', '#8e44ad', '#d68910']
DASHES = ['', '8 5', '2 4', '10 4 2 4', '']
MARKERS = ['circle', 'square', 'triangle', 'circle', 'square']


def _marker(kind, x, y, color):
    if kind == 'square':
        return f'<rect x="{x-4.5}" y="{y-4.5}" width="9" height="9" fill="{color}"/>'
    if kind == 'triangle':
        return f'<polygon points="{x},{y-6} {x-5.5},{y+4.5} {x+5.5},{y+4.5}" fill="{color}"/>'
    return f'<circle cx="{x}" cy="{y}" r="4.5" fill="{color}"/>'


def chart_svg(c):
    """把 JSON 裡的圖表資料畫成考卷風格的黑白線條圖（線圖 line 或長條圖 bar）。"""
    W, H = 640, 400
    L, R, T, B = 70, 20, 50, 90
    pw, ph = W - L - R, H - T - B
    ymax, step = c['y_max'], c['y_step']
    xs = c['x']
    n = len(xs)
    e = lambda s: str(escape(s))
    out = [f'<svg viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg" role="img" '
           f'aria-label="{e(c.get("title", ""))}" class="task-chart" font-family="Arial, sans-serif">',
           f'<rect width="{W}" height="{H}" fill="#fff"/>',
           f'<text x="{W/2}" y="26" text-anchor="middle" font-size="15" font-weight="bold">{e(c.get("title", ""))}</text>']
    # 格線與 Y 軸刻度
    v = 0
    while v <= ymax:
        y = T + ph - ph * v / ymax
        out.append(f'<line x1="{L}" y1="{y:.1f}" x2="{L+pw}" y2="{y:.1f}" stroke="#d9d9d9"/>')
        out.append(f'<text x="{L-8}" y="{y+4:.1f}" text-anchor="end" font-size="12">{v:g}</text>')
        v += step
    out.append(f'<line x1="{L}" y1="{T}" x2="{L}" y2="{T+ph}" stroke="#333"/>')
    out.append(f'<line x1="{L}" y1="{T+ph}" x2="{L+pw}" y2="{T+ph}" stroke="#333"/>')
    out.append(f'<text transform="translate(18,{T+ph/2}) rotate(-90)" text-anchor="middle" font-size="12">{e(c.get("y_label", ""))}</text>')

    series = c['series']
    if c.get('type') == 'bar':
        gw = pw / n
        bw = gw * 0.7 / len(series)
        for i, x in enumerate(xs):
            cx = L + gw * i + gw / 2
            out.append(f'<text x="{cx:.1f}" y="{T+ph+18}" text-anchor="middle" font-size="12">{e(x)}</text>')
            for k, s in enumerate(series):
                val = s['values'][i]
                h = ph * val / ymax
                bx = L + gw * i + gw * 0.15 + bw * k
                out.append(f'<rect x="{bx:.1f}" y="{T+ph-h:.1f}" width="{bw-2:.1f}" height="{h:.1f}" fill="{PALETTE[k % 5]}"/>')
    else:
        gx = pw / (n - 1) if n > 1 else 0
        for i, x in enumerate(xs):
            out.append(f'<text x="{L+gx*i:.1f}" y="{T+ph+18}" text-anchor="middle" font-size="12">{e(x)}</text>')
        for k, s in enumerate(series):
            pts = [(L + gx * i, T + ph - ph * val / ymax) for i, val in enumerate(s['values'])]
            dash = f' stroke-dasharray="{DASHES[k % 5]}"' if DASHES[k % 5] else ''
            out.append(f'<polyline points="{" ".join(f"{x:.1f},{y:.1f}" for x, y in pts)}" fill="none" '
                       f'stroke="{PALETTE[k % 5]}" stroke-width="2.5"{dash}/>')
            out.extend(_marker(MARKERS[k % 5], round(x, 1), round(y, 1), PALETTE[k % 5]) for x, y in pts)
    # 圖例
    lx = L
    ly = H - 30
    for k, s in enumerate(series):
        col = PALETTE[k % 5]
        if c.get('type') == 'bar':
            out.append(f'<rect x="{lx}" y="{ly-7}" width="16" height="12" fill="{col}"/>')
        else:
            dash = f' stroke-dasharray="{DASHES[k % 5]}"' if DASHES[k % 5] else ''
            out.append(f'<line x1="{lx}" y1="{ly}" x2="{lx+30}" y2="{ly}" stroke="{col}" stroke-width="2.5"{dash}/>')
            out.append(_marker(MARKERS[k % 5], lx + 15, ly, col))
        out.append(f'<text x="{lx+38}" y="{ly+4}" font-size="12">{e(s["name"])}</text>')
        lx += 38 + 8 * len(s['name']) + 26
    out.append('</svg>')
    return Markup(''.join(out))


def chart_as_text(c):
    """給 AI 老師看的圖表數據（與畫出來的圖同一份資料）。"""
    lines = [f"Chart type: {c.get('type', 'line')} graph. Title: {c.get('title', '')}",
             f"Y axis: {c.get('y_label', '')}", 'Data:']
    lines.append('Series | ' + ' | '.join(c['x']))
    for s in c['series']:
        lines.append(f"{s['name']} | " + ' | '.join(f'{v:g}' for v in s['values']))
    return '\n'.join(lines)


# ---------------------------------------------------------------- 分數換算

def round_band(x):
    """雅思的分數進位：小數 .25 以上進到 .5，.75 以上進到下一個整數，其餘捨去。"""
    whole = math.floor(x)
    frac = x - whole
    if frac >= 0.75:
        return whole + 1.0
    if frac >= 0.25:
        return whole + 0.5
    return float(whole)


def task_band(result):
    """單一 Task 的分數：四項標準平均後依雅思規則進位。"""
    bands = [c['band'] for c in result['criteria'].values()]
    return round_band(sum(bands) / len(bands))


def overall_band(t1, t2):
    """寫作總分：Task 2 佔兩倍權重。官方不公布確切算法，這是常用的近似值。"""
    return round_band((t1 + 2 * t2) / 3)


# ---------------------------------------------------------------- AI 老師

def _key_file(path=None):
    path = path or KEY_FILE
    if os.path.exists(path):
        with open(path, encoding='utf-8-sig') as f:
            return f.read().strip()
    return ''


class FreeQuotaError(RuntimeError):
    """Gemini 回 429：免費額度（每分鐘或每天的次數）用完了。有備用付費金鑰時會自動改用付費的。"""


def key_provider(key):
    """依金鑰開頭判斷是哪一家的金鑰。"""
    if key.startswith('sk-ant-'):
        return 'claude'
    # Google AI Studio 從 2026 年起有些帳號產生的是新格式 AQ. 開頭的金鑰，一樣是 Gemini
    if key.startswith('AIza') or key.startswith('AQ.'):
        return 'gemini'
    return None


def ai_config():
    """回傳 (哪一家, 金鑰)。ai_key.txt 優先，其次是環境變數；都沒有時回傳 (None, '')。"""
    key = _key_file()
    if key and key_provider(key):
        return key_provider(key), key
    for env, provider in (('GEMINI_API_KEY', 'gemini'), ('ANTHROPIC_API_KEY', 'claude')):
        key = os.environ.get(env, '').strip()
        if key:
            return provider, key
    return None, ''


def paid_config():
    """備用付費金鑰：回傳 (哪一家, 金鑰)，沒有設定時回傳 (None, '')。
    讀 ai_key_paid.txt，其次是環境變數 AI_PAID_KEY；和主要金鑰一樣依開頭判斷是 Gemini（付費專案）還是 Claude。"""
    key = _key_file(PAID_KEY_FILE) or os.environ.get('AI_PAID_KEY', '').strip()
    provider = key_provider(key) if key else None
    if not provider or key == ai_config()[1]:
        return None, ''
    return provider, key


def _log_paid(model, what):
    """記下每一次改用付費金鑰（instance/ai_paid_log.txt），之後對帳單用。"""
    from datetime import datetime
    try:
        os.makedirs(os.path.dirname(PAID_LOG), exist_ok=True)
        with open(PAID_LOG, 'a', encoding='utf-8') as f:
            f.write(f"{datetime.now():%Y-%m-%d %H:%M}\t{model}\t{what}\n")
    except OSError:
        pass


def run_ai(run, what=''):
    """用主要金鑰呼叫 run(哪一家, 金鑰)；免費額度用完（FreeQuotaError）而且有備用付費金鑰時，改用付費金鑰再呼叫一次。
    run 的回傳值要是 (結果, 模型名稱)。"""
    provider, key = ai_config()
    if not key:
        raise RuntimeError('AI 老師還沒設定：請在櫃台電腦雙擊 set_ai_key.bat 輸入 API 金鑰。')
    try:
        return run(provider, key)
    except FreeQuotaError:
        paid, paid_key = paid_config()
        if not paid_key:
            raise
    result = run(paid, paid_key)
    _log_paid(result[1] if isinstance(result, tuple) and len(result) > 1 else '', what)
    return result


def api_key():
    return ai_config()[1]


def ai_ready():
    provider, key = ai_config()
    if not key:
        return False
    try:
        if provider == 'gemini':
            from google import genai  # noqa: F401
        else:
            import anthropic  # noqa: F401
    except ImportError:
        return False
    return True


def ai_label():
    """顯示用：目前是哪一位 AI 老師。"""
    provider = ai_config()[0]
    label = {'gemini': 'Google Gemini（免費額度）', 'claude': 'Anthropic Claude'}.get(provider, '尚未設定')
    paid = paid_config()[0]
    if provider and paid:
        label += '，額度用完改用' + {'gemini': ' Gemini 付費版', 'claude': ' Claude'}[paid]
    return label


SYSTEM_PROMPT = """You are a senior, certified IELTS Writing examiner acting as a strict teacher at a Taiwanese cram school. You mark one Academic Writing task at a time against the four official public band descriptors.

Marking principles — be rigorous, never generous:
- Mark only what is on the page. Do not reward intentions, ideas the candidate "probably meant", or length for its own sake.
- Each criterion receives a WHOLE band from 0 to 9. A band is awarded only when the script fully meets that band's descriptor; if it falls between two bands, award the LOWER one.
- Under-length: Task 1 under 150 words or Task 2 under 250 words must be penalised in Task Achievement / Task Response. Very short scripts (Task 1 under 50 words, Task 2 under 100 words) cannot score above 3 on that criterion.
- Memorised or off-topic text earns no credit; a script that is wholly off-topic or memorised is capped at band 2 overall for that criterion. Copied wording from the question does not count towards range of vocabulary.
- Task 1 (Academic): no clear overview of the main trends/features caps Task Achievement at 5. Inaccurate data, missing key features, or giving opinions/reasons not shown in the visual must be penalised. Mechanical listing of every number without comparison cannot exceed 5.
- Task 2: a position that is unclear or inconsistent caps Task Response at 5; ideas that are underdeveloped, unsupported or overgeneralised cannot exceed 6. Both parts of a multi-part question must be addressed.
- Coherence and Cohesion: paragraphing, clear progression, referencing and substitution; overuse or mechanical use of linking words ("Firstly, Secondly, In addition, Moreover" at every sentence start) cannot exceed 6.
- Lexical Resource: precision, collocation and range; repeated spelling or word-formation errors and inappropriate register lower the band. Band 7+ needs less common items used with awareness of style and collocation.
- Grammatical Range and Accuracy: band 7 needs frequent error-free sentences and a variety of complex structures; band 6 is a mix of simple and complex forms with some errors; frequent errors that impede communication are band 5 or below. Punctuation errors count.
- Do not inflate scores to encourage the student. Your job is an honest estimate; encouragement belongs in the comments, not in the band.

Write all comments for a Taiwanese student in Traditional Chinese (繁體中文, Taiwan usage). Quote the student's original English exactly when pointing to evidence. Corrections and suggested rewrites must be in English.
"""

CRIT_SCHEMA = {
    'type': 'object',
    'properties': {
        'band': {'type': 'integer', 'description': '整數 Band，0 到 9'},
        'reason': {'type': 'string', 'description': '為什麼是這個分數、為什麼不是高一級（繁體中文，引用原文為證）'},
        'strengths': {'type': 'array', 'items': {'type': 'string'}},
        'weaknesses': {'type': 'array', 'items': {'type': 'string'}},
    },
    'required': ['band', 'reason', 'strengths', 'weaknesses'],
    'additionalProperties': False,
}


def _schema(task_no):
    keys = [k for k, _, _ in CRITERIA[task_no]]
    return {
        'type': 'object',
        'properties': {
            'criteria': {
                'type': 'object',
                'properties': {k: CRIT_SCHEMA for k in keys},
                'required': keys,
                'additionalProperties': False,
            },
            'summary': {'type': 'string', 'description': '整體評語，3–5 句，繁體中文'},
            'errors': {
                'type': 'array',
                'description': '最重要的語言錯誤，最多 10 個',
                'items': {
                    'type': 'object',
                    'properties': {
                        'original': {'type': 'string'},
                        'correction': {'type': 'string'},
                        'explain': {'type': 'string'},
                    },
                    'required': ['original', 'correction', 'explain'],
                    'additionalProperties': False,
                },
            },
            'next_steps': {'type': 'array', 'items': {'type': 'string'},
                           'description': '要升一級最該先改的 3 件事，繁體中文'},
            'model_paragraph': {'type': 'string',
                                'description': '把學生表現最弱的一段改寫成 Band 7 水準的英文示範（Task 1 優先示範 overview）'},
        },
        'required': ['criteria', 'summary', 'errors', 'next_steps', 'model_paragraph'],
        'additionalProperties': False,
    }


def _user_message(task, essay):
    n = task['no']
    parts = [f"IELTS Academic Writing Task {n}. Recommended time {task['minutes']} minutes. "
             f"Minimum {task['min_words']} words.",
             '', 'QUESTION:', task['prompt'], task.get('instruction', '')]
    if task.get('chart'):
        parts += ['', 'THE VISUAL (exact data the candidate saw):', chart_as_text(task['chart'])]
    parts += ['', f'CANDIDATE SCRIPT ({count_words(essay)} words):', '"""', essay.strip() or '(blank)', '"""',
              '', f"Mark this Task {n} script strictly on the four criteria: "
              + ', '.join(name for _, name, _ in CRITERIA[n]) + '.']
    return '\n'.join(parts)


def _blank_result(task):
    keys = [k for k, _, _ in CRITERIA[task['no']]]
    return {'criteria': {k: {'band': 0, 'reason': '沒有作答。', 'strengths': [], 'weaknesses': []} for k in keys},
            'summary': '這個 Task 沒有作答，正式考試會是 0 分。', 'errors': [], 'next_steps': [],
            'model_paragraph': '', 'band': 0.0}


def _ask_claude(key, task, essay):
    """用 Claude 批改雅思寫作，回傳 (JSON 文字, 模型名稱)。"""
    return _claude_json(key, SYSTEM_PROMPT, _user_message(task, essay), _schema(task['no']))


def _claude_json(key, system, message, schema, effort='high', model=None):
    """用 Claude 依評分規則 system 批改 message，照 schema 回 JSON，回傳 (JSON 文字, 模型名稱)。
    雅思寫作與韓檢寫作（topik_mock.py）共用；AI 學習教練（ai_tutor.py）用較低的 effort，回得比較快。"""
    import anthropic
    model = model or CLAUDE_MODEL
    client = anthropic.Anthropic(api_key=key, timeout=300)
    kwargs = dict(model=model, max_tokens=16000, system=system,
                  output_config={'effort': effort, 'format': {'type': 'json_schema', 'schema': schema}},
                  messages=[{'role': 'user', 'content': message}])
    try:
        if model == CLAUDE_LIGHT_MODEL:     # Haiku 沒有伺服器端的拒答備援（fallbacks），用一般的呼叫
            resp = client.messages.create(**kwargs)
        else:
            resp = client.beta.messages.create(betas=['server-side-fallback-2026-07-01'], fallbacks='default',
                                               **kwargs)
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
        raise RuntimeError('AI 老師無法批改這篇內容。')
    if resp.stop_reason == 'max_tokens':
        raise RuntimeError('AI 回覆太長被截斷，請再按一次批改。')
    return next((b.text for b in resp.content if b.type == 'text'), ''), model


def gemini_client(key):
    """建立 Gemini 連線。一定要指定 v1beta：google-genai 套件新版把預設改成 v1，
    但 v1 不接受評分規則（system_instruction），會回「Developer instruction is not enabled for api version v1」，
    寫作和口說的 AI 批改就全部失敗（run.bat 每次都會更新套件，所以櫃台電腦會自動升到新版）。"""
    from google import genai
    from google.genai import types
    return genai.Client(api_key=key, http_options=types.HttpOptions(api_version='v1beta'))


def gemini_models():
    forced = os.environ.get('GEMINI_MODEL', '').strip()
    return [forced] if forced else list(GEMINI_MODELS)


def _gemini_error(e):
    """把 Gemini 的錯誤換成看得懂的中文。"""
    code = getattr(e, 'code', None)
    msg = str(e)
    if code == 401 and 'ACCESS_TOKEN_TYPE_UNSUPPORTED' in msg:
        return ('Google 不接受這把 AQ. 開頭的新格式金鑰（ACCESS_TOKEN_TYPE_UNSUPPORTED）。'
                '請到 Google AI Studio 重新建立一把 AIza 開頭的金鑰，再雙擊 set_ai_key.bat 設定。')
    if code == 429:
        return 'Gemini 免費額度暫時用完了（每分鐘或每天有次數上限），請過一下再按一次批改。'
    if code in (400, 401, 403) and ('API key' in msg or 'API_KEY' in msg or code in (401, 403)):
        return 'Gemini 金鑰無效或沒有權限，請重新雙擊 set_ai_key.bat 設定正確的金鑰。'
    if code and code >= 500:
        return 'Gemini 伺服器暫時有問題，請稍後再按一次批改。'
    return f'Gemini 回報錯誤（{code}）：{msg[:120]}'


def gemini_exc(e):
    """Gemini 的錯誤換成要丟出的例外：429（免費額度用完）是 FreeQuotaError，可以改用付費金鑰；其他是 RuntimeError。"""
    cls = FreeQuotaError if getattr(e, 'code', None) == 429 else RuntimeError
    return cls(_gemini_error(e))


def _try_next_model(e):
    """這個錯誤換一個模型可能就好：404 是模型下架或不存在；500 以上是那個模型暫時故障或太忙
    （gemini-flash-latest 尖峰時段常回 503「high demand」，同一時間 gemini-2.5-flash 是正常的）。"""
    code = getattr(e, 'code', None) or 0
    return code == 404 or code >= 500


def _no_model_error(last):
    """每個模型都試過還是不行時的訊息。"""
    if last is not None and (getattr(last, 'code', None) or 0) >= 500:
        return _gemini_error(last)     # 全部都在忙：請學生稍後再按一次
    return '找不到可用的 Gemini 模型，請通知維護人員更新 GEMINI_MODELS。' + (f'（{last}）' if last else '')


def _ask_gemini(key, task, essay):
    """用 Gemini 批改雅思寫作，回傳 (JSON 文字, 模型名稱)。"""
    return _gemini_json(key, SYSTEM_PROMPT, _user_message(task, essay), _schema(task['no']))


def _gemini_json(key, system, message, schema, effort=None):
    """用 Gemini 依評分規則 system 批改 message，照 schema 回 JSON，回傳 (JSON 文字, 模型名稱)。"""
    from google import genai
    from google.genai import errors, types
    client = gemini_client(key)
    config = types.GenerateContentConfig(
        system_instruction=system,
        response_mime_type='application/json',
        response_json_schema=schema,
        max_output_tokens=16000,
    )
    last = None
    for model in gemini_models():
        try:
            resp = client.models.generate_content(model=model, contents=message, config=config)
        except errors.APIError as e:
            if _try_next_model(e):     # 這個模型下架了或暫時太忙，換下一個
                last = e
                continue
            raise gemini_exc(e)
        except Exception as e:      # 網路斷線等
            raise RuntimeError(f'連不上 Gemini，請確認這台電腦有網路。（{type(e).__name__}）')
        text = resp.text or ''
        if not text:
            reason = ''
            if resp.candidates:
                reason = str(resp.candidates[0].finish_reason or '')
            if 'MAX_TOKENS' in reason:
                raise RuntimeError('AI 回覆太長被截斷，請再按一次批改。')
            raise RuntimeError('Gemini 沒有回覆批改內容（可能被安全機制擋下），請再按一次批改。')
        return text, model
    raise RuntimeError(_no_model_error(last))


def ask_json(system, message, schema, effort='high', light=False):
    """依目前設定的 AI 老師（Gemini 或 Claude）批改，回傳 (解析好的 dict, 模型名稱)。失敗丟 RuntimeError。
    effort 只對 Claude 有用（Gemini 沒有這個設定）：批改作文用 high，解釋錯題這類短回答用 low。"""
    def run(provider, key):
        if provider == 'gemini':
            return _gemini_json(key, system, message, schema, effort=effort)
        return _claude_json(key, system, message, schema, effort=effort,
                            model=CLAUDE_LIGHT_MODEL if light else CLAUDE_MODEL)
    text, model = run_ai(run, 'AI 學習教練／韓檢寫作')
    try:
        return json.loads(text), model
    except ValueError:
        raise RuntimeError('AI 回覆的格式不正確，請再按一次批改。')


def grade_task(task, essay):
    """批改一個 Task，回傳 dict（criteria、summary、errors…，再加上 band 與 model）。失敗時丟出 RuntimeError。"""
    if count_words(essay) == 0:
        return _blank_result(task)
    def run(provider, key):
        ask = _ask_gemini if provider == 'gemini' else _ask_claude
        return ask(key, task, essay)
    text, model = run_ai(run, f"雅思寫作 Task {task['no']}")
    try:
        data = json.loads(text)
        crit = data['criteria']
        for k, _, _ in CRITERIA[task['no']]:      # 保險：四項都要有、分數一定是 0–9 的整數
            crit[k]['band'] = max(0, min(9, int(crit[k]['band'])))
    except (ValueError, KeyError, TypeError):
        raise RuntimeError('AI 回覆的格式不正確，請再按一次批改。')
    for k in ('summary', 'model_paragraph'):
        data.setdefault(k, '')
    for k in ('errors', 'next_steps'):
        data.setdefault(k, [])
    data['band'] = task_band(data)
    data['model'] = model
    return data


def grade_all(test, essays):
    """兩個 Task 同時批改。回傳 {'tasks': {1: ..., 2: ...}, 'overall': 6.5, 'model': ...}"""
    tasks = {t['no']: t for t in test['tasks']}
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = {n: pool.submit(grade_task, tasks[n], essays.get(n, '')) for n in (1, 2)}
        results = {n: f.result() for n, f in futures.items()}
    return {'tasks': {str(n): r for n, r in results.items()},
            'overall': overall_band(results[1]['band'], results[2]['band']),
            'model': results[2].get('model') or results[1].get('model', '')}
