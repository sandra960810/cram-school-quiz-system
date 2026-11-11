import os
from app import app, db, Vocabulary, Student

def import_raw_txt_to_db(filepath):
    with app.app_context():
        # 1. 確保資料庫有我們的測試學生
        if not Student.query.filter_by(token="test_token_123").first():
            student1 = Student(token="test_token_123", name="王小明", enrolled_course="IELTS")
            db.session.add(student1)
            db.session.commit()

        print(f"開始解析並匯入 {filepath} 的單字庫...")
        added_count = 0
        
        # 2. 開啟並讀取這個非標準格式的檔案
        with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
            for line in f:
                line = line.strip()
                
                # 如果這行是空的，或是沒有包含冒號 ':' (例如標題 "A", "B")，就略過
                if not line or ':' not in line:
                    continue
                
                # 用冒號把字串切成兩半：前面是單字，後面是意思
                parts = line.split(':', 1)
                if len(parts) == 2:
                    word = parts[0].strip()
                    meaning = parts[1].strip()
                    
                    if word and meaning:
                        # 檢查單字是否已經在資料庫中
                        exists = Vocabulary.query.filter_by(word=word, category="IELTS").first()
                        if not exists:
                            new_word = Vocabulary(
                                category="IELTS", 
                                level="不分級", 
                                theme="11 雅思學術高頻字彙", # 預設分配一個新主題給這 4000 字
                                word=word, 
                                meaning=meaning, 
                                sentence="無例句 (由公開字典檔匯入)" # 因為來源沒有例句，所以給個預設值
                            )
                            db.session.add(new_word)
                            added_count += 1
                            
                            # 每處理 500 個字就寫入資料庫一次，避免記憶體爆炸
                            if added_count % 500 == 0:
                                db.session.commit()
                                print(f"進度報告：已成功匯入 {added_count} 個單字...")

        # 3. 把剩下的字也存進去
        db.session.commit()
        print(f"🎉 匯入大功告成！總共為資料庫新增了 {added_count} 個全新的雅思單字。")

if __name__ == '__main__':
    # 確認檔案名稱與你下載的一致
    import_raw_txt_to_db('ielts.csv')