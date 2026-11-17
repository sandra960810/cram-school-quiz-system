"""檢查 AI 老師的 API 金鑰能不能用（set_ai_key.bat 會呼叫）。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import writing_bank  # noqa: E402

key = writing_bank.api_key()
if not key:
    print('找不到金鑰：ai_key.txt 是空的。')
    sys.exit(1)
try:
    import anthropic
except ImportError:
    print('還沒安裝 anthropic 套件，請先雙擊 run.bat 一次。')
    sys.exit(1)

client = anthropic.Anthropic(api_key=key, timeout=60)
try:
    resp = client.messages.create(model=writing_bank.AI_MODEL, max_tokens=50,
                                  output_config={'effort': 'low'},
                                  messages=[{'role': 'user', 'content': 'Reply with the single word OK.'}])
except anthropic.AuthenticationError:
    print('金鑰無效：請確認貼上的是完整的金鑰（sk-ant- 開頭）。')
    sys.exit(1)
except anthropic.PermissionDeniedError:
    print('這把金鑰沒有權限，可能帳戶還沒儲值。')
    sys.exit(1)
except anthropic.APIConnectionError:
    print('連不上 Anthropic，請確認這台電腦有網路。')
    sys.exit(1)
except anthropic.APIStatusError as e:
    print(f'Anthropic 回報錯誤 {e.status_code}：{e.message}')
    sys.exit(1)
print('金鑰可以使用，AI 老師已就緒！')
