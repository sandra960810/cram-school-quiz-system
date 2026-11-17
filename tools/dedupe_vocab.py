"""雅思字庫去重：同一個字在資料庫只留一筆，學生紀錄全部轉到留下的那筆。

run.bat 匯入單字之後會自動跑，可以重複執行（沒有重複字時什麼都不做）。

用法：
    python tools/dedupe_vocab.py            # 合併重複字
    python tools/dedupe_vocab.py --dry-run  # 只列出會合併哪些字，不寫入

規則：
- 只處理 COURSES 裡的課程（目前只有 IELTS），不同課程的同一個字不算重複
- 同拼字（不分大小寫、前後空白）的幾筆裡，留下內容最完整的一筆：
  有例句 > 有詞性 > 有中文意思，一樣完整就留編號最小的
- 被合併掉那筆的學習紀錄（熟／不熟）、收藏、單字測驗作答與題目、舊版錯題，
  全部改指到留下的那筆；兩筆都有紀錄時保留比較新的那筆紀錄
- REMOVED_WORDS 是確定要下架的錯誤資料（來源檔混進來的亂碼），連同它的學習紀錄一起刪掉
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text  # noqa: E402

from app import app, db  # noqa: E402

COURSES = ('IELTS',)
# 來源字典檔最後一行的越南文署名（「蒐集與整理」），不是英文單字
REMOVED_WORDS = {'IELTS': ['Sưu tầm & tổng hợp']}
NO_SENTENCE_PREFIX = '無例句'


def has_table(name):
    return db.session.execute(text("SELECT 1 FROM sqlite_master WHERE type='table' AND name=:n"),
                              {"n": name}).first() is not None


def richness(row):
    sentence = row.sentence or ''
    has_sentence = bool(sentence) and not sentence.startswith(NO_SENTENCE_PREFIX)
    has_zh = bool(row.meaning) and row.meaning != (row.meaning_en or '')
    return (has_sentence, bool(row.pos), has_zh, -row.id)


def move_rows(table, old_id, new_id, unique_cols=None, newer_col=None):
    """把 table 裡 vocab_id=old_id 的紀錄改指到 new_id。

    unique_cols：和 vocab_id 一起構成唯一鍵的欄位。新舊兩筆撞在一起時只留一筆
    （有 newer_col 就留比較新的，否則留原本就在 new_id 的那筆）。
    """
    if not has_table(table):
        return 0
    if not unique_cols:
        return db.session.execute(text(f"UPDATE {table} SET vocab_id=:new WHERE vocab_id=:old"),
                                  {"new": new_id, "old": old_id}).rowcount
    cols = ', '.join(unique_cols)
    moved = 0
    olds = db.session.execute(text(f"SELECT id, {cols}{', ' + newer_col if newer_col else ''} "
                                   f"FROM {table} WHERE vocab_id=:old"), {"old": old_id}).all()
    for o in olds:
        cond = ' AND '.join(f"{c}=:{c}" for c in unique_cols)
        params = {c: getattr(o, c) for c in unique_cols}
        params["new"] = new_id
        clash = db.session.execute(text(f"SELECT id{', ' + newer_col if newer_col else ''} FROM {table} "
                                        f"WHERE vocab_id=:new AND {cond}"), params).first()
        if clash is None:
            db.session.execute(text(f"UPDATE {table} SET vocab_id=:new WHERE id=:id"),
                               {"new": new_id, "id": o.id})
            moved += 1
            continue
        old_time = getattr(o, newer_col) if newer_col else None
        new_time = getattr(clash, newer_col) if newer_col else None
        if newer_col and old_time and (not new_time or str(old_time) > str(new_time)):
            # 舊那筆比較新：用它取代
            db.session.execute(text(f"DELETE FROM {table} WHERE id=:id"), {"id": clash.id})
            db.session.execute(text(f"UPDATE {table} SET vocab_id=:new WHERE id=:id"),
                               {"new": new_id, "id": o.id})
        else:
            db.session.execute(text(f"DELETE FROM {table} WHERE id=:id"), {"id": o.id})
        moved += 1
    return moved


def fix_quiz_questions(id_map):
    """單字測驗的題目存成 JSON，裡面的 vocab_id 也要改。"""
    if not has_table('vocab_quiz_attempt') or not id_map:
        return 0
    changed = 0
    for row in db.session.execute(text("SELECT id, questions FROM vocab_quiz_attempt "
                                       "WHERE questions IS NOT NULL")).all():
        try:
            qs = json.loads(row.questions)
        except ValueError:
            continue
        dirty = False
        for q in qs if isinstance(qs, list) else []:
            if isinstance(q, dict) and q.get('vocab_id') in id_map:
                q['vocab_id'] = id_map[q['vocab_id']]
                dirty = True
        if dirty:
            db.session.execute(text("UPDATE vocab_quiz_attempt SET questions=:q WHERE id=:id"),
                               {"q": json.dumps(qs, ensure_ascii=False), "id": row.id})
            changed += 1
    return changed


def run(dry_run=False):
    with app.app_context():
        id_map = {}
        for course in COURSES:
            rows = db.session.execute(text("SELECT id, word, pos, meaning, meaning_en, sentence "
                                           "FROM vocabulary WHERE category=:c"), {"c": course}).all()
            groups = {}
            for r in rows:
                groups.setdefault(r.word.strip().lower(), []).append(r)
            for word, group in groups.items():
                if len(group) < 2:
                    continue
                keep = max(group, key=richness)
                for r in group:
                    if r.id != keep.id:
                        id_map[r.id] = keep.id

        stats = {"progress": 0, "favorite": 0, "quiz_answer": 0, "exam": 0}
        for old_id, new_id in id_map.items():
            stats["progress"] += move_rows('learning_progress', old_id, new_id,
                                           ('student_id',), 'last_reviewed')
            stats["favorite"] += move_rows('favorite', old_id, new_id, ('student_id',), 'created_at')
            stats["quiz_answer"] += move_rows('vocab_quiz_answer', old_id, new_id)
            stats["exam"] += move_rows('exam_question', old_id, new_id)
            stats["exam"] += move_rows('exam_mistake', old_id, new_id,
                                       ('student_id', 'qtype'), 'last_wrong_at')
            db.session.execute(text("DELETE FROM vocabulary WHERE id=:id"), {"id": old_id})
        quizzes = fix_quiz_questions(id_map)

        removed = []
        for course, words in REMOVED_WORDS.items():
            for w in words:
                for r in db.session.execute(text("SELECT id FROM vocabulary WHERE category=:c AND word=:w"),
                                            {"c": course, "w": w}).all():
                    used = any(has_table(t) and db.session.execute(
                        text(f"SELECT 1 FROM {t} WHERE vocab_id=:id"), {"id": r.id}).first()
                        for t in ('vocab_quiz_answer', 'exam_question'))
                    if used:
                        print(f"⚠️  「{w}」有測驗作答紀錄，先不刪")
                        continue
                    for t in ('learning_progress', 'favorite', 'exam_mistake'):
                        if has_table(t):
                            db.session.execute(text(f"DELETE FROM {t} WHERE vocab_id=:id"), {"id": r.id})
                    db.session.execute(text("DELETE FROM vocabulary WHERE id=:id"), {"id": r.id})
                    removed.append(w)

        print(f"合併重複字 {len(id_map)} 筆（學習紀錄 {stats['progress']}、收藏 {stats['favorite']}、"
              f"測驗作答 {stats['quiz_answer']}、測驗題目 {quizzes} 份、舊版測驗 {stats['exam']}）；"
              f"下架錯誤資料 {len(removed)} 筆。")
        for course in COURSES:
            total, unique = db.session.execute(text(
                "SELECT COUNT(*), COUNT(DISTINCT LOWER(TRIM(word))) FROM vocabulary WHERE category=:c"),
                {"c": course}).one()
            print(f"{course}：共 {total} 筆、{unique} 個不重複單字")
        if dry_run:
            db.session.rollback()
            print('（--dry-run：沒有寫入資料庫）')
        else:
            db.session.commit()


if __name__ == '__main__':
    run(dry_run='--dry-run' in sys.argv)
