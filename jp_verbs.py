"""日文動詞變化：日檢單字卡上顯示「ます形、ない形、て形…」。

依單字檔的「詞性」判斷動詞種類（第一類＝五段、第二類＝一段、第三類＝する／来る），
不靠字尾猜（帰る、入る這種長得像一段的五段動詞，單字檔已經標對）。
「名詞・する動詞」（勉強）顯示「勉強する」的變化。

conjugations(word, reading, pos) 回傳 {"base": 原形, "base_reading": 讀音, "forms": [{label, word, reading}]}，
不是動詞就回傳 None。寫法（漢字）和讀音（假名）一起變，例如 会う／あう → 会います／あいます。
"""

# 五段動詞字尾 → い段、あ段、え段、お段
_I = dict(zip('うくぐすつぬぶむる', 'いきぎしちにびみり'))
_A = dict(zip('うくぐすつぬぶむる', 'わかがさたなばまら'))
_E = dict(zip('うくぐすつぬぶむる', 'えけげせてねべめれ'))
_O = dict(zip('うくぐすつぬぶむる', 'おこごそとのぼもろ'))
# て形、た形
_TE = {'う': 'って', 'つ': 'って', 'る': 'って', 'む': 'んで', 'ぶ': 'んで', 'ぬ': 'んで',
       'く': 'いて', 'ぐ': 'いで', 'す': 'して'}

# 顯示順序與中文名稱
LABELS = [
    ('masu', 'ます形（禮貌）'),
    ('nai', 'ない形（否定）'),
    ('ta', 'た形（過去）'),
    ('nakatta', 'なかった形（過去否定）'),
    ('te', 'て形（連接）'),
    ('potential', '可能形（能夠）'),
    ('volitional', '意向形（～吧）'),
    ('ba', 'ば形（如果）'),
    ('passive', '被動形'),
    ('causative', '使役形（讓～）'),
    ('imperative', '命令形'),
]


def _godan(stem, end, is_iku=False, is_aru=False):
    te = 'って' if is_iku else _TE[end]
    ta = te[:-1] + ('だ' if te.endswith('で') else 'た')
    a = _A[end]
    return {
        'masu': stem + _I[end] + 'ます',
        'nai': 'ない' if is_aru else (stem + a + 'ない'),          # ある的否定是「ない」
        'ta': stem + ta,
        'nakatta': 'なかった' if is_aru else (stem + a + 'なかった'),
        'te': stem + te,
        'potential': stem + _E[end] + 'る',
        'volitional': stem + _O[end] + 'う',
        'ba': stem + _E[end] + 'ば',
        'passive': stem + a + 'れる',
        'causative': stem + a + 'せる',
        'imperative': stem + _E[end],
    }


def _drop_aru(f):
    # ある沒有可能形、被動形、使役形、命令形的日常用法，不顯示
    for k in ('potential', 'passive', 'causative', 'imperative'):
        f[k] = None
    return f


def _ichidan(stem):
    return {
        'masu': stem + 'ます', 'nai': stem + 'ない', 'ta': stem + 'た', 'nakatta': stem + 'なかった',
        'te': stem + 'て', 'potential': stem + 'られる', 'volitional': stem + 'よう', 'ba': stem + 'れば',
        'passive': stem + 'られる', 'causative': stem + 'させる', 'imperative': stem + 'ろ',
    }


def _suru(prefix):
    return {
        'masu': prefix + 'します', 'nai': prefix + 'しない', 'ta': prefix + 'した', 'nakatta': prefix + 'しなかった',
        'te': prefix + 'して', 'potential': prefix + 'できる', 'volitional': prefix + 'しよう', 'ba': prefix + 'すれば',
        'passive': prefix + 'される', 'causative': prefix + 'させる', 'imperative': prefix + 'しろ',
    }


def _kuru_reading(prefix):
    return {
        'masu': prefix + 'きます', 'nai': prefix + 'こない', 'ta': prefix + 'きた', 'nakatta': prefix + 'こなかった',
        'te': prefix + 'きて', 'potential': prefix + 'こられる', 'volitional': prefix + 'こよう', 'ba': prefix + 'くれば',
        'passive': prefix + 'こられる', 'causative': prefix + 'こさせる', 'imperative': prefix + 'こい',
    }


def _kuru_written(prefix):
    """漢字寫法「来る」：漢字不變，只改後面的假名。"""
    tail = {k: v[1:] for k, v in _kuru_reading('').items()}   # きます → ます、こない → ない …
    return {k: prefix + '来' + v for k, v in tail.items()}


def _kind(pos):
    pos = pos or ''
    if '第一類' in pos or '五段' in pos:
        return 'godan'
    if '第二類' in pos or '一段' in pos:
        return 'ichidan'
    if '第三類' in pos:
        return 'irregular'
    if 'する動詞' in pos:
        return 'noun_suru'
    return None


def _forms(word, kind):
    """依種類變化一個字串（寫法或讀音）。變不了就回傳 None。"""
    if kind == 'noun_suru':
        return _suru(word)
    if kind == 'irregular':
        if word.endswith('する'):
            return _suru(word[:-2])
        if word.endswith('ずる'):           # 信ずる、感ずる：じます、じない…
            p = word[:-2]
            return {'masu': p + 'じます', 'nai': p + 'じない', 'ta': p + 'じた', 'nakatta': p + 'じなかった',
                    'te': p + 'じて', 'potential': p + 'じられる', 'volitional': p + 'じよう', 'ba': p + 'ずれば',
                    'passive': p + 'じられる', 'causative': p + 'じさせる', 'imperative': p + 'じろ'}
        if word.endswith('くる'):
            return _kuru_reading(word[:-2])
        if word.endswith('来る'):
            return _kuru_written(word[:-2])
        return None
    if not word or not word.endswith(tuple(_I)):
        return None
    stem, end = word[:-1], word[-1]
    if kind == 'ichidan' and end == 'る':
        return _ichidan(stem)
    # 標成第二類卻不是る結尾（單字檔標錯，例如励ます）：照五段變
    is_iku = word.endswith(('行く', 'いく', '逝く', 'ゆく')) and end == 'く'
    is_aru = word in ('ある', '有る', '在る')
    f = _godan(stem, end, is_iku=is_iku, is_aru=is_aru)
    return _drop_aru(f) if is_aru else f


def conjugations(word, reading, pos):
    kind = _kind(pos)
    if not kind or not word:
        return None
    reading = (reading or '').split('／')[0].strip() or word
    base, base_r = word, reading
    if kind == 'noun_suru':
        if word.endswith('する'):
            kind = 'irregular'
        else:
            base, base_r = word + 'する', reading + 'する'
            kind = 'irregular'
    fw = _forms(base, kind)
    fr = _forms(base_r, kind)
    if not fr:
        return None
    if not fw:
        fw = fr
    forms = [{"label": label, "word": fw[k], "reading": fr[k] if fr[k] != fw[k] else ''}
             for k, label in LABELS if fw.get(k) and fr.get(k)]
    return {"base": base, "base_reading": base_r if base_r != base else '', "forms": forms}
