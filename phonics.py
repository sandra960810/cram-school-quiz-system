"""英文零基礎：單字發音頁（/phonics/<學生id>）。

入口在零基礎的主介面（exams.py 的 features 有 "phonics"）。
2026-11 使用者要求「不要這麼複雜」：只留 KK 音標和「單字怎麼唸」。
頁面上選一個零基礎／一般英文主題，每個字顯示拼字、KK 音標、中文意思，
按「聽」唸正常速度、按「慢慢聽」放慢唸；下面列出整個主題的字，點一下就唸。
原本的 ABC 字母、發音規則課、聽音選字、跟讀評分都拿掉了。

音標資料在 pronunciation/kk.json（tools/make_pronunciation.py 由 CMU 發音字典產生）。
"""
import json
import os

from flask import Blueprint, jsonify, render_template, request

bp = Blueprint('phonics', __name__)

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
                               general_themes=[t for t in word_themes.values() if t["course"] == "GENERAL"])

    @bp.route('/phonics/<int:student_id>/words')
    def phonics_words(student_id):
        """某個主題的單字（拼字、KK 音標、中文），同拼字只給一次。"""
        get_student(student_id)
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
