"""檢查 AI 老師的 API 金鑰能不能用（set_ai_key.bat 會呼叫）。
金鑰開頭 AIza 是 Google Gemini（免費額度），sk-ant- 是 Anthropic Claude。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import writing_bank  # noqa: E402

provider, key = writing_bank.ai_config()
if not key:
    print('找不到金鑰：ai_key.txt 是空的，或金鑰開頭不是 AIza（Gemini）或 sk-ant-（Claude）。')
    sys.exit(1)
print('偵測到的 AI 老師：' + writing_bank.ai_label())

if provider == 'gemini':
    try:
        from google import genai
        from google.genai import errors
    except ImportError:
        print('還沒安裝 google-genai 套件，請先雙擊 run.bat 一次。')
        sys.exit(1)
    client = genai.Client(api_key=key)
    for model in writing_bank.gemini_models():
        try:
            client.models.generate_content(model=model, contents='Reply with the single word OK.')
        except errors.APIError as e:
            if e.code == 404:
                print(f'模型 {model} 不存在，換下一個試試…')
                continue
            print(writing_bank._gemini_error(e))
            sys.exit(1)
        except Exception as e:
            print(f'連不上 Google，請確認這台電腦有網路。（{type(e).__name__}）')
            sys.exit(1)
        print(f'金鑰可以使用（模型 {model}），AI 老師已就緒！')
        sys.exit(0)
    print('找不到可用的 Gemini 模型，請通知維護人員。')
    sys.exit(1)

try:
    import anthropic
except ImportError:
    print('還沒安裝 anthropic 套件，請先雙擊 run.bat 一次。')
    sys.exit(1)
client = anthropic.Anthropic(api_key=key, timeout=60)
try:
    client.messages.create(model=writing_bank.CLAUDE_MODEL, max_tokens=50,
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
