"""官網有人填「免費諮詢」或迷你模考解鎖表單時，自動寄信通知補習班（2026-11 使用者要求寄到 service@wkedu.com.tw）。

- 收件人：public_site/site_info.json 的 notify_email（可用逗號分隔多個）
- 寄件帳號：instance/mail.json（不進 git），在櫃台電腦雙擊 set_mail.bat 設定（Gmail／Google Workspace 用「應用程式密碼」）
- 在背景寄，寄失敗不影響表單送出，名單照樣存在 instance/leads.db；結果記在 instance/mail_log.txt
- leads.mailed 記這筆寄過沒有；沒寄成功的（還沒設定寄件帳號、寄信失敗）之後會補寄：
  set_mail.bat 設定成功時、以及每次有新名單寄出後，都會把還沒寄的一起寄（使用者要求「存在裡面的也都寄過去」）
"""
import json
import os
import smtplib
import sqlite3
import ssl
import threading
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from email.utils import formataddr

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG = os.path.join(HERE, 'instance', 'mail.json')
LOG = os.path.join(HERE, 'instance', 'mail_log.txt')
TW = timezone(timedelta(hours=8))
DB = os.path.join(HERE, 'instance', 'leads.db')
_lock = threading.Lock()     # 一次只讓一條線補寄，免得同一筆寄兩次


def load_config():
    try:
        with open(CONFIG, encoding='utf-8') as f:
            cfg = json.load(f)
    except (OSError, ValueError):
        return None
    return cfg if cfg.get('user') and cfg.get('password') else None


def log(msg):
    try:
        os.makedirs(os.path.dirname(LOG), exist_ok=True)
        with open(LOG, 'a', encoding='utf-8') as f:
            f.write(f"{datetime.now(TW):%Y-%m-%d %H:%M:%S} {msg}\n")
    except OSError:
        pass


def send(cfg, to, subject, body):
    msg = EmailMessage()
    msg['From'] = formataddr((cfg.get('sender_name') or '官網通知', cfg['user']))
    msg['To'] = ', '.join(to)
    msg['Subject'] = subject
    msg.set_content(body)
    host, port = cfg.get('smtp_host') or 'smtp.gmail.com', int(cfg.get('smtp_port') or 465)
    ctx = ssl.create_default_context()
    if port == 465:
        with smtplib.SMTP_SSL(host, port, context=ctx, timeout=20) as s:
            s.login(cfg['user'], cfg['password'])
            s.send_message(msg)
    else:
        with smtplib.SMTP(host, port, timeout=20) as s:
            s.starttls(context=ctx)
            s.login(cfg['user'], cfg['password'])
            s.send_message(msg)


def recipients(info):
    return [x.strip() for x in (info.get('notify_email') or '').split(',') if x.strip()]


def lead_text(lead, site_name):
    rows = [('時間', lead.get('created_at')), ('姓名', lead.get('name')), ('電話', lead.get('phone')),
            ('Email', lead.get('email')), ('LINE ID', lead.get('line_id')), ('身分', lead.get('identity')),
            ('想了解的課程', lead.get('courses')), ('校區', lead.get('campus')), ('方便聯絡時段', lead.get('contact_time')),
            ('模考成績', lead.get('mock')), ('留言', lead.get('message')), ('來源', lead.get('source'))]
    body = '\n'.join(f'{k}：{v}' for k, v in rows if v)
    return (f"{site_name}官網收到一筆新的諮詢資料：\n\n{body}\n\n"
            "所有名單都在網站後台「官網諮詢名單」（工作人員登入後台 /admin/leads）。\n"
            "這封信含學生個人資料，請勿轉寄給無關的人。")


def subject_of(lead):
    return f"【官網諮詢】{lead.get('name', '')} {lead.get('courses') or lead.get('source') or ''}".strip()


def _conn():
    c = sqlite3.connect(DB, timeout=15)
    c.row_factory = sqlite3.Row
    cols = {r[1] for r in c.execute('PRAGMA table_info(leads)')}
    if cols and 'mailed' not in cols:
        c.execute("ALTER TABLE leads ADD COLUMN mailed INTEGER DEFAULT 0")
    return c


def mark_mailed(lead_id):
    try:
        with _conn() as c:
            c.execute('UPDATE leads SET mailed=1 WHERE id=?', (lead_id,))
    except sqlite3.Error as e:
        log(f'記錄已寄出失敗（id {lead_id}）：{e!r}')


def unsent():
    if not os.path.exists(DB):
        return []
    try:
        with _conn() as c:
            return [dict(r) for r in c.execute('SELECT * FROM leads WHERE COALESCE(mailed,0)=0 ORDER BY id')]
    except sqlite3.Error:
        return []


def send_unsent(cfg, info):
    """把還沒寄過通知的名單補寄出去，回傳 (寄出幾筆, 失敗幾筆)。"""
    to = recipients(info)
    if not to or not cfg:
        return 0, 0
    ok = bad = 0
    with _lock:
        for lead in unsent():
            subject = subject_of(lead)
            try:
                send(cfg, to, subject, lead_text(lead, info.get('name', '')))
                mark_mailed(lead['id'])
                log(f"已寄出：{subject} → {', '.join(to)}")
                ok += 1
            except Exception as e:
                log(f"寄信失敗：{subject}：{e!r}")
                bad += 1
                break          # 連不上或登入失敗，後面的也不用試了，下次再補
    return ok, bad


def notify_lead(lead, info):
    """表單存檔後呼叫；在背景寄信，不讓學生等。沒設定寄件帳號就只記一筆 log（之後會補寄）。"""
    to, cfg = recipients(info), load_config()
    if not to:
        return
    if not cfg:
        log('沒有寄信：還沒設定寄件帳號（雙擊 set_mail.bat）')
        return
    # 這筆和之前沒寄成功的一起寄
    threading.Thread(target=send_unsent, args=(cfg, info), daemon=True).start()
