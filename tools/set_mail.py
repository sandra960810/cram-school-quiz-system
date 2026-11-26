"""set_mail.bat 呼叫：設定官網諮詢通知信的寄件帳號，存在 instance/mail.json（不進 git），並寄一封測試信。"""
import getpass
import json
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
import lead_mail  # noqa: E402

with open(os.path.join(HERE, 'public_site', 'site_info.json'), encoding='utf-8') as f:
    info = json.load(f)
to = lead_mail.recipients(info)
print('通知信會寄到：', ', '.join(to) or '（site_info.json 沒有設定 notify_email）')
print()
user = input('寄件用的 Email 帳號（例如 xxx@gmail.com 或公司 Google 信箱）：').strip()
if '@' not in user:
    print('Email 格式不對，已取消。')
    sys.exit(1)
print('請輸入這個帳號的「應用程式密碼」（16 個英文字母，不是平常登入的密碼）。')
print('輸入時畫面不會顯示任何字，打完按 Enter 就好。')
password = getpass.getpass('應用程式密碼：').replace(' ', '').strip()
if not password:
    print('沒有輸入密碼，已取消。')
    sys.exit(1)
domain = user.split('@')[1].lower()
host, port = 'smtp.gmail.com', 465
if domain in ('outlook.com', 'hotmail.com', 'live.com'):
    host, port = 'smtp.office365.com', 587
custom = input(f'寄信伺服器（直接按 Enter 用 {host}）：').strip()
if custom:
    host = custom
    port = int(input('連接埠（465 或 587）：').strip() or 465)
cfg = dict(user=user, password=password, smtp_host=host, smtp_port=port, sender_name=info.get('name', '') + ' 官網')
print('\n正在寄測試信...')
try:
    lead_mail.send(cfg, to or [user], f"【測試】{info.get('name', '')}官網諮詢通知",
                   '這是測試信。之後官網有人填表，就會用這個帳號寄通知到這個信箱。')
except Exception as e:
    print('寄信失敗：', repr(e))
    print('請確認帳號、應用程式密碼是否正確（Google 帳號要先開「兩步驟驗證」才能建立應用程式密碼）。設定沒有存檔。')
    sys.exit(1)
os.makedirs(os.path.join(HERE, 'instance'), exist_ok=True)
with open(lead_mail.CONFIG, 'w', encoding='utf-8') as f:
    json.dump(cfg, f, ensure_ascii=False)
print('測試信已寄出，設定已存檔！請到', ', '.join(to or [user]), '收信確認。')
