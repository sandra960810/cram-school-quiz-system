"""把 vocab_master.xlsx（單字總表）匯入資料庫。

用法：
    python import_sheet.py                 # 匯入 vocab_master.xlsx
    python import_sheet.py 其他檔案.xlsx    # 指定檔案（也可以是 UTF-8 的 .csv）
    python import_sheet.py --dry-run       # 只檢查、不寫入

規則：
- 有「編號」的列：更新資料庫裡那個字（可以改主題、拼字、意思…）
- 沒有編號的列：找同課程、同主題、同拼字的字更新；找不到就新增
- 不會刪除資料庫裡的字，也不會動學生的學習進度
- 匯入後，同一個字若出現在多個主題，學生學過的會兩邊同步解鎖
"""
import csv
import sys

from app import app, db, Vocabulary, LearningProgress, OFFICIAL_BY_ID, set_progress
from sqlalchemy import func

HEADERS = {
    '編號': 'id', '課程': 'category', '主題': 'theme', '程度': 'level', '單字': 'word',
    '詞性': 'pos', '中文意思': 'meaning_zh', '英文解釋': 'meaning_en',
    '例句': 'sentence', '例句中譯': 'sentence_zh',
}
LEVELS = {'基礎級', '中級', '中高級', '進階級', '不分級'}
SHEET_NAME = '單字總表'


def read_rows(path):
    if path.lower().endswith('.csv'):
        with open(path, encoding='utf-8-sig', newline='') as f:
            table = list(csv.reader(f))
    else:
        from openpyxl import load_workbook
        wb = load_workbook(path, read_only=True, data_only=True)
        ws = wb[SHEET_NAME] if SHEET_NAME in wb.sheetnames else wb.active
        table = [list(r) for r in ws.iter_rows(values_only=True)]
    if not table:
        return []
    keys = [HEADERS.get(str(h).strip() if h is not None else '', None) for h in table[0]]
    missing = {'theme', 'word'} - set(keys)
    if missing:
        sys.exit(f"找不到必要欄位：{', '.join(k for k, v in HEADERS.items() if v in missing)}")
    rows = []
    for line_no, values in enumerate(table[1:], start=2):
        row = {k: (str(v).strip() if v is not None else '') for k, v in zip(keys, values) if k}
        if any(row.values()):
            rows.append((line_no, row))
    return rows


def normalize_theme(value):
    """'02'、'02 環境' 都轉成官方名稱 '02 環境與自然生態'；其他名稱照原樣。"""
    code = value.split(' ', 1)[0]
    if code.isdigit() and code.zfill(2) in OFFICIAL_BY_ID:
        t = OFFICIAL_BY_ID[code.zfill(2)]
        return f"{t['id']} {t['name']}"
    return value


def run(path, dry_run=False):
    rows = read_rows(path)
    added = updated = unchanged = 0
    problems = []
    with app.app_context():
        by_id = {v.id: v for v in Vocabulary.query.all()}
        by_key = {(v.category, v.theme, v.word.lower()): v for v in by_id.values()}

        for line_no, r in rows:
            word = r.get('word', '')
            theme = normalize_theme(r.get('theme', ''))
            category = r.get('category') or 'IELTS'
            level = r.get('level') or '不分級'
            meaning_zh, meaning_en = r.get('meaning_zh', ''), r.get('meaning_en', '')
            if not word or not theme:
                problems.append(f"第 {line_no} 列：單字或主題是空的，略過")
                continue
            if not (meaning_zh or meaning_en):
                problems.append(f"第 {line_no} 列（{word}）：中文意思和英文解釋都是空的，略過")
                continue
            if level not in LEVELS:
                problems.append(f"第 {line_no} 列（{word}）：程度「{level}」不在清單內，改為「不分級」")
                level = '不分級'

            values = dict(category=category, theme=theme, level=level, word=word,
                          pos=r.get('pos') or None, meaning=meaning_zh or meaning_en,
                          meaning_en=meaning_en or None, sentence=r.get('sentence') or None,
                          sentence_zh=r.get('sentence_zh') or None)

            vocab = None
            raw_id = r.get('id', '')
            if raw_id:
                try:
                    vocab = by_id.get(int(float(raw_id)))
                except ValueError:
                    pass
                if vocab is None:
                    problems.append(f"第 {line_no} 列（{word}）：編號 {raw_id} 不存在，改用單字比對")
            if vocab is None:
                vocab = by_key.get((category, theme, word.lower()))

            if vocab is None:
                vocab = Vocabulary(**values)
                db.session.add(vocab)
                added += 1
            elif any(getattr(vocab, k) != v for k, v in values.items()):
                by_key.pop((vocab.category, vocab.theme, vocab.word.lower()), None)
                for k, v in values.items():
                    setattr(vocab, k, v)
                updated += 1
            else:
                unchanged += 1
            by_key[(category, theme, word.lower())] = vocab

        db.session.flush()

        # 同一個字在多個主題：學過的同步解鎖（例如學過 11 的 pollution，02 的 pollution 也算學過）
        synced = 0
        same_word = {}
        for v in Vocabulary.query.all():
            same_word.setdefault((v.category, v.word.lower()), set()).add(v.id)
        for rec in LearningProgress.query.filter_by(status='familiar').all():
            v = db.session.get(Vocabulary, rec.vocab_id)
            if not v:
                continue
            ids = same_word.get((v.category, v.word.lower()), set())
            have = {p.vocab_id for p in LearningProgress.query.filter(
                LearningProgress.student_id == rec.student_id,
                LearningProgress.vocab_id.in_(ids),
                LearningProgress.status == 'familiar')}
            if ids - have:
                set_progress(rec.student_id, v, 'familiar')
                synced += len(ids - have)
                db.session.flush()

        for p in problems:
            print('⚠️ ', p)
        print(f"讀取 {len(rows)} 列：新增 {added}、更新 {updated}、沒變動 {unchanged}；同步解鎖 {synced} 筆學習紀錄。")
        if dry_run:
            db.session.rollback()
            print('（--dry-run：沒有寫入資料庫）')
        else:
            db.session.commit()
            total = db.session.query(func.count(Vocabulary.id)).scalar()
            print(f"🎉 匯入完成，資料庫目前共有 {total} 個單字。")


if __name__ == '__main__':
    args = [a for a in sys.argv[1:] if a != '--dry-run']
    run(args[0] if args else 'vocab_master.xlsx', dry_run='--dry-run' in sys.argv)
