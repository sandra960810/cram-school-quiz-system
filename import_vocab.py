from app import app, db, Vocabulary, Student

AWL_THEME = "11 雅思學術高頻字彙"


def parse_word_list(filepath):
    """解析「單字: 解釋」格式的字典檔。

    原始檔有些解釋太長會換到下一行（下一行沒有冒號），
    這些行要接回上一個單字的解釋，不然解釋會被截斷。
    """
    entries = []  # [(word, meaning)]
    with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
        for raw in f:
            line = raw.strip()
            if not line:
                continue
            if ':' in line:
                word, meaning = (p.strip() for p in line.split(':', 1))
                if word and meaning:
                    entries.append([word, meaning])
                continue
            # 沒有冒號：單一字母標題（A、B…）或檔頭直接略過，其餘是上一行解釋的延續
            if len(line) > 1 and entries and not line.isupper():
                entries[-1][1] = f"{entries[-1][1]} {line}"
    return [(w, m) for w, m in entries]


def import_raw_txt_to_db(filepath):
    with app.app_context():
        # 1. 確保資料庫有我們的測試學生
        if not Student.query.filter_by(token="test_token_123").first():
            db.session.add(Student(token="test_token_123", name="王小明", enrolled_course="IELTS"))
            db.session.commit()

        print(f"開始解析並匯入 {filepath} 的單字庫...")
        added_count = 0
        fixed_count = 0
        existing = {v.word: v for v in Vocabulary.query.filter_by(category="IELTS").all()}

        for word, meaning in parse_word_list(filepath):
            current = existing.get(word)
            if current:
                # 之前匯入時被截斷的解釋：用完整版本補上（只更新本字庫匯入的字）
                if current.theme == AWL_THEME and current.meaning != meaning \
                        and meaning.startswith(current.meaning):
                    current.meaning = meaning
                    fixed_count += 1
                continue

            new_word = Vocabulary(
                category="IELTS",
                level="不分級",
                theme=AWL_THEME,
                word=word,
                meaning=meaning,
                sentence="無例句 (由公開字典檔匯入)",  # 來源沒有例句，學習頁會自動隱藏例句區
            )
            db.session.add(new_word)
            existing[word] = new_word
            added_count += 1
            if added_count % 500 == 0:
                db.session.commit()
                print(f"進度報告：已成功匯入 {added_count} 個單字...")

        db.session.commit()
        print(f"🎉 匯入完成！新增 {added_count} 個單字，補齊 {fixed_count} 個被截斷的解釋。")


if __name__ == '__main__':
    import_raw_txt_to_db('ielts.csv')
