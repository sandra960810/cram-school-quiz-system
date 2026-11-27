"""趨勢補習班的公開官網（給 Google 搜尋得到的那一面）。

- 首頁 /、課程 /courses/<考試>、校區 /campus/<校區>、免費諮詢表單 /contact、迷你模考入口 /mock-test、個資說明 /privacy
- SEO：每頁的 title／description／canonical／Open Graph、JSON-LD 結構化資料、/sitemap.xml、/robots.txt
  學生的測驗系統（/dashboard、/learn…）一律加 X-Robots-Tag: noindex，不讓 Google 收錄學生頁面
- 補習班資料（電話、地址、LINE…）在 public_site/site_info.json，空白的欄位網頁顯示「待填」，結構化資料會略過
- 諮詢名單是個資：存在 instance/leads.db（獨立的檔案、不進 git，不和 quiz.db 放一起，因為 quiz.db 有進 git），
  只有工作人員登入後台才看得到（/admin/leads），可以匯出 Excel 用的 CSV
"""
import csv
import io
import json
import os
import re
import secrets
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

from flask import (Blueprint, Response, abort, redirect, render_template, request, session, url_for)

import admin

bp = Blueprint('site', __name__)
_ = {}

HERE = os.path.dirname(os.path.abspath(__file__))
INFO_PATH = os.path.join(HERE, 'public_site', 'site_info.json')
TW = timezone(timedelta(hours=8))

# 課程頁：只寫網站上真的有的東西，上課時間、師資、費用由 site_info.json 填
# points 是學員線上學習系統（單字學習、模擬考）在該科的功能。2026-11 使用者決定系統上線，官網要介紹：
# 各科專屬頁面與課程頁只列該科，主頁面列全部。只寫系統真的有的東西
COURSES = [
    {"key": "toeic", "name": "多益", "en": "TOEIC", "title": "多益補習班｜多益全方位課程",
     "lead": "從職場情境單字到聽力閱讀，一步步把多益分數往上拉。",
     "kw": ["多益補習班", "多益課程", "TOEIC 補習", "多益單字"],
     "sys": ["單字 5,005 字", "背單字神器 5 種題型", "AI 記憶法", "AI 錯題解釋"],
     "points": ["5,005 個多益職場單字，依主題分類，滑卡就能背",
                "「背單字神器」拼寫、聽寫、例句填空、選擇題輪流練",
                "答錯的字自動回到不熟區，下次優先複習"]},
    {"key": "ielts", "name": "雅思", "en": "IELTS", "title": "雅思補習班｜雅思全方位課程",
     "lead": "聽說讀寫四科完整備考，比照電腦考介面練習。",
     "kw": ["雅思補習班", "雅思課程", "IELTS 補習", "雅思口說", "雅思寫作"],
     "sys": ["單字 7,037 字", "聽說讀寫模考各 10 回", "AI 批改寫作", "AI 評分口說"],
     "points": ["7,037 個雅思不重複單字，分 14 個主題",
                "聽力、閱讀、寫作、口說各 10 回自製模擬題，比照電腦考版面",
                "寫作、口說有 AI 老師依官方標準評分（模擬，不等於真實考試）"]},
    {"key": "toefl", "name": "托福", "en": "TOEFL", "title": "托福補習班｜托福全方位課程",
     "lead": "托福全方位課程。",
     "kw": ["托福補習班", "托福課程", "TOEFL 補習"],
     "sys": [],
     "points": []},
    {"key": "jlpt", "name": "日檢", "form": "日文", "en": "JLPT", "title": "日文補習班｜日檢 N5～N1 課程",
     "lead": "從五十音到 N1，依等級學單字、做模擬考。",
     "kw": ["日文補習班", "日檢補習班", "JLPT", "日檢 N1", "日檢 N2", "日語課程"],
     "sys": ["單字 10,097 字", "N5～N1 模考各 10 回", "AI 錯題解釋", "AI 記憶法"],
     "points": ["N5～N1 分級單字共 10,097 字，附假名讀音與動詞變化",
                "日檢模擬考 N5～N1 各 10 回，交卷看正解、解析與估計分數",
                "羅馬拼音自動轉假名，沒有日文輸入法也能練打字"]},
    {"key": "topik", "name": "韓檢", "form": "韓文", "en": "TOPIK", "title": "韓文補習班｜韓檢 TOPIK 課程",
     "lead": "TOPIK I、II 一次準備，1～6 級分級學習。",
     "kw": ["韓文補習班", "韓檢補習班", "TOPIK", "韓語課程", "韓檢中級"],
     "sys": ["單字 6,630 字", "TOPIK I／II 模考各 10 回", "AI 批改寫作", "AI 錯題解釋"],
     "points": ["1～6 級分級單字共 6,630 字，韓語發音",
                "TOPIK I、TOPIK II 模擬考各 10 回，算總分與級數",
                "韓檢寫作有 AI 老師批改（模擬，不等於真實考試）"]},
    # 零基礎英文（2026-11 使用者要求「加入零基礎英文的區塊，算一個科目」）：系統裡的英文零基礎＋一般英文
    {"key": "basic", "name": "零基礎英文", "en": "BASIC", "title": "英文補習班｜零基礎英文課程",
     "hero": ["零基礎英文", "從發音開始學"],
     "lead": "英文從零開始：發音、KK 音標、生活單字，一步步把基礎打穩。",
     "kw": ["英文零基礎", "英文補習班", "英文發音", "KK 音標", "成人英文"],
     "sys": ["零基礎 2,006 字＋KK 音標", "一般英文 4,032 字", "AI 記憶法"],
     "points": ["英文零基礎 2,006 字，每個字有 KK 音標，可以正常速度或慢慢聽",
                "一般英文 4,032 個日常生活字，和零基礎不重複",
                "「背單字神器」拼寫、聽寫、例句填空、選擇題輪流練，答錯的字自動回到不熟區"]},
]
COURSE_MAP = {c['key']: c for c in COURSES}
# 為什麼選驅勢（2026-11 使用者提供補習班手冊「Trinity is the best choice」，說「這裡面的內容都可以用」）。
# (標題, 說明, 短說明)：主頁面「為什麼選驅勢」用說明，各科專屬頁面的學校介紹用短說明。只寫手冊上有的；使用者要求只放前六點，第七點是線上直播課（原本在「課程招生中」，該區塊使用者要求拿掉）
# 各科課程介紹（使用者提供的文案，照原文放；2026-11 使用者先給多益）。有的科目在各科頁面（?exam=）的「關於驅勢」右邊與下方顯示，
# 取代原本的照片課程卡。其他科目之後照同樣格式加
PROGRAMS = {
    "toeic": {
        "title": "多益 TOEIC 700-900 高分攻略",
        "tags": ["實體課", "線上直播", "專屬AI 學習系統"],
        "sub": "從英文基礎建立到多益高分，打造完整的多益學習計畫！",
        "intro": "驅勢英日韓結合專業師資、系統化教學、線上單字庫及 AI 多益模考系統，讓學員不只學會解題技巧，更能有效提升英文實力，朝多益 650、750、900 分的目標邁進！",
        "feat_title": "八大多益課程特色",
        "features": [
            ("完整分級教學，循序漸進提升實力", "依照學員的英文程度及目標分數，規劃適合的學習課程，從基礎文法、核心字彙到進階解題技巧，有系統地建立多益應考能力。", [], "layers"),
            ("專業多益師資，掌握高分解題技巧", "透過老師的專業教學，掌握常考題型、出題方向、關鍵字辨識及時間分配技巧，提升答題速度與正確率。", [], "teacher"),
            ("多益 Part 1～7 完整題型訓練", "全面強化聽力與閱讀能力，熟悉各類題型及解題策略。",
             [("Part 1", "照片描述"), ("Part 2", "應答問題"), ("Part 3", "簡短對話"), ("Part 4", "簡短獨白"),
              ("Part 5", "句子填空"), ("Part 6", "段落填空"), ("Part 7", "閱讀理解")], "clipboard"),
            ("多益核心 5,000 字彙，建立高分基礎", "結合商務、職場、旅遊、金融、行銷及日常生活等多益常考主題，補充高頻單字、同義詞、近義詞及常用搭配詞，提升字彙理解與應用能力。", [], "library"),
            ("多益必考文法與閱讀技巧", "系統化整理多益常考文法，包含詞性、時態、分詞、關係子句及各類句型，搭配長篇閱讀訓練，提升文章理解與快速解題能力。", [], "book-open"),
            ("AI 智慧多益模考系統", "結合線上模擬測驗與刷題練習，熟悉多益考試節奏，透過反覆練習掌握自身學習狀況，針對弱項加強訓練，讓每一次練習更有方向。", [], "bot"),
            ("線上英文單字庫，隨時隨地學習", "課堂學習搭配線上單字庫，善用通勤及零碎時間累積字彙量，讓課前預習、課後複習更有效率。", [], "swipe"),
            ("實體課程＋真人線上直播，彈性學習", "提供實體教室及真人線上直播課程，配合上班族與學生的生活時間，讓學習不受地點限制，兼顧工作、生活與英文進修。", [], "monitor"),
        ],
        "close_title": "不只是多益補習，更是完整的多益高分學習方案",
        "close_tags": ["英文實力提升", "多益核心題型解析", "專屬 AI 智慧學習系統"],
        "close": ["從課堂上的英文實力養成、多益核心題型解析與高分解題技巧，到課後自主複習、AI 智慧刷題及考前實戰模擬，打造完整且系統化的學習計畫。",
                  "不只掌握多益應試技巧，更能全面提升英文實力，讓每一次學習都有效累積，穩步邁向多益高分目標！"],
    },
    # 雅思：2026-11 使用者提供的課程文案，照原文放（不要改寫）
    "ielts": {
        "title": "雅思 IELTS 課程｜邁向雅思6.5-8分",
        "tags": ["全面英文實力提升", "雅思核心題型解析", "專屬 AI 智慧學習系統"],
        "tag_sep": "×",
        "sub": "",
        "intro": "無論是出國留學、海外工作、移民申請，或提升國際英語競爭力，驅勢英日韓結合專業師資、系統化教學、AI 智慧學習系統及知識背景單字庫，全面強化聽、說、讀、寫四大能力，協助學員朝 IELTS 6.5-8分的目標邁進！",
        "feat_title": "八大雅思課程特色",
        "features": [
            {"t": "完整分級教學，建立英文核心實力", "icon": "layers",
             "d": ["依照學員的英文程度及目標分數，規劃適合的學習方向，從初階~高階文法、核心字彙、從日常生活到高階知識背景英文，循序漸進提升語言實力。"]},
            {"t": "專業雅思師資，掌握高分應試技巧", "icon": "teacher",
             "d": ["深入解析雅思核心題型、評分標準及常見失分原因，透過系統化教學，掌握答題策略、時間分配及高分解題技巧。"]},
            {"t": "雅思聽說讀寫四大能力訓練", "icon": "clipboard", "wide": True, "list": True,
             "parts": [("Listening 聽力", "強化關鍵字辨識、同義詞轉換、不同口音理解及聽力解題技巧。"),
                       ("Speaking 口說", "針對 Part 1～3 進行主題式口說訓練，提升流暢度、邏輯表達、字彙運用及發音能力。"),
                       ("Reading 閱讀", "掌握文章架構、快速定位、長篇閱讀理解及各類題型解題技巧。"),
                       ("Writing 寫作", "針對 Academic Task 1 圖表分析及 Task 2 議論文寫作，強化文章架構、論點發展及進階句型應用。")]},
            {"t": "專屬 AI 智慧學習系統", "icon": "bot", "wide": True, "list": True,
             "d": ["突破傳統課堂學習限制，結合 AI 科技與自主學習，讓學員在課後也能持續強化英文實力。"],
             "parts": [("AI 聽寫訓練", "透過單字、句型及聽寫題練習，強化聽力辨識、拼字正確率及語音理解能力。"),
                       ("AI 口說練習", "結合雅思常考主題，反覆練習英文口說，提升表達流暢度及語言組織能力。"),
                       ("AI 寫作練習", "透過主題式寫作訓練，加強文法、字彙運用、文章架構及邏輯表達能力。")],
             "after": ["讓學習不再受限於課堂時間，隨時隨地練習，持續累積英文實力。"]},
            {"t": "雅思知識背景單字庫", "icon": "library",
             "d": ["系統化整理雅思及學術英文常見主題字彙，涵蓋教育、科技、人工智慧、環境、能源、醫療健康、經濟、文化、心理學、社會議題及全球化等領域。",
                   "結合高頻字彙、同義詞、近義詞、學術用語及主題背景知識，不只是背單字，更能理解單字在不同情境中的實際應用，全面提升閱讀、口說及寫作能力。"]},
            {"t": "主題式教學，建立國際視野", "icon": "globe",
             "d": ["透過新聞閱讀、國際時事及學術議題討論，累積多元知識背景，培養獨立思考、議題分析及邏輯表達能力，讓雅思口說更有內容、寫作更有深度。"]},
            {"t": "口說與寫作實戰訓練", "icon": "mic",
             "d": ["結合專業教師指導與 AI 自主練習，透過主題式口說、寫作架構分析及實戰演練，改善文法錯誤、字彙運用及表達方式，逐步提升口說與寫作表現。"]},
            {"t": "實體課程×真人線上直播×專屬AI 智慧學習", "icon": "monitor", "full": True,
             "d": ["提供實體教室與真人線上直播課程，搭配專屬 AI 智慧學習系統及線上知識背景單字庫，打造不受時間與地點限制的多元學習環境。"]},
        ],
        "close_title": "不只是雅思補習，更是完整的國際英語學習方案",
        "close_tags": ["專業師資授課", "雅思核心題型解析", "專屬AI 智慧學習", "知識背景單字庫"],
        "close": [
            "從課堂上的英文實力養成、學術英文應用及雅思核心題型解析，到課後 AI 聽寫、口說、寫作練習與考前實戰演練，建立完整且系統化的學習循環。",
            "不只掌握雅思高分應試技巧，更能全面提升英文實力、累積國際知識背景，讓英文成為未來海外留學、國際職涯及跨文化溝通的重要競爭力！",
        ],
    },
}
# 特色卡統一成 dict：t 標題、d 段落（list）、parts 小項目、icon 圖示、after 小項目後面的段落、wide 佔兩列、list 小項目排成條列
for _pg in PROGRAMS.values():
    _pg["features"] = [f if isinstance(f, dict) else {"t": f[0], "d": [f[1]], "parts": f[2], "icon": f[3], "wide": bool(f[2])}
                       for f in _pg["features"]]

# 學習系統的實際畫面（2026-11 使用者要求「介紹學習系統的地方要放系統預覽圖」）：用示範帳號從系統本身截圖，
# 圖在 static/images/site/system/。kind：phone 手機畫面、desk 電腦畫面；exams：哪些科目的頁面顯示（主頁面全部顯示）
SYSTEM_SHOTS = [
    # 每一科放自己那一科的系統畫面（2026-11 使用者要求「每一科的預覽圖都要不一樣、要符合系統」）；
    # exams 是要出現在哪些頁面，main＝主頁面（沒帶 ?exam=），主頁面每科挑一張
    {"file": "toeic-learn.webp", "kind": "phone", "title": "單字庫", "sub": "多益 5,005 字滑卡", "exams": {"toeic", "main"}},
    {"file": "toeic-quiz.webp", "kind": "phone", "title": "背單字神器", "sub": "闖關測驗", "exams": {"toeic"}},
    {"file": "toeic-theme.webp", "kind": "phone", "title": "主題圖鑑", "sub": "熟／不熟分區", "exams": {"toeic"}},
    {"file": "toeic-roots.webp", "kind": "desk", "title": "字根字首", "sub": "一次記住一整組字", "exams": {"toeic"}},
    {"file": "ielts-learn.webp", "kind": "phone", "title": "單字庫", "sub": "雅思 7,037 字滑卡", "exams": {"ielts"}},
    {"file": "ielts-quiz.webp", "kind": "phone", "title": "背單字神器", "sub": "闖關測驗", "exams": {"ielts"}},
    {"file": "ielts-theme.webp", "kind": "phone", "title": "主題圖鑑", "sub": "熟／不熟分區", "exams": {"ielts"}},
    {"file": "ielts-reading.webp", "kind": "desk", "title": "雅思閱讀模考", "sub": "比照電腦考介面", "exams": {"ielts", "main"}},
    {"file": "ielts-writing.webp", "kind": "desk", "title": "雅思寫作模考", "sub": "交卷後 AI 老師批改", "exams": {"ielts"}},
    {"file": "jlpt-learn.webp", "kind": "phone", "title": "單字庫", "sub": "N5～N1 讀音＋發音", "exams": {"jlpt", "main"}},
    {"file": "jlpt-quiz.webp", "kind": "phone", "title": "背單字神器", "sub": "羅馬拼音打假名", "exams": {"jlpt"}},
    {"file": "jlpt-theme.webp", "kind": "phone", "title": "等級圖鑑", "sub": "依五十音分頁", "exams": {"jlpt"}},
    {"file": "jlpt-mock.webp", "kind": "desk", "title": "日檢模擬考", "sub": "N5～N1 各 10 回", "exams": {"jlpt"}},
    {"file": "jlpt-mock2.webp", "kind": "desk", "title": "文法・讀解", "sub": "交卷看正解與解析", "exams": {"jlpt"}},
    {"file": "topik-learn.webp", "kind": "phone", "title": "單字庫", "sub": "1～6 級韓語發音", "exams": {"topik"}},
    {"file": "topik-quiz.webp", "kind": "phone", "title": "背單字神器", "sub": "闖關測驗", "exams": {"topik"}},
    {"file": "topik-theme.webp", "kind": "phone", "title": "等級圖鑑", "sub": "依子音分頁", "exams": {"topik"}},
    {"file": "topik-reading.webp", "kind": "desk", "title": "韓檢模擬考", "sub": "TOPIK I／II 各 10 回", "exams": {"topik"}},
    {"file": "topik-writing.webp", "kind": "desk", "title": "TOPIK II 寫作", "sub": "韓文鍵盤＋AI 批改", "exams": {"topik", "main"}},
    {"file": "basic-phonics.webp", "kind": "phone", "title": "學發音", "sub": "KK 音標＋慢慢聽", "exams": {"basic", "main"}},
    {"file": "basic-learn.webp", "kind": "phone", "title": "單字庫", "sub": "國中小程度單字", "exams": {"basic"}},
    {"file": "basic-quiz.webp", "kind": "phone", "title": "背單字神器", "sub": "闖關測驗", "exams": {"basic"}},
    {"file": "basic-theme.webp", "kind": "phone", "title": "主題圖鑑", "sub": "熟／不熟分區", "exams": {"basic"}},
]

# （標題, 說明, 短說明, 圖示）圖示是 static/icons.svg 的名稱；各科頁面的學校介紹橫排、每點前面配小圖（2026-11 使用者要求）
WHY = [
    ("學員權益履約保證", "與遠東、永豐銀行簽訂 1,600 萬學員權益履約保證，讓學員更安心。", "與遠東、永豐銀行簽訂 1,600 萬履約保證", "shield"),
    ("專業面談程度分級", "除了電腦與紙筆測驗，每個課程都有專業面談，評估口說、字彙與句型，確實分級，不浪費時間與金錢。", "測驗加專業面談，確實分級", "layers"),
    ("學員導向排課系統", "線上排課系統，在家就能選課排課；教師評比與意見反應功能，和學員一起把關教學品質。", "在家就能線上選課、排課", "calendar"),
    ("專業師資精緻教學", "專任教師團隊全時間專注於教學準備與課程研發。", "專任教師專注教學與課程研發", "teacher"),
    ("循環開課多元課程", "每週超過 100 堂全外語聽說讀寫課程，持續循環開課，隨時都有新班。", "每週超過 100 堂，隨時有新班", "refresh"),
    ("口說課程絕對小班", "認證與實力養成的口說班堅持小班制，互動最充分、練習最有效。", "口說班堅持小班制", "users"),
    ("實體課＋線上直播課", "除了面對面授課、即時提問互動，也有線上直播課，即時互動、彈性上課不受地點限制。", "實體課＋線上直播，上課不受地點限制", "monitor"),
]
# 程度分級制度（2026-11 使用者提供補習班手冊「TRINITY 專業程度分級制度」，要求放在主頁面）。依 CEFR 分 6 級；只寫手冊上有的
CEFR_LEVELS = [
    (1, "Fundamental", "基礎", "A1", ["自然發音", "實用生活字彙"]),
    (2, "Basic 1", "初級", "A2", ["實用生活字彙", "生活會話", "旅遊會話", "初級文法"]),
    (3, "Basic 2", "初中級", "B1", ["字彙倍增法", "生活會話", "旅遊會話", "片語會話", "主題式閱讀", "初中級文法"]),
    (4, "Intermediate 1", "中級", "B2", ["字彙倍增法", "Movie", "新聞會話", "國際新聞閱讀", "主題式討論", "寫作", "學術英文（托福／雅思先修班）", "中級文法"]),
    (5, "Intermediate 2", "中高級", "C1", ["學術英文（托福／雅思先修班）", "主題式討論", "主題式閱讀", "Movie English（影音英文）", "商用英文", "高階文法"]),
    (6, "Advanced", "高級", "C2", ["TED Talks（影音英文）", "CNN／BBC 新聞時事", "主題式討論", "主題式閱讀", "高階會話", "英文雜誌"]),
]
# 各檢定對照：四個分數依序對齊 B1、B2、C1、C2（第 3～6 級）
CEFR_EXAMS = [
    ("全民英檢 GEPT", ["初級", "中級", "中高級", "高級"]),
    ("多益 TOEIC", ["550 以上", "650 以上", "750 以上", "850 以上"]),
    ("雅思 IELTS", ["4 以上", "4.5～5 以上", "5.5～6 以上", "7 以上"]),
    ("托福 TOEFL-iBT", ["38 以上", "61 以上", "71 以上", "100 以上"]),
]
# 各科專屬頁面的 CEFR 對照（2026-11 使用者要求「每一科要放每科的 CEFR」）：A1～C2 六格，沒有對照的留空。
# 多益、雅思、托福照補習班手冊「TRINITY 專業程度分級制度」；日檢照日本語能力試驗官方公告：
# 2025 年 12 月起合格者的成績單附 CEFR 參考等級（jpf.go.jp 2026-01 公告，依總分）。韓檢官方沒有公布 CEFR 對照，不放
CEFR_BY_EXAM = {
    "toeic": {"cells": ["", "", "550 以上", "650 以上", "750 以上", "850 以上"], "src": "依驅勢程度分級制度（補習班手冊）"},
    "ielts": {"cells": ["", "", "4 以上", "4.5～5 以上", "5.5～6 以上", "7 以上"], "src": "依驅勢程度分級制度（補習班手冊）"},
    "toefl": {"cells": ["", "", "38 以上", "61 以上", "71 以上", "100 以上"], "src": "依驅勢程度分級制度（補習班手冊）"},
    "basic": {"cells": ["LEVEL 1 基礎\n自然發音・生活字彙", "LEVEL 2 初級\n生活會話・初級文法", "", "", "", ""],
              "src": "依驅勢程度分級制度（補習班手冊）：零基礎從 LEVEL 1 開始"},
    "jlpt": {"cells": ["N5 合格", "N4 合格\nN3 95～103 分", "N3 104 分以上\nN2 90～111 分", "N2 112 分以上\nN1 100～141 分", "N1 142 分以上", ""],
             "src": "日本語能力試驗官方：2025 年 12 月起，合格者的成績單依總分附上 CEFR 參考等級"},
}
# 學員線上學習系統的 AI 功能（ai_tutor.py 真的有的才寫；2026-11 使用者要求系統介紹簡潔、強調 AI）。
# 各科的 sys 是短標籤，「AI」開頭的標籤會標成霧藍色
# 學員線上學習系統的功能（2026-11 使用者要求「每個功能都要寫清楚、排版要融合」）。只寫系統真的有的功能。
# exams：哪些科目有這個功能（basic＝英文基礎）；detail：各科專屬頁面改用的說明（沒寫就用 text）
ALL_SYS = {"toeic", "ielts", "jlpt", "topik", "basic"}
SYSTEM_FEATURES = [
    {"title": "單字庫", "ai": False, "exams": ALL_SYS,
     "text": "依主題分類，像滑卡一樣背：右滑熟、左滑不熟，自動分成熟／不熟兩區，可以收藏、跨主題搜尋。多益 5,005、雅思 7,037、日檢 10,097、韓檢 6,630 字。",
     "detail": {"toeic": "5,005 個多益職場單字依主題分類，像滑卡一樣背：右滑熟、左滑不熟，自動分成熟／不熟兩區，可以收藏、跨主題搜尋。",
                "ielts": "7,037 個雅思不重複單字分 14 個主題，像滑卡一樣背：右滑熟、左滑不熟，自動分成熟／不熟兩區，可以收藏、跨主題搜尋。",
                "jlpt": "N5～N1 分級共 10,097 字，附假名讀音與動詞變化，點一下就唸；右滑熟、左滑不熟，平假名、片假名、羅馬拼音都搜得到。",
                "topik": "1～6 級分級共 6,630 字，韓語發音、附漢字；右滑熟、左滑不熟，自動分成熟／不熟兩區，可以收藏、搜尋。",
                "basic": "英文零基礎 2,006 字、一般英文 4,032 個日常生活字，右滑熟、左滑不熟，自動分成熟／不熟兩區。"}},
    {"title": "字根字首", "ai": False, "exams": {"toeic", "ielts", "basic"},
     "text": "英文單字拆成字首、字根、字尾，看懂一個字就認得同家族的字，系統還會推薦整組一起背。"},
    {"title": "背單字神器", "ai": False, "exams": ALL_SYS,
     "text": "只考學過的字，不熟的優先：拼寫、聽寫、例句填空、選意思、選單字五種題型輪流考，答錯的字自動回到不熟區。",
     "detail": {"jlpt": "只考學過的字，不熟的優先：拼寫、聽寫、例句填空、選擇題輪流考，漢字或假名都算對；沒有日文輸入法也能用羅馬拼音打。",
                "topik": "只考學過的字，不熟的優先：拼寫、聽寫、例句填空、選擇題輪流考，螢幕上有韓文鍵盤，答錯的字自動回到不熟區。"}},
    {"title": "線上模擬考", "ai": False, "exams": {"ielts", "jlpt", "topik"},
     "text": "雅思聽說讀寫各 10 回、日檢 N5～N1 各 10 回、韓檢 TOPIK I／II 各 10 回，題目原創，交卷看正解、中文解析與估計分數。",
     "detail": {"ielts": "聽力、閱讀、寫作、口說各 10 回原創題，比照雅思電腦考版面；交卷看正解與中文解析，錯題自動收進錯題本。",
                "jlpt": "N5～N1 各 10 回原創模考，題型比照正式考試；交卷看正解、中文解析、聽解台詞，算出 180 分制估計分數。",
                "topik": "TOPIK I、TOPIK II 各 10 回原創模考，題型、配分比照正式考試；交卷看正解、中文解析、聽力原文，算總分與級數。"}},
    {"title": "學發音", "ai": False, "exams": {"basic"},
     "text": "每個字有 KK 音標，可以正常速度或慢慢聽；也有 -tion、-ed、-ture 等常見字尾的念法。"},
    {"title": "AI 錯題解釋", "ai": True, "viz": "explain", "exams": ALL_SYS,
     "text": "答錯的題目按「問 AI 老師」，說明為什麼錯、正解的根據、陷阱在哪、下次怎麼判斷，再出一題類似的題目讓你馬上練。"},
    {"title": "AI 弱點練習", "ai": True, "viz": "practice", "exams": ALL_SYS,
     "text": "系統統計你各題型的錯誤率、錯題和不熟的字，AI 針對最弱的地方出 8 題練習，交卷馬上批改。"},
    {"title": "AI 寫作批改", "ai": True, "viz": "writing", "exams": {"ielts", "topik"},
     "text": "雅思寫作依官方四項標準給 Band 分數與修改建議；韓檢寫作四題一次批改、給分數與建議。",
     "detail": {"ielts": "Task 1、Task 2 交卷後，AI 老師依官方四項標準給 Band 分數，指出問題並給修改建議。",
                "topik": "TOPIK II 寫作四題交卷後一次批改，AI 老師給分數、指出問題並給修改建議。"}},
    {"title": "AI 口說評分", "ai": True, "viz": "speaking", "exams": {"ielts"},
     "text": "比照考官流程 Part 1～3 錄音作答，AI 老師依流暢度、字彙、文法、發音四項標準評分並給建議。"},
    {"title": "AI 學習報告", "ai": True, "viz": "report", "exams": ALL_SYS,
     "text": "把學習紀錄整理成報告：強項、弱項、兩週讀書計畫和給家長的話，可以列印成 PDF。"},
    {"title": "AI 單字記憶法", "ai": True, "viz": "memory", "exams": ALL_SYS,
     "text": "單字卡上按一下，AI 給你口訣、字根拆解、更多例句、常用搭配和容易混淆的字。"},
]
# 迷你模考：多益、雅思、日檢、韓檢（日檢、韓檢不分級，測完給預估級數）
MOCKS = [("toeic", "多益"), ("ielts", "雅思"), ("jlpt", "日檢"), ("topik", "韓檢")]
MOCKS_READY = {"toeic", "ielts", "jlpt", "topik"}   # 已經有題目的迷你模考（school_mock.py、public_site/mock/<考試>.json）
MOCK_BLURB = {"toeic": "聽力＋閱讀 22 題，約 12 分鐘，留資料看預估分數",
              "ielts": "聽力＋閱讀 20 題，約 15 分鐘，留資料看預估 Band",
              "jlpt": "不用選級數，N5～N1 共 25 題，留資料看預估級數",
              "topik": "不用選級數，1～6 級共 24 題，留資料看預估級數"}
IDENTITIES = ['學生', '上班族', '家長（幫孩子詢問）', '其他']
CONTACT_TIMES = ['都可以', '平日白天', '平日晚上', '週末']
PUBLIC_PREFIXES = ('/courses', '/campus', '/contact', '/mock-test', '/privacy', '/thanks')


# ---------------------------------------------------------------------------
# 補習班資料
# ---------------------------------------------------------------------------

def info():
    try:
        with open(INFO_PATH, encoding='utf-8') as f:
            data = json.load(f)
    except (OSError, ValueError):
        data = {}
    data.setdefault('name', '趨勢補習班')
    data.setdefault('campuses', [])
    data.setdefault('courses', {})
    for c in data['campuses']:
        c.setdefault('label', c.get('name', '') + '校')
        if not c.get('map_url') and c.get('address'):
            c['map_url'] = 'https://www.google.com/maps/search/?api=1&query=' + quote(f"{data['name']} {c['address']}")
    return data


def campus_of(slug):
    return next((c for c in info()['campuses'] if c.get('slug') == slug), None)


def base_url():
    """正式網址（site_info.json 的 site_url）；還沒有就用目前連進來的網址。"""
    url = (info().get('site_url') or '').strip().rstrip('/')
    return url or request.url_root.rstrip('/')


def abs_url(endpoint, **kw):
    return base_url() + url_for(endpoint, **kw)


def org_jsonld():
    d = info()
    org = {"@context": "https://schema.org", "@type": "EducationalOrganization",
           "name": d['name'], "url": base_url() + '/'}
    alt = [x for x in [d.get('name_en')] + d.get('alt_names', []) if x]
    if alt:
        org['alternateName'] = alt
    for k_src, k_out in ( ('phone', 'telephone'), ('email', 'email'),
                         ('intro', 'description'), ('founded', 'foundingDate')):
        if d.get(k_src):
            org[k_out] = d[k_src]
    if d.get('logo'):
        org['logo'] = base_url() + url_for('static', filename=d['logo'])
    same = [d[k] for k in ('line_url', 'facebook_url', 'instagram_url') if d.get(k)]
    if same:
        org['sameAs'] = same
    deps = [campus_jsonld(c, nested=True) for c in d['campuses']]
    if deps:
        org['department'] = deps
    return org


def campus_jsonld(c, nested=False):
    d = info()
    out = {"@type": "EducationalOrganization", "name": f"{d['name']} {c['label']}",
           "url": abs_url('site.campus', slug=c['slug'])}
    if not nested:
        out["@context"] = "https://schema.org"
    addr = {"@type": "PostalAddress", "addressCountry": "TW", "addressRegion": c.get('city', '')}
    if c.get('address'):
        addr['streetAddress'] = c['address']
    out['address'] = addr
    if c.get('phone') or d.get('phone'):
        out['telephone'] = c.get('phone') or d.get('phone')
    if c.get('map_url'):
        out['hasMap'] = c['map_url']
    return out


def breadcrumb(*items):
    """items：(名稱, 網址)…，首頁會自動加在最前面。"""
    items = (('首頁', base_url() + '/'),) + items
    return {"@context": "https://schema.org", "@type": "BreadcrumbList",
            "itemListElement": [{"@type": "ListItem", "position": i + 1, "name": n, "item": u}
                                for i, (n, u) in enumerate(items)]}


def page(template, *, title, description, keywords=(), jsonld=(), **kw):
    d = info()
    full_title = title if d['name'] in title else f"{title}｜{d['name']}"
    return render_template(template, s=d, courses=COURSES, mocks=MOCKS, mocks_ready=MOCKS_READY, system_features=SYSTEM_FEATURES, system_shots=SYSTEM_SHOTS, cefr_by_exam=CEFR_BY_EXAM, why=WHY, programs=PROGRAMS, cefr_levels=CEFR_LEVELS, cefr_exams=CEFR_EXAMS, mock_blurb=MOCK_BLURB, page_title=full_title,
                           description=description, keywords=', '.join(keywords),
                           canonical=base_url() + request.path,
                           jsonld=[json.dumps(j, ensure_ascii=False).replace('<', '\\u003c') for j in jsonld], **kw)


# ---------------------------------------------------------------------------
# 公開頁面
# ---------------------------------------------------------------------------

@bp.route('/')
def home():
    # 2026-11 使用者要求：官網（含校區）不連到學生系統，已登入的學生也照樣看官網
    d = info()
    towns = '、'.join(c['name'] for c in d['campuses'])
    if not session.get('site_csrf'):          # 首頁主視覺下面直接有諮詢表單（送到 /contact），和諮詢頁共用同一個 csrf
        session['site_csrf'] = secrets.token_hex(16)
    hero = hero_course()
    return page('site/home.html', csrf=session['site_csrf'],
                title=f"{d['name']}｜{towns}多益、雅思、托福、日文、韓文補習班",
                description=f"{d['name']}在{towns}設有校區，提供多益、雅思、托福、日檢、韓檢課程，"
                            f"專屬學習規劃、免費多益程度測驗。免費諮詢、加 LINE 了解課程。",
                keywords=[f"{c['name']}{k}" for c in d['campuses'][:5] for k in ('補習班', '多益補習班', '英文補習班')]
                         + ['多益補習班', '雅思補習班', '日文補習班', '韓文補習班', '托福補習班'],
                jsonld=[org_jsonld()], hero=hero, reviews=reviews_for(d, hero['c']['key']))


def reviews_for(d, key, n=9):
    """學員心得（2026-11 使用者要求：廣告進來的首頁，學校與課程介紹下面放學員心得）。
    資料在 site_info.json 的 testimonials，只放補習班提供的真實心得，不要自己編；
    同一個考試的心得排前面，最多 n 則（2026-11 使用者要求每科 9 則，一次看 3 則、左右滑）。沒有資料時樣板顯示「待填」。"""
    rows = [t for t in d.get('testimonials') or [] if isinstance(t, dict) and (t.get('text') or '').strip()]
    rows.sort(key=lambda t: t.get('course') != key)
    for t in rows:
        c = COURSE_MAP.get(t.get('course') or '')
        t['course_name'] = c['name'] if c else ''
    return rows[:n]


def hero_course():
    """首頁最上面顯示哪個考試（2026-11 使用者要求：之後下廣告，從多益廣告點進來最上面就是多益，以此類推）。
    廣告連結加 ?exam=ielts（或 toeic、toefl、jlpt、topik、basic），也認 utm_content／utm_campaign 等於考試代號；
    沒帶或看不懂就是多益、沒有下面的學校與課程介紹、學員心得。網址參數不影響 canonical，搜尋引擎只看到一個首頁。"""
    for k in ('exam', 'utm_content', 'utm_campaign'):
        key = (request.args.get(k) or '').strip().lower()
        if key in COURSE_MAP:
            return {'c': COURSE_MAP[key], 'ad': True}
    return {'c': COURSE_MAP['toeic'], 'ad': False}


@bp.route('/courses')
def courses():
    return page('site/courses.html', title='課程介紹｜多益、雅思、托福、日檢、韓檢、零基礎英文',
                description=f"{info()['name']}的語言課程：多益、雅思、托福、日檢 N5～N1、韓檢 TOPIK，以及零基礎英文。",
                keywords=[k for c in COURSES for k in c['kw'][:2]],
                jsonld=[breadcrumb(('課程介紹', abs_url('site.courses')))])


@bp.route('/courses/<key>')
def course(key):
    c = COURSE_MAP.get(key)
    if not c:
        abort(404)
    d = info()
    towns = '、'.join(x['name'] for x in d['campuses'])
    extra = d['courses'].get(key, {})
    ld = {"@context": "https://schema.org", "@type": "Course", "name": f"{c['name']}（{c['en']}）課程",
          "description": c['lead'], "inLanguage": "zh-TW",
          "provider": {"@type": "EducationalOrganization", "name": d['name'], "url": base_url() + '/'}}
    return page('site/course.html', title=f"{towns.split('、')[0] if towns else ''}{c['title']}",
                description=f"{d['name']}{c['name']}課程：{c['lead']}{towns}校區開課，免費諮詢。",
                keywords=c['kw'] + [f"{x['name']}{c['kw'][0]}" for x in d['campuses']],
                jsonld=[ld, breadcrumb(('課程介紹', abs_url('site.courses')),
                                       (c['name'], abs_url('site.course', key=key)))],
                c=c, extra=extra)


@bp.route('/campus/<slug>')
def campus(slug):
    c = campus_of(slug)
    if not c:
        abort(404)
    d = info()
    return page('site/campus.html', title=f"{c['name']}補習班｜{d['name']} {c['label']}",
                description=f"{d['name']} {c['label']}：{c['name']}多益、雅思、托福、日文、韓文補習班。"
                            f"地址、電話、上課時間與免費諮詢。",
                keywords=[f"{c['name']}{k}" for k in ('補習班', '多益補習班', '雅思補習班', '日文補習班',
                                                     '韓文補習班', '英文補習班')],
                jsonld=[campus_jsonld(c), breadcrumb((c['label'], abs_url('site.campus', slug=slug)))],
                c=c)


@bp.route('/mock-test')
def mock_test():
    return page('site/mock.html', title='免費迷你模考｜多益、雅思、日檢、韓檢 10 分鐘測程度',
                description='10 分鐘迷你模考，測出多益、雅思、日檢、韓檢的程度，拿到分數、錯題與弱點分析報告。',
                keywords=['多益模擬考', '雅思模擬考', '日檢模擬考', '韓檢模擬考', '免費程度測驗'],
                jsonld=[breadcrumb(('免費迷你模考', abs_url('site.mock_test')))])


@bp.route('/privacy')
def privacy():
    return page('site/privacy.html', title='個人資料蒐集說明',
                description=f"{info()['name']}蒐集、使用與保護個人資料的說明。")


@bp.route('/contact', methods=['GET', 'POST'])
def contact():
    d = info()
    values, errors = {'courses': [request.args.get('course', '')], 'campus': request.args.get('campus', '')}, []
    if request.method == 'POST':
        if request.form.get('csrf') != session.get('site_csrf'):
            errors.append('表單已過期，請重新整理頁面再送出一次')
        elif request.form.get('website'):          # 機器人才會填的隱藏欄位：假裝成功，什麼都不存
            return redirect(url_for('site.thanks'))
        else:
            values, errors = validate(request.form, d)
            if not errors and too_many(client_ip()):
                errors.append('送出太多次了，請稍後再試，或直接加 LINE 聯絡我們')
            if not errors:
                save_lead(values)
                return redirect(url_for('site.thanks'))
    if not session.get('site_csrf'):
        session['site_csrf'] = secrets.token_hex(16)
    return page('site/contact.html', title='免費諮詢・預約試聽',
                description=f"填寫資料預約{d['name']}免費諮詢，或加 LINE 直接詢問多益、雅思、托福、日文、韓文課程。",
                keywords=['補習班諮詢', '預約試聽', '多益課程諮詢', '雅思課程諮詢'],
                jsonld=[breadcrumb(('免費諮詢', abs_url('site.contact')))],
                v=values, errors=errors, csrf=session['site_csrf'],
                identities=IDENTITIES, contact_times=CONTACT_TIMES)


@bp.route('/thanks')
def thanks():
    resp = Response(page('site/thanks.html', title='已收到您的資料', description='已收到您的諮詢資料。'))
    resp.headers['X-Robots-Tag'] = 'noindex'
    return resp


@bp.route('/robots.txt')
def robots():
    lines = ['User-agent: *', 'Allow: /']
    for p in ('/dashboard/', '/learn/', '/vocab', '/exam/', '/jlpt-mock/', '/topik-mock/', '/ai/',
              '/phonics/', '/admin', '/login', '/register', '/api/', '/tts', '/thanks',
              '/mock-test/result/'):
        lines.append(f'Disallow: {p}')
    lines.append(f'Sitemap: {abs_url("site.sitemap")}')
    return Response('\n'.join(lines) + '\n', mimetype='text/plain')


@bp.route('/sitemap.xml')
def sitemap():
    today = datetime.now(TW).date().isoformat()
    urls = [(abs_url('site.home'), '1.0'), (abs_url('site.courses'), '0.9')]
    urls += [(abs_url('site.course', key=c['key']), '0.9') for c in COURSES]
    urls += [(abs_url('site.campus', slug=c['slug']), '0.8') for c in info()['campuses']]
    urls += [(abs_url('site.mock_take', key=k), '0.8') for k, _n in MOCKS if k in MOCKS_READY]
    urls += [(abs_url('site.mock_test'), '0.7'), (abs_url('site.contact'), '0.8'), (abs_url('site.privacy'), '0.2')]
    body = ''.join(f'<url><loc>{u}</loc><lastmod>{today}</lastmod><priority>{p}</priority></url>' for u, p in urls)
    xml = f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{body}</urlset>'
    return Response(xml, mimetype='application/xml')


def is_public(path):
    return path in ('/', '/robots.txt', '/sitemap.xml') or path.startswith(PUBLIC_PREFIXES) \
        or path.startswith('/static/')


def noindex_private(resp):
    """學生的測驗系統、後台、登入頁都不讓搜尋引擎收錄。"""
    if not is_public(request.path):
        resp.headers.setdefault('X-Robots-Tag', 'noindex, nofollow')
    return resp


# ---------------------------------------------------------------------------
# 諮詢名單（個資）：獨立的 instance/leads.db，不進 git
# ---------------------------------------------------------------------------

LEAD_FIELDS = ['name', 'phone', 'email', 'line_id', 'identity', 'courses', 'campus', 'contact_time', 'message', 'source']


def client_ip():
    return request.headers.get('Cf-Connecting-Ip') or request.remote_addr or '?'


_hits = {}


def too_many(ip, limit=5, window=3600):
    """同一個 IP 一小時最多送 5 次，避免被灌假名單。"""
    now = time.time()
    hits = [t for t in _hits.get(ip, []) if now - t < window]
    if len(hits) >= limit:
        _hits[ip] = hits
        return True
    _hits[ip] = hits + [now]
    return False


def db_path():
    return os.path.join(_['app'].instance_path, 'leads.db')


def conn():
    os.makedirs(_['app'].instance_path, exist_ok=True)
    c = sqlite3.connect(db_path())
    c.row_factory = sqlite3.Row
    c.execute("""CREATE TABLE IF NOT EXISTS leads (
        id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT NOT NULL,
        name TEXT, phone TEXT, email TEXT, line_id TEXT, identity TEXT, courses TEXT, campus TEXT,
        contact_time TEXT, message TEXT, source TEXT, consent INTEGER DEFAULT 0,
        status TEXT DEFAULT 'new', staff_note TEXT DEFAULT '')""")
    cols = {r[1] for r in c.execute('PRAGMA table_info(leads)')}
    if 'mock' not in cols:   # 迷你模考的成績摘要（school_mock.py）
        c.execute("ALTER TABLE leads ADD COLUMN mock TEXT DEFAULT ''")
    if 'mailed' not in cols:   # 通知信寄過沒有（lead_mail.py；沒寄成功的之後會補寄）
        c.execute("ALTER TABLE leads ADD COLUMN mailed INTEGER DEFAULT 0")
    return c


PHONE_RE = re.compile(r'^(09\d{8}|0\d{1,2}\d{6,8}|\+?886\d{8,9})$')
EMAIL_RE = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')


def validate(form, d):
    v = {k: (form.get(k) or '').strip()[:500] for k in LEAD_FIELDS if k != 'courses'}
    v['phone'] = re.sub(r'[\s\-()]', '', v['phone'])
    v['courses'] = [k for k in form.getlist('courses') if k in COURSE_MAP]
    v['consent'] = form.get('consent') == 'yes'
    errors = []
    if not v['name']:
        errors.append('請填姓名')
    if not PHONE_RE.match(v['phone']):
        errors.append('請填正確的電話（例如 0912345678）')
    if v['email'] and not EMAIL_RE.match(v['email']):
        errors.append('電子郵件格式不對')
    if v['campus'] and v['campus'] not in [c['name'] for c in d['campuses']]:
        v['campus'] = ''
    if v['identity'] not in IDENTITIES:
        v['identity'] = ''
    if v['contact_time'] not in CONTACT_TIMES:
        v['contact_time'] = ''
    if not v['consent']:
        errors.append('請勾選同意個人資料蒐集說明')
    return v, errors


def save_lead(v, mock=''):
    with conn() as c:
        cur = c.execute("""INSERT INTO leads (created_at, name, phone, email, line_id, identity, courses, campus,
                     contact_time, message, source, consent, mock) VALUES (?,?,?,?,?,?,?,?,?,?,?,1,?)""",
                        (datetime.now(TW).strftime('%Y-%m-%d %H:%M'), v['name'], v['phone'], v['email'], v['line_id'],
                         v['identity'], '、'.join(COURSE_MAP[k].get('form') or COURSE_MAP[k]['name'] for k in v['courses']), v['campus'],
                         v['contact_time'], v['message'], v['source'][:200], mock))
        lead_id = cur.lastrowid
        row = dict(c.execute('SELECT * FROM leads WHERE id=?', (lead_id,)).fetchone())
    import lead_mail
    lead_mail.notify_lead(row, info())
    return lead_id


def lead_rows(status=None):
    with conn() as c:
        if status in ('new', 'done'):
            return c.execute('SELECT * FROM leads WHERE status=? ORDER BY id DESC', (status,)).fetchall()
        return c.execute('SELECT * FROM leads ORDER BY id DESC').fetchall()


@admin.bp.route('/leads')
@admin.login_required
def leads():
    status = request.args.get('status', 'new')
    with conn() as c:
        counts = dict(c.execute('SELECT status, COUNT(*) FROM leads GROUP BY status').fetchall())
    return render_template('site/admin_leads.html', rows=lead_rows(status), status=status, counts=counts)


@admin.bp.route('/leads/<int:lead_id>', methods=['POST'])
@admin.login_required
def lead_update(lead_id):
    status = 'done' if request.form.get('status') == 'done' else 'new'
    with conn() as c:
        c.execute('UPDATE leads SET status=?, staff_note=? WHERE id=?',
                  (status, (request.form.get('staff_note') or '').strip()[:500], lead_id))
    return redirect(url_for('admin.leads', status=request.args.get('back', 'new')))


def _cell(x):
    """擋 Excel 公式注入：表單填 =、+、-、@ 開頭的字，打開 CSV 時不會被當成公式執行。"""
    x = '' if x is None else str(x)
    return "'" + x if x[:1] in ('=', '+', '-', '@', '\t', '\r') else x


@admin.bp.route('/leads.csv')
@admin.login_required
def leads_csv():
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(['編號', '時間', '姓名', '電話', 'Email', 'LINE ID', '身分', '想了解的課程', '校區',
                '方便聯絡時段', '留言', '從哪一頁來', '模考成績', '狀態', '工作人員備註'])
    for r in lead_rows('all'):
        w.writerow([_cell(x) for x in [r['id'], r['created_at'], r['name'], r['phone'], r['email'], r['line_id'], r['identity'],
                    r['courses'], r['campus'], r['contact_time'], r['message'], r['source'], r['mock'],
                    '已聯絡' if r['status'] == 'done' else '未聯絡', r['staff_note']]])
    # 前面加 BOM，Excel 打開中文才不會亂碼
    return Response('﻿' + out.getvalue(), mimetype='text/csv',
                    headers={'Content-Disposition': 'attachment; filename=leads.csv',
                             'Cache-Control': 'no-store'})


def register(app, deps):
    """由 app.py 呼叫（要在 admin.register 之前，名單頁掛在後台的 bp 上）。deps：current_student。"""
    _.update(deps, app=app)
    app.after_request(noindex_private)
    import school_mock  # noqa: F401  迷你模考的路由掛在同一個 bp 上，要在註冊前載入
    app.register_blueprint(bp)
