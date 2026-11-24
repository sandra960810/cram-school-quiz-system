"""英文零基礎：單字發音頁（/phonics/<學生id>）。

入口在零基礎的主介面（exams.py 的 features 有 "phonics"）。
2026-11 使用者要求「不要這麼複雜」：只留 KK 音標和「單字怎麼唸」。
頁面上選一個零基礎／一般英文主題，每個字顯示拼字、KK 音標、中文意思，
按「聽」唸正常速度、按「慢慢聽」放慢唸；下面列出整個主題的字，點一下就唸。
原本的 ABC 字母、發音規則課、聽音選字、跟讀評分都拿掉了。
同一個選單另有「常見字尾」（-tion、-ing、-ed、-er、-ly、-ful…）：每個字尾一組例字，
字尾和它在 KK 音標裡的那段音會標顏色，一樣按「聽」「慢慢聽」或點清單上的字。

音標資料在 pronunciation/kk.json（tools/make_pronunciation.py 由 CMU 發音字典產生）。
"""
import json
import os

from flask import Blueprint, jsonify, render_template, request

bp = Blueprint('phonics', __name__)

# 常見字尾：key, 字尾（拼字）, 念法（KK）, 提示, 例字 [(單字, 中文, KK)]。
# KK 留空就查 kk.json；字典裡沒有的變化形（-ing、-ed、-es）直接寫在這裡。
# 前端把單字結尾的「字尾」和 KK 結尾的「念法」標顏色，所以例字的 KK 一定要以念法結尾。
SUFFIXES = [
    ("tion", "tion", "ʃən", "像輕輕的「ㄕㄣ」，重音在它前面那一節", [
        ("nation", "國家", ""), ("station", "車站", ""), ("action", "行動", ""),
        ("vacation", "假期", ""), ("education", "教育", ""), ("information", "資訊", "")]),
    ("sion", "sion", "ʒən", "多半念 /ʒən/，比 -tion 多一點震動", [
        ("vision", "視力", ""), ("decision", "決定", ""), ("television", "電視", "")]),
    ("ing", "ing", "ɪŋ", "短短的「一」接鼻音「ㄥ」，g 不要另外念出來", [
        ("running", "跑步", "ˈrʌnɪŋ"), ("eating", "吃", "ˈitɪŋ"), ("reading", "閱讀", "ˈridɪŋ"),
        ("singing", "唱歌", "ˈsɪŋɪŋ"), ("swimming", "游泳", ""), ("morning", "早上", "")]),
    ("ed-t", "ed", "t", "-ed 念 /t/：前面是 p、k、s、sh、ch、f 這類不震動的音", [
        ("jumped", "跳了", "dʒʌmpt"), ("walked", "走了", "wɔkt"), ("helped", "幫忙了", "hɛlpt"),
        ("washed", "洗了", "wɑʃt"), ("cooked", "煮了", "kʊkt")]),
    ("ed-d", "ed", "d", "-ed 念 /d/：前面是母音或 b、g、l、m、n 這類會震動的音", [
        ("played", "玩了", "pled"), ("called", "打電話了", "kɔld"), ("opened", "打開了", "ˈopənd"),
        ("cleaned", "打掃了", "klind")]),
    ("ed-id", "ed", "ɪd", "-ed 念 /ɪd/：前面是 t 或 d，多一個音節", [
        ("wanted", "想要了", "ˈwɑntɪd"), ("needed", "需要了", "ˈnidɪd"), ("visited", "拜訪了", "ˈvɪzɪtɪd"),
        ("started", "開始了", "ˈstɑrtɪd")]),
    ("es", "es", "ɪz", "字尾是 s、x、sh、ch 時加 -es，念 /ɪz/，多一個音節", [
        ("boxes", "盒子（複數）", "ˈbɑksɪz"), ("buses", "公車（複數）", "ˈbʌsɪz"),
        ("watches", "手錶（複數）", "ˈwɑtʃɪz"), ("dishes", "盤子（複數）", "ˈdɪʃɪz")]),
    ("er", "er", "ɚ", "輕輕捲舌的「ㄦ」，常表示「做這件事的人」", [
        ("teacher", "老師", ""), ("singer", "歌手", ""), ("water", "水", ""), ("sister", "姊妹", ""), ("dinner", "晚餐", "")]),
    ("or", "or", "ɚ", "在字尾和 -er 念法一樣", [
        ("doctor", "醫生", ""), ("actor", "演員", ""), ("visitor", "訪客", ""), ("color", "顏色", "")]),
    ("ture", "ture", "tʃɚ", "念「ㄑㄩㄦ」，不是 ture 照拼字念", [
        ("picture", "圖畫；照片", ""), ("future", "未來", ""), ("nature", "自然", ""), ("culture", "文化", "")]),
    ("ly", "ly", "li", "「ㄌㄧ」，常把形容詞變成副詞", [
        ("slowly", "慢慢地", ""), ("quickly", "快速地", ""), ("really", "真的", ""), ("friendly", "友善的", ""), ("happily", "快樂地", "")]),
    ("y", "y", "i", "字尾的 y 念「一」", [
        ("happy", "快樂的", ""), ("sunny", "晴朗的", ""), ("funny", "好笑的", ""), ("baby", "嬰兒", ""), ("candy", "糖果", "")]),
    ("ful", "ful", "fəl", "輕輕的「ㄈㄜㄌ」，不念成 full", [
        ("helpful", "有幫助的", ""), ("beautiful", "美麗的", ""), ("careful", "小心的", ""), ("useful", "有用的", ""), ("wonderful", "很棒的", "")]),
    ("less", "less", "ləs", "輕輕的「ㄌㄜㄙ」，意思是「沒有…」", [
        ("careless", "粗心的", ""), ("homeless", "無家可歸的", ""), ("useless", "沒用的", ""), ("endless", "沒完沒了的", "")]),
    ("ness", "ness", "nəs", "輕輕的「ㄋㄜㄙ」，把形容詞變成名詞", [
        ("kindness", "善良", ""), ("sadness", "難過", ""), ("happiness", "快樂", ""), ("darkness", "黑暗", "")]),
    ("ment", "ment", "mənt", "輕輕的「ㄇㄣㄊ」", [
        ("payment", "付款", ""), ("movement", "動作", ""), ("agreement", "同意", ""), ("apartment", "公寓", "")]),
    ("ous", "ous", "əs", "輕輕的「ㄜㄙ」，不念成 o-u-s", [
        ("famous", "有名的", ""), ("dangerous", "危險的", ""), ("nervous", "緊張的", ""), ("jealous", "嫉妒的", "")]),
]
SUFFIX_BY_KEY = {x[0]: x for x in SUFFIXES}

KK_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'pronunciation', 'kk.json')
_kk = None


def kk_table():
    global _kk
    if _kk is None:
        try:
            with open(KK_PATH, encoding='utf-8') as f:
                _kk = json.load(f)
        except OSError:
            _kk = {}
    return _kk


def kk_of(word):
    """單字的 KK 音標（含重音符號 ˈ），字典沒有就回空字串。"""
    p = kk_table().get(word.strip().lower())
    return p["kk"] if p else ''


def register(app, get_student, Vocabulary, theme_condition, themes):
    """themes：官方主題，單字發音可以挑零基礎（BASIC）與一般英文（GENERAL）的主題。"""
    word_themes = {t["id"]: t for t in themes if t["course"] in ("BASIC", "GENERAL")}

    @bp.route('/phonics/<int:student_id>')
    def phonics_home(student_id):
        student = get_student(student_id)
        return render_template('phonics.html', student=student,
                               basic_themes=[t for t in word_themes.values() if t["course"] == "BASIC"],
                               general_themes=[t for t in word_themes.values() if t["course"] == "GENERAL"],
                               suffixes=[{"key": k, "suf": suf, "kk": kk} for k, suf, kk, _h, _w in SUFFIXES])

    @bp.route('/phonics/<int:student_id>/words')
    def phonics_words(student_id):
        """某個主題的單字（拼字、KK 音標、中文），同拼字只給一次。"""
        get_student(student_id)
        suf = SUFFIX_BY_KEY.get(request.args.get('suffix', ''))
        if suf:
            key, spell, sound, hint, words = suf
            return jsonify({"suffix": {"suf": spell, "kk": sound, "hint": hint},
                            "words": [{"word": w, "zh": zh, "kk": kk or kk_of(w)} for w, zh, kk in words]})
        theme = word_themes.get(request.args.get('theme', ''))
        if not theme:
            return jsonify([])
        rows = Vocabulary.query.filter(Vocabulary.category == theme["course"], theme_condition(theme["id"])) \
            .order_by(Vocabulary.id).all()
        seen, out = set(), []
        for v in rows:
            key = v.word.strip().lower()
            if key in seen or ' ' in key:
                continue
            seen.add(key)
            out.append({"word": v.word.strip(), "zh": v.meaning or '', "kk": kk_of(key)})
        return jsonify(out)

    app.register_blueprint(bp)
