"""原創雅思寫作題庫（學術組）：載入、圖表繪製與 AI 老師批改。

題庫放在 writing/<測驗代號>/，task1.json 是圖表題（圖表資料直接寫在 JSON 裡，
由這裡畫成 SVG，所以圖表與給 AI 老師看的數據必定一致），task2.json 是論說文。

AI 老師依雅思寫作四項評分標準批改，支援兩家 AI：
- Google Gemini（有免費額度，金鑰 AIza 開頭）
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

BASE = os.path.dirname(os.path.abspath(__file__))
BANK_DIR = os.path.join(BASE, 'writing')
KEY_FILE = os.path.join(BASE, 'ai_key.txt')

SECTION = 'writing'
CLAUDE_MODEL = 'claude-opus-5-5'
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
    path = os.path.join(BANK_DIR, 'tests.json')
    if not os.path.exists(path):
        return []
    with open(path, encoding='utf-8') as f:
        tests = json.load(f)
    return [t for t in tests if _task_files(t['key'])]


def _task_files(key):
    d = os.path.join(BANK_DIR, key)
    out = []
    for n in (1, 2):
        p = os.path.join(d, f'task{n}.json')
        if os.path.exists(p):
            with open(p, encoding='utf-8') as f:
                out.append(json.load(f))
    return out if len(out) == 2 else []


def load_test(key):
    """載入一份寫作測驗；找不到回傳 None。"""
    if not re.fullmatch(r'[A-Za-z0-9_-]+', key or ''):
        return None
    tasks = _task_files(key)
    if not tasks:
        return None
    meta = {}
    meta_path = os.path.join(BANK_DIR, key, 'meta.json')
    if os.path.exists(meta_path):
        with open(meta_path, encoding='utf-8') as f:
            meta = json.load(f)
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

def _key_file():
    if os.path.exists(KEY_FILE):
        with open(KEY_FILE, encoding='utf-8-sig') as f:
            return f.read().strip()
    return ''


def key_provider(key):
    """依金鑰開頭判斷是哪一家的金鑰。"""
    if key.startswith('sk-ant-'):
        return 'claude'
    if key.startswith('AIza'):
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
    return {'gemini': 'Google Gemini（免費額度）', 'claude': 'Anthropic Claude'}.get(provider, '尚未設定')


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
    """用 Claude 批改，回傳 (JSON 文字, 模型名稱)。"""
    import anthropic
    client = anthropic.Anthropic(api_key=key, timeout=300)
    try:
        resp = client.beta.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=16000,
            betas=['server-side-fallback-2026-07-01'],
            fallbacks='default',
            system=SYSTEM_PROMPT,
            output_config={'effort': 'high',
                           'format': {'type': 'json_schema', 'schema': _schema(task['no'])}},
            messages=[{'role': 'user', 'content': _user_message(task, essay)}],
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
        raise RuntimeError('AI 老師無法批改這篇內容。')
    if resp.stop_reason == 'max_tokens':
        raise RuntimeError('AI 回覆太長被截斷，請再按一次批改。')
    return next((b.text for b in resp.content if b.type == 'text'), ''), CLAUDE_MODEL


def gemini_models():
    forced = os.environ.get('GEMINI_MODEL', '').strip()
    return [forced] if forced else list(GEMINI_MODELS)


def _gemini_error(e):
    """把 Gemini 的錯誤換成看得懂的中文。"""
    code = getattr(e, 'code', None)
    msg = str(e)
    if code == 429:
        return 'Gemini 免費額度暫時用完了（每分鐘或每天有次數上限），請過一下再按一次批改。'
    if code in (400, 401, 403) and ('API key' in msg or 'API_KEY' in msg or code in (401, 403)):
        return 'Gemini 金鑰無效或沒有權限，請重新雙擊 set_ai_key.bat 設定正確的金鑰。'
    if code and code >= 500:
        return 'Gemini 伺服器暫時有問題，請稍後再按一次批改。'
    return f'Gemini 回報錯誤（{code}）：{msg[:120]}'


def _ask_gemini(key, task, essay):
    """用 Gemini 批改，回傳 (JSON 文字, 模型名稱)。"""
    from google import genai
    from google.genai import errors, types
    client = genai.Client(api_key=key)
    config = types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT,
        response_mime_type='application/json',
        response_json_schema=_schema(task['no']),
        max_output_tokens=16000,
    )
    last = None
    for model in gemini_models():
        try:
            resp = client.models.generate_content(model=model, contents=_user_message(task, essay), config=config)
        except errors.APIError as e:
            if e.code == 404:          # 這個模型已經下架或不存在，換下一個
                last = e
                continue
            raise RuntimeError(_gemini_error(e))
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
    raise RuntimeError('找不到可用的 Gemini 模型，請通知維護人員更新 GEMINI_MODELS。'
                       + (f'（{last}）' if last else ''))


def grade_task(task, essay):
    """批改一個 Task，回傳 dict（criteria、summary、errors…，再加上 band 與 model）。失敗時丟出 RuntimeError。"""
    if count_words(essay) == 0:
        return _blank_result(task)
    provider, key = ai_config()
    if not key:
        raise RuntimeError('AI 老師還沒設定：請在櫃台電腦雙擊 set_ai_key.bat 輸入 API 金鑰。')
    ask = _ask_gemini if provider == 'gemini' else _ask_claude
    text, model = ask(key, task, essay)
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
