"""趨勢補習班的公開官網（給 Google 搜尋得到的那一面）。

- 首頁 /、課程 /courses/<考試>、校區 /campus/<校區>、免費諮詢表單 /contact、迷你模考入口 /mock-test、個資說明 /privacy
- SEO：每頁的 title／description／canonical／Open Graph、JSON-LD 結構化資料、/sitemap.xml、/robots.txt
  學生的測驗系統（/dashboard、/learn…）一律加 X-Robots-Tag: noindex，不讓 Google 收錄學生頁面
- 補習班資料（電話、地址、LINE…）在 public_site/site_info.json，空白的欄位網頁顯示「待填」，結構化資料會略過
- 諮詢名單是個資：存在 instance/leads.db（獨立的檔案、不進 git，不和 quiz.db 放一起，因為 quiz.db 有進 git），
  只有工作人員登入後台才看得到（/admin/leads），可以匯出 Excel 用的 CSV
"""
import csv
import io
import json
import os
import re
import secrets
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

from flask import (Blueprint, Response, abort, redirect, render_template, request, session, url_for)

import admin

bp = Blueprint('site', __name__)
_ = {}

HERE = os.path.dirname(os.path.abspath(__file__))
INFO_PATH = os.path.join(HERE, 'public_site', 'site_info.json')
TW = timezone(timedelta(hours=8))

# 課程頁：只寫網站上真的有的東西，上課時間、師資、費用由 site_info.json 填
# points 是學員線上學習系統（單字學習、模擬考）在該科的功能。2026-11 使用者決定系統上線，官網要介紹：
# 各科專屬頁面與課程頁只列該科，主頁面列全部（加上 SYSTEM_BASIC 的英文基礎）。只寫系統真的有的東西
COURSES = [
    {"key": "toeic", "name": "多益", "en": "TOEIC", "title": "多益補習班｜多益全方位課程",
     "lead": "從職場情境單字到聽力閱讀，一步步把多益分數往上拉。",
     "kw": ["多益補習班", "多益課程", "TOEIC 補習", "多益單字"],
     "points": ["5,005 個多益職場單字，依主題分類，滑卡就能背",
                "「背單字神器」拼寫、聽寫、例句填空、選擇題輪流練",
                "答錯的字自動回到不熟區，下次優先複習"]},
    {"key": "ielts", "name": "雅思", "en": "IELTS", "title": "雅思補習班｜雅思全方位課程",
     "lead": "聽說讀寫四科完整備考，比照電腦考介面練習。",
     "kw": ["雅思補習班", "雅思課程", "IELTS 補習", "雅思口說", "雅思寫作"],
     "points": ["7,037 個雅思不重複單字，分 14 個主題",
                "聽力、閱讀、寫作、口說各 10 回自製模擬題，比照電腦考版面",
                "寫作、口說有 AI 老師依官方標準評分（模擬，不等於真實考試）"]},
    {"key": "toefl", "name": "托福", "en": "TOEFL", "title": "托福補習班｜托福全方位課程",
     "lead": "托福全方位課程。",
     "kw": ["托福補習班", "托福課程", "TOEFL 補習"],
     "points": []},
    {"key": "jlpt", "name": "日檢", "en": "JLPT", "title": "日文補習班｜日檢 N5～N1 課程",
     "lead": "從五十音到 N1，依等級學單字、做模擬考。",
     "kw": ["日文補習班", "日檢補習班", "JLPT", "日檢 N1", "日檢 N2", "日語課程"],
     "points": ["N5～N1 分級單字共 10,097 字，附假名讀音與動詞變化",
                "日檢模擬考 N5～N1 各 10 回，交卷看正解、解析與估計分數",
                "羅馬拼音自動轉假名，沒有日文輸入法也能練打字"]},
    {"key": "topik", "name": "韓檢", "en": "TOPIK", "title": "韓文補習班｜韓檢 TOPIK 課程",
     "lead": "TOPIK I、II 一次準備，1～6 級分級學習。",
     "kw": ["韓文補習班", "韓檢補習班", "TOPIK", "韓語課程", "韓檢中級"],
     "points": ["1～6 級分級單字共 6,630 字，韓語發音",
                "TOPIK I、TOPIK II 模擬考各 10 回，算總分與級數",
                "韓檢寫作有 AI 老師批改（模擬，不等於真實考試）"]},
]
COURSE_MAP = {c['key']: c for c in COURSES}
# 為什麼選驅勢（2026-11 使用者提供補習班手冊「Trinity is the best choice」，說「這裡面的內容都可以用」）。
# (標題, 說明, 短說明)：主頁面「為什麼選驅勢」用說明，各科專屬頁面的學校介紹用短說明。只寫手冊上有的；使用者要求只放前六點
WHY = [
    ("學員權益履約保證", "與遠東、永豐銀行簽訂 1,600 萬學員權益履約保證，讓學員更安心。", "與遠東、永豐銀行簽訂 1,600 萬履約保證"),
    ("專業面談程度分級", "除了電腦與紙筆測驗，每個課程都有專業面談，評估口說、字彙與句型，確實分級，不浪費時間與金錢。", "測驗加專業面談，確實分級"),
    ("學員導向排課系統", "線上排課系統，在家就能選課排課；教師評比與意見反應功能，和學員一起把關教學品質。", "在家就能線上選課、排課"),
    ("專業師資精緻教學", "專任教師團隊全時間專注於教學準備與課程研發。", "專任教師專注教學與課程研發"),
    ("循環開課多元課程", "每週超過 100 堂全外語聽說讀寫課程，持續循環開課，隨時都有新班。", "每週超過 100 堂，隨時有新班"),
    ("口說課程絕對小班", "認證與實力養成的口說班堅持小班制，互動最充分、練習最有效。", "口說班堅持小班制"),
]
# 程度分級制度（2026-11 使用者提供補習班手冊「TRINITY 專業程度分級制度」，要求放在主頁面）。依 CEFR 分 6 級；只寫手冊上有的
CEFR_LEVELS = [
    (1, "Fundamental", "基礎", "A1", ["自然發音", "實用生活字彙"]),
    (2, "Basic 1", "初級", "A2", ["實用生活字彙", "生活會話", "旅遊會話", "初級文法"]),
    (3, "Basic 2", "初中級", "B1", ["字彙倍增法", "生活會話", "旅遊會話", "片語會話", "主題式閱讀", "初中級文法"]),
    (4, "Intermediate 1", "中級", "B2", ["字彙倍增法", "Movie", "新聞會話", "國際新聞閱讀", "主題式討論", "寫作", "學術英文（托福／雅思先修班）", "中級文法"]),
    (5, "Intermediate 2", "中高級", "C1", ["學術英文（托福／雅思先修班）", "主題式討論", "主題式閱讀", "Movie English（影音英文）", "商用英文", "高階文法"]),
    (6, "Advanced", "高級", "C2", ["TED Talks（影音英文）", "CNN／BBC 新聞時事", "主題式討論", "主題式閱讀", "高階會話", "英文雜誌"]),
]
# 各檢定對照：對應 B1、B2、C1、C2（第 3～6 級）
CEFR_COLS = ["B1", "B2", "C1", "C2"]
CEFR_EXAMS = [
    ("全民英檢 GEPT", ["初級", "中級", "中高級", "高級"]),
    ("多益 TOEIC", ["550 以上", "650 以上", "750 以上", "850 以上"]),
    ("雅思 IELTS", ["4 以上", "4.5～5 以上", "5.5～6 以上", "7 以上"]),
    ("托福 TOEFL-iBT", ["38 以上", "61 以上", "71 以上", "100 以上"]),
]
# 主頁面的學習系統介紹另外列英文基礎（英文零基礎、一般英文，不是對外課程，但系統裡有）
SYSTEM_BASIC = {"key": "basic", "name": "英文基礎", "en": "BASIC",
                "points": ["英文零基礎 2,006 字，每個字有 KK 音標，可以正常速度或慢慢聽",
                           "一般英文 4,032 個日常生活字，和零基礎不重複"]}
# 迷你模考：多益、雅思、日檢、韓檢（日檢、韓檢不分級，測完給預估級數）
MOCKS = [("toeic", "多益"), ("ielts", "雅思"), ("jlpt", "日檢"), ("topik", "韓檢")]
MOCKS_READY = {"toeic", "ielts", "jlpt", "topik"}   # 已經有題目的迷你模考（school_mock.py、public_site/mock/<考試>.json）
MOCK_BLURB = {"toeic": "聽力＋閱讀 22 題，約 12 分鐘，交卷看預估分數",
              "ielts": "聽力＋閱讀 20 題，約 15 分鐘，交卷看預估 Band",
              "jlpt": "不用選級數，N5～N1 共 25 題，交卷看預估級數",
              "topik": "不用選級數，1～6 級共 24 題，交卷看預估級數"}
IDENTITIES = ['學生', '上班族', '家長（幫孩子詢問）', '其他']
CONTACT_TIMES = ['都可以', '平日白天', '平日晚上', '週末']
PUBLIC_PREFIXES = ('/courses', '/campus', '/contact', '/mock-test', '/privacy', '/thanks')


# ---------------------------------------------------------------------------
# 補習班資料
# ---------------------------------------------------------------------------

def info():
    try:
        with open(INFO_PATH, encoding='utf-8') as f:
            data = json.load(f)
    except (OSError, ValueError):
        data = {}
    data.setdefault('name', '趨勢補習班')
    data.setdefault('campuses', [])
    data.setdefault('courses', {})
    for c in data['campuses']:
        c.setdefault('label', c.get('name', '') + '校')
        if not c.get('map_url') and c.get('address'):
            c['map_url'] = 'https://www.google.com/maps/search/?api=1&query=' + quote(f"{data['name']} {c['address']}")
    return data


def campus_of(slug):
    return next((c for c in info()['campuses'] if c.get('slug') == slug), None)


def base_url():
    """正式網址（site_info.json 的 site_url）；還沒有就用目前連進來的網址。"""
    url = (info().get('site_url') or '').strip().rstrip('/')
    return url or request.url_root.rstrip('/')


def abs_url(endpoint, **kw):
    return base_url() + url_for(endpoint, **kw)


def org_jsonld():
    d = info()
    org = {"@context": "https://schema.org", "@type": "EducationalOrganization",
           "name": d['name'], "url": base_url() + '/'}
    alt = [x for x in [d.get('name_en')] + d.get('alt_names', []) if x]
    if alt:
        org['alternateName'] = alt
    for k_src, k_out in ( ('phone', 'telephone'), ('email', 'email'),
                         ('intro', 'description'), ('founded', 'foundingDate')):
        if d.get(k_src):
            org[k_out] = d[k_src]
    if d.get('logo'):
        org['logo'] = base_url() + url_for('static', filename=d['logo'])
    same = [d[k] for k in ('line_url', 'facebook_url', 'instagram_url') if d.get(k)]
    if same:
        org['sameAs'] = same
    deps = [campus_jsonld(c, nested=True) for c in d['campuses']]
    if deps:
        org['department'] = deps
    return org


def campus_jsonld(c, nested=False):
    d = info()
    out = {"@type": "EducationalOrganization", "name": f"{d['name']} {c['label']}",
           "url": abs_url('site.campus', slug=c['slug'])}
    if not nested:
        out["@context"] = "https://schema.org"
    addr = {"@type": "PostalAddress", "addressCountry": "TW", "addressRegion": c.get('city', '')}
    if c.get('address'):
        addr['streetAddress'] = c['address']
    out['address'] = addr
    if c.get('phone') or d.get('phone'):
        out['telephone'] = c.get('phone') or d.get('phone')
    if c.get('map_url'):
        out['hasMap'] = c['map_url']
    return out


def breadcrumb(*items):
    """items：(名稱, 網址)…，首頁會自動加在最前面。"""
    items = (('首頁', base_url() + '/'),) + items
    return {"@context": "https://schema.org", "@type": "BreadcrumbList",
            "itemListElement": [{"@type": "ListItem", "position": i + 1, "name": n, "item": u}
                                for i, (n, u) in enumerate(items)]}


def page(template, *, title, description, keywords=(), jsonld=(), **kw):
    d = info()
    full_title = title if d['name'] in title else f"{title}｜{d['name']}"
    return render_template(template, s=d, courses=COURSES, mocks=MOCKS, mocks_ready=MOCKS_READY, system_basic=SYSTEM_BASIC, why=WHY, cefr_levels=CEFR_LEVELS, cefr_cols=CEFR_COLS, cefr_exams=CEFR_EXAMS, mock_blurb=MOCK_BLURB, page_title=full_title,
                           description=description, keywords=', '.join(keywords),
                           canonical=base_url() + request.path,
                           jsonld=[json.dumps(j, ensure_ascii=False).replace('<', '\\u003c') for j in jsonld], **kw)


# ---------------------------------------------------------------------------
# 公開頁面
# ---------------------------------------------------------------------------

@bp.route('/')
def home():
    # 2026-11 使用者要求：官網（含校區）不連到學生系統，已登入的學生也照樣看官網
    d = info()
    towns = '、'.join(c['name'] for c in d['campuses'])
    if not session.get('site_csrf'):          # 首頁主視覺下面直接有諮詢表單（送到 /contact），和諮詢頁共用同一個 csrf
        session['site_csrf'] = secrets.token_hex(16)
    hero = hero_course()
    return page('site/home.html', csrf=session['site_csrf'],
                title=f"{d['name']}｜{towns}多益、雅思、托福、日文、韓文補習班",
                description=f"{d['name']}在{towns}設有校區，提供多益、雅思、托福、日檢、韓檢課程，"
                            f"專屬學習規劃、免費多益程度測驗。免費諮詢、加 LINE 了解課程。",
                keywords=[f"{c['name']}{k}" for c in d['campuses'][:5] for k in ('補習班', '多益補習班', '英文補習班')]
                         + ['多益補習班', '雅思補習班', '日文補習班', '韓文補習班', '托福補習班'],
                jsonld=[org_jsonld()], hero=hero, reviews=reviews_for(d, hero['c']['key']))


def reviews_for(d, key, n=3):
    """學員心得（2026-11 使用者要求：廣告進來的首頁，學校與課程介紹下面放學員心得）。
    資料在 site_info.json 的 testimonials，只放補習班提供的真實心得，不要自己編；
    同一個考試的心得排前面，最多 n 則。沒有資料時樣板顯示「待填」。"""
    rows = [t for t in d.get('testimonials') or [] if isinstance(t, dict) and (t.get('text') or '').strip()]
    rows.sort(key=lambda t: t.get('course') != key)
    for t in rows:
        c = COURSE_MAP.get(t.get('course') or '')
        t['course_name'] = c['name'] if c else ''
    return rows[:n]


def hero_course():
    """首頁最上面顯示哪個考試（2026-11 使用者要求：之後下廣告，從多益廣告點進來最上面就是多益，以此類推）。
    廣告連結加 ?exam=ielts（或 toeic、toefl、jlpt、topik），也認 utm_content／utm_campaign 等於考試代號；
    沒帶或看不懂就是多益、沒有下面的學校與課程介紹、學員心得。網址參數不影響 canonical，搜尋引擎只看到一個首頁。"""
    for k in ('exam', 'utm_content', 'utm_campaign'):
        key = (request.args.get(k) or '').strip().lower()
        if key in COURSE_MAP:
            return {'c': COURSE_MAP[key], 'ad': True}
    return {'c': COURSE_MAP['toeic'], 'ad': False}


@bp.route('/courses')
def courses():
    return page('site/courses.html', title='課程介紹｜多益、雅思、托福、日檢、韓檢',
                description=f"{info()['name']}的語言檢定課程：多益、雅思、托福、日檢 N5～N1、韓檢 TOPIK。",
                keywords=[k for c in COURSES for k in c['kw'][:2]],
                jsonld=[breadcrumb(('課程介紹', abs_url('site.courses')))])


@bp.route('/courses/<key>')
def course(key):
    c = COURSE_MAP.get(key)
    if not c:
        abort(404)
    d = info()
    towns = '、'.join(x['name'] for x in d['campuses'])
    extra = d['courses'].get(key, {})
    ld = {"@context": "https://schema.org", "@type": "Course", "name": f"{c['name']}（{c['en']}）課程",
          "description": c['lead'], "inLanguage": "zh-TW",
          "provider": {"@type": "EducationalOrganization", "name": d['name'], "url": base_url() + '/'}}
    return page('site/course.html', title=f"{towns.split('、')[0] if towns else ''}{c['title']}",
                description=f"{d['name']}{c['name']}課程：{c['lead']}{towns}校區開課，免費諮詢。",
                keywords=c['kw'] + [f"{x['name']}{c['kw'][0]}" for x in d['campuses']],
                jsonld=[ld, breadcrumb(('課程介紹', abs_url('site.courses')),
                                       (c['name'], abs_url('site.course', key=key)))],
                c=c, extra=extra)


@bp.route('/campus/<slug>')
def campus(slug):
    c = campus_of(slug)
    if not c:
        abort(404)
    d = info()
    return page('site/campus.html', title=f"{c['name']}補習班｜{d['name']} {c['label']}",
                description=f"{d['name']} {c['label']}：{c['name']}多益、雅思、托福、日文、韓文補習班。"
                            f"地址、電話、上課時間與免費諮詢。",
                keywords=[f"{c['name']}{k}" for k in ('補習班', '多益補習班', '雅思補習班', '日文補習班',
                                                     '韓文補習班', '英文補習班')],
                jsonld=[campus_jsonld(c), breadcrumb((c['label'], abs_url('site.campus', slug=slug)))],
                c=c)


@bp.route('/mock-test')
def mock_test():
    return page('site/mock.html', title='免費迷你模考｜多益、雅思、日檢、韓檢 10 分鐘測程度',
                description='10 分鐘迷你模考，測出多益、雅思、日檢、韓檢的程度，拿到分數、錯題與弱點分析報告。',
                keywords=['多益模擬考', '雅思模擬考', '日檢模擬考', '韓檢模擬考', '免費程度測驗'],
                jsonld=[breadcrumb(('免費迷你模考', abs_url('site.mock_test')))])


@bp.route('/privacy')
def privacy():
    return page('site/privacy.html', title='個人資料蒐集說明',
                description=f"{info()['name']}蒐集、使用與保護個人資料的說明。")


@bp.route('/contact', methods=['GET', 'POST'])
def contact():
    d = info()
    values, errors = {'courses': [request.args.get('course', '')], 'campus': request.args.get('campus', '')}, []
    if request.method == 'POST':
        if request.form.get('csrf') != session.get('site_csrf'):
            errors.append('表單已過期，請重新整理頁面再送出一次')
        elif request.form.get('website'):          # 機器人才會填的隱藏欄位：假裝成功，什麼都不存
            return redirect(url_for('site.thanks'))
        else:
            values, errors = validate(request.form, d)
            if not errors and too_many(client_ip()):
                errors.append('送出太多次了，請稍後再試，或直接加 LINE 聯絡我們')
            if not errors:
                save_lead(values)
                return redirect(url_for('site.thanks'))
    if not session.get('site_csrf'):
        session['site_csrf'] = secrets.token_hex(16)
    return page('site/contact.html', title='免費諮詢・預約試聽',
                description=f"填寫資料預約{d['name']}免費諮詢，或加 LINE 直接詢問多益、雅思、托福、日文、韓文課程。",
                keywords=['補習班諮詢', '預約試聽', '多益課程諮詢', '雅思課程諮詢'],
                jsonld=[breadcrumb(('免費諮詢', abs_url('site.contact')))],
                v=values, errors=errors, csrf=session['site_csrf'],
                identities=IDENTITIES, contact_times=CONTACT_TIMES)


@bp.route('/thanks')
def thanks():
    resp = Response(page('site/thanks.html', title='已收到您的資料', description='已收到您的諮詢資料。'))
    resp.headers['X-Robots-Tag'] = 'noindex'
    return resp


@bp.route('/robots.txt')
def robots():
    lines = ['User-agent: *', 'Allow: /']
    for p in ('/dashboard/', '/learn/', '/vocab', '/exam/', '/jlpt-mock/', '/topik-mock/', '/ai/',
              '/phonics/', '/admin', '/login', '/register', '/api/', '/tts', '/thanks',
              '/mock-test/result/'):
        lines.append(f'Disallow: {p}')
    lines.append(f'Sitemap: {abs_url("site.sitemap")}')
    return Response('\n'.join(lines) + '\n', mimetype='text/plain')


@bp.route('/sitemap.xml')
def sitemap():
    today = datetime.now(TW).date().isoformat()
    urls = [(abs_url('site.home'), '1.0'), (abs_url('site.courses'), '0.9')]
    urls += [(abs_url('site.course', key=c['key']), '0.9') for c in COURSES]
    urls += [(abs_url('site.campus', slug=c['slug']), '0.8') for c in info()['campuses']]
    urls += [(abs_url('site.mock_take', key=k), '0.8') for k, _n in MOCKS if k in MOCKS_READY]
    urls += [(abs_url('site.mock_test'), '0.7'), (abs_url('site.contact'), '0.8'), (abs_url('site.privacy'), '0.2')]
    body = ''.join(f'<url><loc>{u}</loc><lastmod>{today}</lastmod><priority>{p}</priority></url>' for u, p in urls)
    xml = f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{body}</urlset>'
    return Response(xml, mimetype='application/xml')


def is_public(path):
    return path in ('/', '/robots.txt', '/sitemap.xml') or path.startswith(PUBLIC_PREFIXES) \
        or path.startswith('/static/')


def noindex_private(resp):
    """學生的測驗系統、後台、登入頁都不讓搜尋引擎收錄。"""
    if not is_public(request.path):
        resp.headers.setdefault('X-Robots-Tag', 'noindex, nofollow')
    return resp


# ---------------------------------------------------------------------------
# 諮詢名單（個資）：獨立的 instance/leads.db，不進 git
# ---------------------------------------------------------------------------

LEAD_FIELDS = ['name', 'phone', 'email', 'line_id', 'identity', 'courses', 'campus', 'contact_time', 'message', 'source']


def client_ip():
    return request.headers.get('Cf-Connecting-Ip') or request.remote_addr or '?'


_hits = {}


def too_many(ip, limit=5, window=3600):
    """同一個 IP 一小時最多送 5 次，避免被灌假名單。"""
    now = time.time()
    hits = [t for t in _hits.get(ip, []) if now - t < window]
    if len(hits) >= limit:
        _hits[ip] = hits
        return True
    _hits[ip] = hits + [now]
    return False


def db_path():
    return os.path.join(_['app'].instance_path, 'leads.db')


def conn():
    os.makedirs(_['app'].instance_path, exist_ok=True)
    c = sqlite3.connect(db_path())
    c.row_factory = sqlite3.Row
    c.execute("""CREATE TABLE IF NOT EXISTS leads (
        id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT NOT NULL,
        name TEXT, phone TEXT, email TEXT, line_id TEXT, identity TEXT, courses TEXT, campus TEXT,
        contact_time TEXT, message TEXT, source TEXT, consent INTEGER DEFAULT 0,
        status TEXT DEFAULT 'new', staff_note TEXT DEFAULT '')""")
    cols = {r[1] for r in c.execute('PRAGMA table_info(leads)')}
    if 'mock' not in cols:   # 迷你模考的成績摘要（school_mock.py）
        c.execute("ALTER TABLE leads ADD COLUMN mock TEXT DEFAULT ''")
    if 'mailed' not in cols:   # 通知信寄過沒有（lead_mail.py；沒寄成功的之後會補寄）
        c.execute("ALTER TABLE leads ADD COLUMN mailed INTEGER DEFAULT 0")
    return c


PHONE_RE = re.compile(r'^(09\d{8}|0\d{1,2}\d{6,8}|\+?886\d{8,9})$')
EMAIL_RE = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')


def validate(form, d):
    v = {k: (form.get(k) or '').strip()[:500] for k in LEAD_FIELDS if k != 'courses'}
    v['phone'] = re.sub(r'[\s\-()]', '', v['phone'])
    v['courses'] = [k for k in form.getlist('courses') if k in COURSE_MAP]
    v['consent'] = form.get('consent') == 'yes'
    errors = []
    if not v['name']:
        errors.append('請填姓名')
    if not PHONE_RE.match(v['phone']):
        errors.append('請填正確的電話（例如 0912345678）')
    if v['email'] and not EMAIL_RE.match(v['email']):
        errors.append('電子郵件格式不對')
    if v['campus'] and v['campus'] not in [c['name'] for c in d['campuses']]:
        v['campus'] = ''
    if v['identity'] not in IDENTITIES:
        v['identity'] = ''
    if v['contact_time'] not in CONTACT_TIMES:
        v['contact_time'] = ''
    if not v['consent']:
        errors.append('請勾選同意個人資料蒐集說明')
    return v, errors


def save_lead(v, mock=''):
    with conn() as c:
        cur = c.execute("""INSERT INTO leads (created_at, name, phone, email, line_id, identity, courses, campus,
                     contact_time, message, source, consent, mock) VALUES (?,?,?,?,?,?,?,?,?,?,?,1,?)""",
                        (datetime.now(TW).strftime('%Y-%m-%d %H:%M'), v['name'], v['phone'], v['email'], v['line_id'],
                         v['identity'], '、'.join(COURSE_MAP[k]['name'] for k in v['courses']), v['campus'],
                         v['contact_time'], v['message'], v['source'][:200], mock))
        lead_id = cur.lastrowid
        row = dict(c.execute('SELECT * FROM leads WHERE id=?', (lead_id,)).fetchone())
    import lead_mail
    lead_mail.notify_lead(row, info())
    return lead_id


def lead_rows(status=None):
    with conn() as c:
        if status in ('new', 'done'):
            return c.execute('SELECT * FROM leads WHERE status=? ORDER BY id DESC', (status,)).fetchall()
        return c.execute('SELECT * FROM leads ORDER BY id DESC').fetchall()


@admin.bp.route('/leads')
@admin.login_required
def leads():
    status = request.args.get('status', 'new')
    with conn() as c:
        counts = dict(c.execute('SELECT status, COUNT(*) FROM leads GROUP BY status').fetchall())
    return render_template('site/admin_leads.html', rows=lead_rows(status), status=status, counts=counts)


@admin.bp.route('/leads/<int:lead_id>', methods=['POST'])
@admin.login_required
def lead_update(lead_id):
    status = 'done' if request.form.get('status') == 'done' else 'new'
    with conn() as c:
        c.execute('UPDATE leads SET status=?, staff_note=? WHERE id=?',
                  (status, (request.form.get('staff_note') or '').strip()[:500], lead_id))
    return redirect(url_for('admin.leads', status=request.args.get('back', 'new')))


def _cell(x):
    """擋 Excel 公式注入：表單填 =、+、-、@ 開頭的字，打開 CSV 時不會被當成公式執行。"""
    x = '' if x is None else str(x)
    return "'" + x if x[:1] in ('=', '+', '-', '@', '\t', '\r') else x


@admin.bp.route('/leads.csv')
@admin.login_required
def leads_csv():
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(['編號', '時間', '姓名', '電話', 'Email', 'LINE ID', '身分', '想了解的課程', '校區',
                '方便聯絡時段', '留言', '從哪一頁來', '模考成績', '狀態', '工作人員備註'])
    for r in lead_rows('all'):
        w.writerow([_cell(x) for x in [r['id'], r['created_at'], r['name'], r['phone'], r['email'], r['line_id'], r['identity'],
                    r['courses'], r['campus'], r['contact_time'], r['message'], r['source'], r['mock'],
                    '已聯絡' if r['status'] == 'done' else '未聯絡', r['staff_note']]])
    # 前面加 BOM，Excel 打開中文才不會亂碼
    return Response('﻿' + out.getvalue(), mimetype='text/csv',
                    headers={'Content-Disposition': 'attachment; filename=leads.csv',
                             'Cache-Control': 'no-store'})


def register(app, deps):
    """由 app.py 呼叫（要在 admin.register 之前，名單頁掛在後台的 bp 上）。deps：current_student。"""
    _.update(deps, app=app)
    app.after_request(noindex_private)
    import school_mock  # noqa: F401  迷你模考的路由掛在同一個 bp 上，要在註冊前載入
    app.register_blueprint(bp)
