"""建構式字彙：英文單字的字根、字首、字尾。

學生在單字卡上看到一個字時，卡片下方會跳出「同字根／同字首／同字尾」的其他字，
滑完一輪後推薦接著背整組字（例如 spect＝看：inspect、respect、spectator…）。

資料在 morphology/roots.txt，一行一組：種類|字形|意思|單字（空白分開）。
單字可以寫成「happiness=happy」，表示去掉字尾後是哪個字（單字卡上顯示 happiness ＝ happy ＋ -ness）；
沒寫的話，字首會試著去掉字首、字尾會試著去掉字尾，剩下的部分是字庫裡的字才顯示。
**每一組的字都是人工依字源逐字挑的**，不用字串比對自動猜（important 和 import 同源、
opportunity 卻和 port 無關，這種只能人工判斷）。新增字時請查字源確認，再加進那一行；
單字不在目前考試的字庫裡沒關係，畫面只顯示字庫裡有的字。

只用在英文的考試（雅思、多益、零基礎、一般英文），日檢、韓檢不顯示。

這個模組用 `register(app, db, deps)` 掛到主程式上，避免和 app.py 互相 import。
"""
import os
import re
import time

from flask import Blueprint, abort, jsonify, render_template, url_for

ENGLISH_COURSES = {'IELTS', 'TOEIC', 'BASIC', 'GENERAL'}
KIND_NAMES = {'prefix': '字首', 'root': '字根', 'suffix': '字尾'}
KIND_ORDER = {'root': 0, 'prefix': 1, 'suffix': 2}   # 單字卡上先顯示字根，再字首、字尾
CARD_FAMILIES = 4        # 一張單字卡最多顯示幾組
CARD_WORDS = 8           # 每組在單字卡上最多列幾個字
RECOMMEND = 3            # 滑完一輪最多推薦幾組
BIG_SUFFIX = 40          # 字尾的同組字超過這麼多就不在單字卡上列出

DATA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'morphology', 'roots.txt')

bp = Blueprint('word_roots', __name__)
_ = {}


def _slug(kind, form, used):
    """網址用的代號：spect、vis-vid、pre-un、suf-less；同字形的第二組加 -2。"""
    base = '-'.join(re.findall(r'[a-z]+', form.split('（')[0].lower())) or 'x'
    if kind == 'prefix':
        base = 'pre-' + base
    elif kind == 'suffix':
        base = 'suf-' + base
    key, n = base, 2
    while key in used:
        key, n = f'{base}-{n}', n + 1
    used.add(key)
    return key


def load_families(path=DATA_FILE):
    families, used = [], set()
    with open(path, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            kind, form, meaning, words = line.split('|')
            seen, members, stems = set(), [], {}
            for tok in words.split():
                w, _eq, stem = tok.lower().partition('=')
                if stem:
                    stems[w] = stem
                if w not in seen:
                    seen.add(w)
                    members.append(w)
            families.append({"key": _slug(kind, form, used), "kind": kind, "kind_name": KIND_NAMES[kind],
                             # 畫面上不顯示括號裡的區別字（terr（土地）、terr（害怕）靠意思就分得出來）
                             "form": form.split('（')[0], "meaning": meaning, "words": members, "stems": stems})
    return families


FAMILIES = load_families()
FAMILY_BY_KEY = {f["key"]: f for f in FAMILIES}
FAMILIES_OF_WORD = {}
for _f in FAMILIES:
    for _w in _f["words"]:
        FAMILIES_OF_WORD.setdefault(_w, []).append(_f)


def is_english(course):
    return course in ENGLISH_COURSES


def _alts(fam):
    """字形的各種拼法（去掉連字號）：「-tion／-sion」→ ['tion', 'sion']。"""
    return [re.sub(r'[^a-z]', '', a.replace('(s)', '')) for a in fam["form"].split('／')]


def stem_of(fam, word, words):
    """去掉字首／字尾後剩下的字（要是字庫裡的字才算），例如 unhappy → happy、happiness → happy；找不到回 None。"""
    stem = fam["stems"].get(word)
    if stem:
        return stem if stem in words else None
    if fam["kind"] == 'prefix':
        for a in _alts(fam):
            rest = word[len(a):].lstrip('-')
            if a and word.startswith(a) and len(rest) >= 3 and rest in words:
                return rest
    elif fam["kind"] == 'suffix':
        for a in _alts(fam):
            if not a or not word.endswith(a):
                continue
            base = word[:-len(a)]
            cands = [base, base + 'e']
            if base.endswith('i'):
                cands.append(base[:-1] + 'y')
            if len(base) > 1 and base[-1] == base[-2]:
                cands.append(base[:-1])
            for c in cands:
                if len(c) >= 3 and c != word and c in words:
                    return c
    return None


# ---------------------------------------------------------------------------
# 目前考試字庫裡的字
# ---------------------------------------------------------------------------

def course_words(student):
    """目前考試裡的字：{小寫拼字: Vocabulary}（同拼字留編號最小的那筆，沒開通的等級不算）。"""
    V = _['Vocabulary']
    rows = (V.query.filter(V.category == _['exams'].course_of(student))
            .order_by(V.id).all())
    locked = _['locked_theme_ids'](student)
    result = {}
    for v in rows:
        if locked and _['official_id_of'](v.theme) in locked:
            continue
        result.setdefault(v.word.lower(), v)
    return result


_all_cache = {"at": 0, "words": {}}


def all_english_words():
    """所有英文考試的字：{小寫拼字: Vocabulary}。拆字時「去掉字尾後的字」可能不在這個考試的字庫（零基礎才有 happy），
    就從這裡找意思。10 分鐘更新一次。"""
    if time.time() - _all_cache["at"] > 600:
        V = _['Vocabulary']
        words = {}
        for v in V.query.filter(V.category.in_(ENGLISH_COURSES)).order_by(V.id).all():
            words.setdefault(v.word.lower(), v)
        _all_cache.update(at=time.time(), words=words)
    return _all_cache["words"]


def family_rows(student, family, words=None):
    """這一組在目前字庫裡有的字（依資料檔的順序）。"""
    words = course_words(student) if words is None else words
    return [words[w] for w in family["words"] if w in words]


def word_item(student_id, v, status, root_key):
    """一個字的卡片資料；點開是單字卡，可以在這一組裡前後翻。"""
    return {"id": v.id, "word": v.word, "meaning": v.meaning, "pos": v.pos or '',
            "status": status.get(v.id, 'new'),
            "url": url_for('learn_word', student_id=student_id, theme_key=_['theme_key_of'](v),
                           vocab_id=v.id, root=root_key, **{"from": "root"})}


def family_summary(student, family, words, status):
    rows = family_rows(student, family, words)
    return {"key": family["key"], "kind": family["kind"], "kind_name": family["kind_name"],
            "form": family["form"], "meaning": family["meaning"], "total": len(rows),
            "familiar": sum(1 for v in rows if status.get(v.id) == 'familiar'),
            "unfamiliar": sum(1 for v in rows if status.get(v.id) == 'unfamiliar'),
            "new": sum(1 for v in rows if v.id not in status),
            "url": url_for('word_roots.family_page', student_id=student.id, key=family["key"]),
            "study_url": url_for('word_roots.family_study', student_id=student.id, key=family["key"])}


def families_for_word(student, vocab, words=None, status=None):
    """單字卡要顯示的組：這個字所屬的組（字根優先，最多 CARD_FAMILIES 組）。
    字庫裡沒有同組其他字的也列出來，單字卡才看得到這個字是怎麼組成的（words 是空的）。"""
    if not is_english(vocab.category):
        return []
    words = course_words(student) if words is None else words
    status = _['status_of'](student.id) if status is None else status
    me = vocab.word.lower()
    result = []
    for fam in sorted(FAMILIES_OF_WORD.get(me, []), key=lambda f: KIND_ORDER[f["kind"]]):
        others = [v for v in family_rows(student, fam, words) if v.word.lower() != me]
        if fam["kind"] == 'suffix' and len(others) > BIG_SUFFIX:
            others = []   # -tion、-ly 這種幾百個字的大字尾，列出來沒有幫助：單字卡只顯示「字的組成」
        # 推薦順序：還沒學的、不熟的優先，熟的放後面
        rank = {'new': 0, 'unfamiliar': 1, 'familiar': 2}
        others.sort(key=lambda v: rank[status.get(v.id, 'new')])
        info = family_summary(student, fam, words, status)
        info["words"] = [word_item(student.id, v, status, fam["key"]) for v in others[:CARD_WORDS]]
        info["more"] = max(0, len(others) - CARD_WORDS)
        info["to_study"] = info["new"] + info["unfamiliar"]
        pool = all_english_words()
        stem = stem_of(fam, me, pool)
        info["stem"] = {"word": pool[stem].word, "meaning": pool[stem].meaning} if stem else None
        result.append(info)
        if len(result) >= CARD_FAMILIES:
            break
    return result


def is_big(info):
    """幾百個字的大字尾（-tion、-ly）：推薦整組背沒有意義，不推薦。"""
    return info["kind"] == 'suffix' and info["total"] > BIG_SUFFIX


def recommend_families(student, words=None, status=None, limit=None):
    """推薦接著背的組：學生已經學過其中幾個字、但還有沒學或不熟的字，學過越多的越前面。"""
    words = course_words(student) if words is None else words
    status = _['status_of'](student.id) if status is None else status
    picks = []
    for fam in FAMILIES:
        info = family_summary(student, fam, words, status)
        learned = info["familiar"] + info["unfamiliar"]
        todo = info["new"] + info["unfamiliar"]
        if info["total"] >= 2 and learned and todo and not is_big(info):
            picks.append((-learned, -info["total"], info))
    picks.sort(key=lambda t: (t[0], t[1]))
    picks = [p[2] for p in picks]
    return picks[:limit] if limit else picks


# ---------------------------------------------------------------------------
# 頁面
# ---------------------------------------------------------------------------

def _student_english(student_id):
    student = _['get_student'](student_id)
    if not is_english(_['exams'].course_of(student)):
        abort(404, description="字根字首只有英文的單字庫有")
    return student


@bp.route('/learn/<int:student_id>/roots')
def roots_home(student_id):
    """字根字首總覽：依字根、字首、字尾分組，最上面是推薦接著背的組。"""
    student = _student_english(student_id)
    words = course_words(student)
    status = _['status_of'](student_id)
    groups = {k: [] for k in KIND_ORDER}
    for fam in FAMILIES:
        info = family_summary(student, fam, words, status)
        if info["total"] >= 2:
            groups[fam["kind"]].append(info)
    sections = [{"kind": k, "name": KIND_NAMES[k], "fams": groups[k]} for k in KIND_ORDER if groups[k]]
    return render_template('roots_home.html', student=student, sections=sections,
                           recommend=recommend_families(student, words, status, limit=6),
                           total=sum(len(s["fams"]) for s in sections))


@bp.route('/learn/<int:student_id>/roots/<key>')
def family_page(student_id, key):
    student = _student_english(student_id)
    fam = FAMILY_BY_KEY.get(key) or abort(404, description="找不到這個字根")
    words = course_words(student)
    status = _['status_of'](student_id)
    info = family_summary(student, fam, words, status)
    cards = [word_item(student_id, v, status, key) for v in family_rows(student, fam, words)]
    if not cards:
        abort(404, description="目前的單字庫沒有這一組的字")
    return render_template('roots_family.html', student=student, fam=info, cards=cards,
                           batch=_['STUDY_BATCH_SIZE'])


@bp.route('/learn/<int:student_id>/roots/<key>/study')
def family_study(student_id, key):
    """整組一起滑卡：不熟的先出，再出還沒學的；熟的不出（跟主題滑卡一樣）。"""
    student = _student_english(student_id)
    fam = FAMILY_BY_KEY.get(key) or abort(404, description="找不到這個字根")
    status = _['status_of'](student_id)
    rows = family_rows(student, fam)
    picked = _['pick_swipe_words'](rows, status)
    fav = _['favorite_words'](student)
    label = f'{fam["kind_name"]} {fam["form"]}（{fam["meaning"]}）'
    words = [_['word_payload'](v, label, fav, status) for v in picked]
    back_url = url_for('word_roots.family_page', student_id=student_id, key=key)
    return render_template('ielts.html', words=words, student_id=student_id,
                           theme={"label": label}, mode='swipe', letter=None,
                           back_url=back_url, back_label='返回這組字',
                           again_url=url_for('word_roots.family_study', student_id=student_id, key=key),
                           home_url=url_for('learn_home', student_id=student_id))


@bp.route('/learn/<int:student_id>/roots/api/word/<int:vocab_id>')
def word_families(student_id, vocab_id):
    """單字卡用：這個字的同字根、同字首、同字尾字（英文以外回空清單）。"""
    student = _['get_student'](student_id)
    vocab = _['db'].session.get(_['Vocabulary'], vocab_id)
    if not vocab or vocab.category != _['exams'].course_of(student):
        return jsonify({"families": []})
    return jsonify({"families": families_for_word(student, vocab)})


@bp.route('/learn/<int:student_id>/roots/api/recommend', methods=['POST'])
def recommend_api(student_id):
    """滑完一輪：依剛滑過的字推薦整組接著背（剛滑過的字所屬的組優先）。"""
    from flask import request
    student = _['get_student'](student_id)
    if not is_english(_['exams'].course_of(student)):
        return jsonify({"families": []})
    ids = [i for i in (request.get_json(silent=True) or {}).get('vocab_ids', []) if isinstance(i, int)][:200]
    V = _['Vocabulary']
    words = course_words(student)
    status = _['status_of'](student_id)
    seen_keys, picks = set(), []
    for v in V.query.filter(V.id.in_(ids)).all() if ids else []:
        for fam in FAMILIES_OF_WORD.get(v.word.lower(), []):
            if fam["key"] in seen_keys:
                continue
            seen_keys.add(fam["key"])
            info = family_summary(student, fam, words, status)
            if info["total"] >= 2 and info["new"] + info["unfamiliar"] and not is_big(info):
                picks.append(info)
    picks.sort(key=lambda i: (KIND_ORDER[i["kind"]], -(i["new"] + i["unfamiliar"])))
    return jsonify({"families": picks[:RECOMMEND]})


def register(app, db, deps):
    """掛到主程式。deps 是 app.py 裡的模型與輔助函式。"""
    _.update(deps, db=db)
    app.register_blueprint(bp)

    @app.context_processor
    def _roots_helpers():
        # 樣板用：目前的考試是不是英文（只有英文顯示字根字首）
        return {"roots_enabled": lambda: is_english(_['exams'].current_exam()["course"])}
