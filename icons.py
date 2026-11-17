"""全站線條圖示：取代 emoji，讓圖示跟紫色學院風一致（單色、細線、跟著文字顏色）。

圖示本體在 static/icons.svg（一個 symbol 一個圖示），這裡負責產生 <svg><use> 標籤。
輸出的 HTML 刻意不帶任何引號，所以放進 JS 字串（'…'、"…"、`…`）也不會壞掉。
"""
import re
from markupsafe import Markup, escape

# 舊資料或舊樣板裡的 emoji → 圖示名稱。新程式請直接寫圖示名稱。
EMOJI = {
    '📚': 'library', '📖': 'book-open', '🎧': 'headphones', '🧠': 'quiz', '📝': 'exam',
    '✍️': 'pen', '✍': 'pen', '🗣️': 'speech', '🗣': 'speech', '🎙️': 'mic', '🎙': 'mic', '📒': 'notebook',
    '⚠️': 'alert', '⚠': 'alert', '🔑': 'key', '💡': 'bulb', '🕑': 'clock', '⏱': 'clock', '⏳': 'hourglass',
    '🔁': 'refresh', '✅': 'check-circle', '❌': 'x-circle', '✏️': 'pencil', '✏': 'pencil',
    '🔊': 'volume', '🔈': 'volume', '🔇': 'volume-x', '⭐': 'star', '🟠': 'dot', '🎉': 'sparkle',
    '🔒': 'lock', '🧑‍🏫': 'teacher', '🧑': 'user', '👆': 'swipe', '📄': 'file', '🤖': 'bot',
    '🧩': 'puzzle', '🔤': 'type', '🅰️': 'letter', '🧪': 'flask', '👁️': 'eye', '🙈': 'eye-off',
    '🔍': 'search', '🏷️': 'tag', '📋': 'clipboard', '🎯': 'target', '🐢': 'slow', '👍': 'thumb',
    '💪': 'trend', '🖼️': 'image', '🙂': 'smile', '🎓': 'cap', '🌍': 'globe', '🔬': 'microscope',
    '🏥': 'heart', '🤝': 'users', '💰': 'coins', '⚖️': 'scale', '🏙️': 'building', '🎨': 'palette',
    '✈️': 'plane', '🗂️': 'folder',
}
_EMOJI_RE = re.compile('|'.join(sorted(map(re.escape, EMOJI), key=len, reverse=True)))


def icon(name):
    """{{ icon('book-open') }} → 一個線條圖示。也接受 emoji（會換成對應圖示）。
    大小跟著外層的 font-size（1em），顏色跟著外層的 color。"""
    name = EMOJI.get(name, name)
    if not re.fullmatch(r'[a-z-]+', name or ''):
        return Markup('')
    return Markup(f'<svg class=ui-ic aria-hidden=true><use href=/static/icons.svg#i-{name}></use></svg>')


def iconize(text):
    """把字串裡的 emoji 換成圖示，其餘文字照常跳脫。給資料裡的標籤用：{{ label|ico }}"""
    s = str(escape(text or ''))
    return Markup(_EMOJI_RE.sub(lambda m: str(icon(EMOJI[m.group(0)])), s))


def init_app(app):
    app.jinja_env.globals['icon'] = icon
    app.add_template_filter(iconize, 'ico')
