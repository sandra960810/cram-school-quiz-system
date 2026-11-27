"""set_mail.bat 呼叫：設定官網諮詢通知信的寄件帳號，存在 instance/mail.json（不進 git），並寄一封測試信。"""
import json
import os
import smtplib
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
print('可以直接貼上（在視窗裡按滑鼠右鍵貼上），貼上後畫面會看得到，確認是 16 個字母再按 Enter。')
# 以前用 getpass（畫面不顯示）：Windows 的黑色視窗裡 Ctrl+V 貼不進去，還會混進看不到的控制字元，
# 使用者不知道自己貼錯，測試信就一直失敗。改成看得到的輸入，並只留英文字母。
raw = input('應用程式密碼：')
password = raw.replace(' ', '').strip()
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
if host == 'smtp.gmail.com':
    # Google 的應用程式密碼只有英文字母；濾掉貼上時混進來的空白、控制字元
    password = ''.join(ch for ch in password if ch.isascii() and ch.isalpha()).lower()
cfg = dict(user=user, password=password, smtp_host=host, smtp_port=port, sender_name=info.get('name', '') + ' 官網')
if host == 'smtp.gmail.com' and len(password) != 16:
    print(f'注意：Google 的應用程式密碼是 16 個英文字母，你輸入的有 {len(password)} 個，可能少貼或多貼了。還是先試寄看看。')
print('\n正在寄測試信...')
subject = f"【測試】{info.get('name', '')}官網諮詢通知"
body = '這是測試信。之後官網有人填表，就會用這個帳號寄通知到這個信箱。'
# 有些網路會擋 465 埠，連不上時自動改試 587
tries = [(host, port)]
if not custom and host == 'smtp.gmail.com':
    tries.append((host, 587))
ok, last = False, None
for h, p in tries:
    cfg['smtp_host'], cfg['smtp_port'] = h, p
    try:
        lead_mail.send(cfg, to or [user], subject, body)
        ok = True
        break
    except smtplib.SMTPAuthenticationError as e:
        last = e
        break          # 帳號密碼不對，換連接埠也沒用
    except Exception as e:
        last = e
        print(f'  用 {h}:{p} 連不上（{type(e).__name__}），換一個連接埠再試...')
if not ok:
    if isinstance(last, smtplib.SMTPAuthenticationError):
        why = '帳號或應用程式密碼不對（Google 不接受）。請確認：寄件 Email 就是建立應用程式密碼的那個帳號、密碼 16 個字母都有貼到。'
    elif isinstance(last, smtplib.SMTPRecipientsRefused):
        why = '收件信箱被拒絕，請確認 site_info.json 的 notify_email。'
    else:
        why = '連不上寄信伺服器，可能是這裡的網路或防毒軟體擋住寄信（465／587 埠）。'
    print('寄信失敗：', why)
    print('詳細錯誤：', repr(last))
    lead_mail.log(f'set_mail 測試信失敗：{type(last).__name__}: {str(last)[:200]}')
    print('設定沒有存檔。這個視窗的內容可以截圖給工程人員看（裡面沒有密碼）。')
    sys.exit(1)
os.makedirs(os.path.join(HERE, 'instance'), exist_ok=True)
with open(lead_mail.CONFIG, 'w', encoding='utf-8') as f:
    json.dump(cfg, f, ensure_ascii=False)
print('測試信已寄出，設定已存檔！請到', ', '.join(to or [user]), '收信確認。')

# 設定成功後，把之前存著但沒寄出通知的名單補寄出去
waiting = lead_mail.unsent()
if waiting:
    print(f'\n之前有 {len(waiting)} 筆名單還沒寄通知，現在補寄...')
    ok, bad = lead_mail.send_unsent(cfg, info)
    print(f'補寄完成：寄出 {ok} 筆' + (f'，{bad} 筆失敗（下次有新名單時會再補寄）' if bad else '') + '。')
