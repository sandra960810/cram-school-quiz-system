# 補習班雅思測驗系統

給 Claude 的專案說明。接手前請先讀完這份。

## 這是什麼

一套給補習班學生用的雅思練習網站，用 Flask + SQLite 寫成，跑在補習班櫃台那台
Windows 電腦上（`C:\Users\TLC-5\Desktop\quiz-system`），需要給主管或遠端學生看時，
用 `share.bat` 開 Cloudflare 臨時通道產生公開網址。
官網的正式網址是 **https://www.trinity413.com**（2026-11 使用者在 Cloudflare 買的；tlc.tw 不動、不放新官網），
由 `site_tunnel.bat` 開 Cloudflare 具名通道 `trinity-site`（設定在櫃台電腦 `%USERPROFILE%\.cloudflared\config.yml`），
開機自動執行（啟動資料夾捷徑）。通道程式刻意叫 `site-tunnel.exe`：`share.bat` 會 `taskkill cloudflared.exe`，換名字才不會把官網一起關掉。

兩大功能：

1. **單字學習與圖鑑** — 依主題滑卡學單字（右滑熟、左滑不熟），雅思 7,037 個不重複單字，分在 01–10、12–15 共 14 個主題（來源見 `ielts/README.md`）
2. **模擬測驗區** — 聽說讀寫四個技能，各自一套**自製**題庫

## 使用者

補習班經營者，不是工程師。她用滑鼠雙擊 `.bat` 檔操作，不打指令。
因此：

- 任何需要她執行的東西，做成可雙擊的 `.bat`，並把結果寫進 log 檔
- 介面文字、程式註解、commit 訊息一律用**繁體中文**
- 報告結果時講清楚「做了什麼、她要做什麼」，不要只貼指令

## 怎麼跑起來

雙擊 `run.bat`。它會依序：備份資料庫 → `git pull` → 裝套件 → 匯入單字 →
關掉舊的 5000 埠程式 → 啟動網站 → **用 Edge 開啟**。

用 Edge 是刻意的：這台電腦沒有安裝任何英文系統語音，Chrome 只有 3 個 Google
語音，而 Edge 內建 46 個微軟神經語音（Sonia、Ryan、Libby…），單字發音自然得多。
`static/ui.js` 會自動挑最好的語音（Natural／Neural 神經語音優先、英文固定英國腔、避開 Maisie 這類兒童聲），挑不到神經語音時會提示改用 Edge。
**不讓學生自己選語音或口音**（2026-11 使用者要求拿掉）：右下角「聲音」面板只留按鈕音效與語速，以前存的語音選擇一律忽略。

其他裝置（**特別是 Android 的 Chrome：連續播放時會一直唸同一個字**）改播伺服器產生的音檔：
`UI.speak` 在瀏覽器沒有神經語音或是 Android 時，改用 `/tts?text=…`（`word_audio.py` 用 edge-tts 產生並快取），
產生失敗才退回瀏覽器語音。所以櫃台電腦要能連上微軟語音服務，`run.bat` 會裝 `edge-tts`。

## 程式結構

```
app.py              Flask 主程式：資料模型、單字學習、測驗區路由
school_site.py      驅勢英日韓公開官網（首頁、課程、校區、諮詢表單、SEO、後台諮詢名單 /admin/leads）；資料在 public_site/site_info.json
listening_bank.py   聽力題庫的載入、渲染與批改
reading_bank.py     閱讀題庫的載入、渲染與批改（判分沿用 listening_bank）
listening/          聽力題庫資料（每回一個資料夾）
  tests.json        題庫清單
  L01/meta.json     該回的標題與說明
  L01/part1~4.json  逐字稿、題組、答案、解析
reading/            閱讀題庫資料：tests.json、R01/meta.json、R01/passage1~3.json
writing_bank.py     寫作題庫的載入、圖表繪製（SVG）與 AI 老師批改
writing/            寫作題庫資料：tests.json、W01/meta.json、W01/task1~2.json
speaking_bank.py    口說題庫的載入、考官台詞流程與 AI 老師評分（沿用寫作的金鑰設定）
speaking/           口說題庫資料：tests.json、S01/test.json…
jlpt_mock.py        日檢模擬考 /jlpt-mock/<學生id>：題庫解析、作答、交卷顯示正解、估計分數（Blueprint）
jlpt_mock/          日檢模擬考題庫 N5.txt～N1.txt、第 2 回起 N5-2.txt…（純文字格式，見 README.md）
jlpt_audio.bat      在櫃台電腦產生日檢模擬考聽解音檔（雙擊）
topik_mock.py       韓檢模擬考 /topik-mock/<學生id>：TOPIK I／II 各十回，作答、交卷顯示正解、算總分與級數、寫作 AI 批改（Blueprint）
topik_mock/         韓檢模擬考題庫 TOPIK1.txt、TOPIK2.txt，第 2 回起 TOPIK1-2.txt…（純文字格式，見 README.md）
topik_audio.bat     在櫃台電腦產生韓檢模擬考聽力音檔（雙擊）
set_ai_key.bat      在櫃台電腦設定 AI 老師的 API 金鑰（存進 ai_key.txt，不進 git）
site_tunnel.bat     官網固定網址 www.trinity413.com 的 Cloudflare 具名通道（開機自動執行，log 在 site_tunnel_log.txt）
set_mail.bat        設定官網諮詢通知信的寄件帳號（instance/mail.json，不進 git）
set_ai_paid_key.bat 設定備用付費金鑰（ai_key_paid.txt，不進 git）：免費 Gemini 額度用完時自動改用
ai_tutor.py         AI 學習教練（Blueprint）：錯題解釋、弱點練習 /ai/<id>/practice、學習報告 /ai/<id>/report、單字記憶法；前端 static/ai_tutor.js／ai_tutor.css
templates/          Jinja 樣板
static/ui.js        共用：音效、動畫、英文發音挑選
static/theme.css    全站色系（色彩變數），每一頁都要先載入；換色只改這一份
static/icons.svg    全站線條圖示（取代 emoji）；icons.py 提供樣板用的 icon()
static/exam.css     測驗頁共用樣式
tools/              產生音檔與檢查題庫的腳本
import_sheet.py     從 vocab_master.xlsx 匯入單字（run.bat 會跑）
tools/dedupe_vocab.py  合併同課程的重複單字並轉移學生紀錄（run.bat 匯入後會跑）
word_audio.py       單字／例句發音音檔 /tts（edge-tts 產生、快取在 instance/tts_cache/）
vocab_quiz.py       單字測驗區：出題、批改、交卷（Blueprint，由 app.py 最後面 register 掛上）
word_roots.py       建構式字彙：英文單字的字根／字首／字尾家族、單字卡上的同家族字、推薦整組背（Blueprint）
morphology/roots.txt  字根字首資料（一行一組，字依字源人工挑選）；改完跑 tools/check_word_roots.py
phonics.py          英文零基礎的「學發音」頁 /phonics/<學生id>：只有單字＋KK 音標＋聽／慢慢聽（2026-11 簡化）
pronunciation/      單字 KK 音標 kk.json（tools/make_pronunciation.py 由 CMU 發音字典產生，見 README）
basic/、general/    英文零基礎、一般英文的單字 CSV 與來源授權說明（README.md）
accounts.py         學生註冊／登入（/register、/login）、每個請求前的權限檢查 guard()、工作人員審核開通頁 /admin/students
admin.py            工作人員後台 /admin：登入（管理員密碼）；單字編輯目前暫停（EDITOR_ENABLED=False，程式保留）
admin_bank.py       管理員後台 /admin/bank：聽說讀寫題庫的新增、編輯、刪除（編輯頁的前端在 static/admin_bank.js）
bank_store.py       題庫存取層：原始題庫＋後台改動（instance/bank_edits/，不進 git）
reset_admin_password.bat  忘記管理員密碼時清掉，回到本機重新設定
topik/              韓檢 1～6 級單字 CSV 與來源說明（README.md）
static/hangul_keyboard.js  韓文鍵盤：韓檢單字測驗的打字題用（沒有韓文輸入法的電腦也能打）
jlpt/               日檢 N5～N1 單字 CSV（含「讀音」欄）與來源說明（README.md）
jp_verbs.py         日文動詞變化（日檢單字卡的「動詞變化」）
static/kana_keyboard.js    日文輸入：羅馬拼音自動轉假名＋五十音鍵盤（日檢打字題、單字搜尋用）
```

資料模型都在 `app.py` 上半部：`Student`、`Vocabulary`、`LearningProgress`、
`Favorite`、`TestAttempt`、`TestAnswer`、`TestMistake`、`WritingDraft`。
啟動時會自動補欄位（`PRAGMA table_info` 檢查後 `ALTER TABLE`），不用寫 migration。

## 考試類型（雅思、多益…）

網站會涵蓋多種考試（雅思、多益、英文零基礎、一般英文、韓檢、日檢），設定集中在 `exams.py` 的 `EXAMS`：

- `/dashboard/<學生id>` 是**選擇考試**頁；`/dashboard/<學生id>/<考試>`（ielts、toeic）是該考試的功能選單
- 目前在哪個考試記在 cookie `exam`，單字學習、單字測驗都只看該考試的課程（`Vocabulary.category`，
  例如 `IELTS`、`TOEIC`），用 `exams.course_of(student)` 取得，**不要再用 `student.enrolled_course`**
- `features` 決定開哪些功能：雅思有 learn／vocab_quiz／exam，多益與一般英文有 learn／vocab_quiz，
  零基礎多一個 phonics（ABC 與發音教學）；`/exam/` 一律算雅思、`/phonics/` 一律算零基礎
- 主題清單 `OFFICIAL_THEMES` 每筆有 `course`；多益主題編號是 T01–T12、零基礎 B01–B13、一般英文 G01–G15，避免和雅思 01–15 混在一起
- 色系：每個樣板的 `<html data-exam="{{ exam.key }}">`，`theme.css` 用 `:root[data-exam="toeic"]` 覆寫成藍色，
  零基礎（basic）暖橘、一般英文（general）青綠；選擇考試頁的卡片色是 `.exam-tone-<考試>`
- 之後做登入與後台開通權限：改 `exams.exams_for(student)` 依學生權限回傳可用考試即可
- 多益單字在 `toeic/toeic_vocab.csv`（TSL＋BSL＋NGSL 三份開放字表 4,002 字＋2026-11 從雅思字庫補 1,003 字，共 5,005 字，CC BY-SA 4.0，來源與改動見 `toeic/README.md`），
  `run.bat` 會匯入
- 零基礎單字在 `basic/basic_vocab.csv`（2,006 字，國中小程度、例句刻意很短），一般英文在 `general/general_vocab.csv`
  （4,032 個日常生活字）。**兩區互不重複**，各自也沒有重複字；來源是 NGSL＋OpenSubtitles 字頻（CC BY-SA 4.0），
  中文意思與例句原創，見各資料夾的 `README.md`。`run.bat` 會匯入。加字時兩份都要檢查不重複
- **韓檢（topik，莓果紅）**：單字依等級分成 K1～K6 六個主題（1～6 級），共 6,630 字，來源與分級方式見 `topik/README.md`。
  - **逐級開通**：學生可用的等級由 `exams.open_levels(student, exam)` 決定，讀 `Student.unlocked_levels`
    （JSON，例如 `{"topik": [1, 2]}`；空的＝全部開放）。沒開通的等級（`app.locked_theme_ids`）在單字學習區顯示
    「尚未開通」、主題頁回 403，也不會出現在單字測驗與收藏。之後接購買紀錄或後台，只要寫這個欄位
  - 韓文頁面（`<html data-exam="topik">`）：`UI.speak` 唸韓文（伺服器音檔 `/tts?accent=KR` 用 `ko-KR-SunHiNeural`，
    瀏覽器語音挑 ko-KR），發音設定和英文分開存；圖鑑分頁依第一個字的子音（ㄱㄴㄷ…，`first_letter`）
  - 單字測驗：例句填空由 `vocab_quiz.find_cloze_ko` 辨認活用形（가다→가요、봤어요、했어요），
    不規則活用在例句裡用 `[ ]` 標出（顯示例句時 `clean_sentence` 會拿掉括號）；拼寫與填空提示只給子音（ㅈㅇㅇ），
    打字題有韓文鍵盤（實體鍵盤照 2 벌식鍵位打，或點螢幕按鍵）
  - 「英文解釋」欄放漢字（`漢字：學校`），單字卡顯示在中文意思下面
- **日檢（jlpt，抹茶綠）**：單字依等級分成 N5～N1 五個主題（`level` 5～1，逐級開通和韓檢共用 `Student.unlocked_levels`，
  例如 `{"jlpt": [5, 4]}`），來源與各級字數見 `jlpt/README.md`
  - `Vocabulary.reading` 存假名讀音（只有日檢用；兩種讀法用「／」隔開）。單字卡、圖鑑、搜尋結果顯示讀音；
    播放單字唸讀音（`say_text`，語音唸漢字可能唸錯）；伺服器音檔 `/tts?accent=JP` 用 `ja-JP-NanamiNeural`
  - 圖鑑依讀音五十音排序，分頁是「あ行、か行…」（`first_letter(word, reading)`，濁音併到清音那行）
  - 搜尋比對讀音：平假名、片假名、羅馬拼音（前端用 `KanaKeyboard.romajiToKana` 轉）都找得到；中文意思照常
  - **動詞變化**：單字卡（滑卡和點開的單字卡）上，動詞與する動詞有「動詞變化」可展開（ます形、ない形、た形、なかった形、て形、
    可能、意向、ば形、被動、使役、命令），寫法和讀音一起變、點一下會唸；由 `jp_verbs.conjugations()` 依「詞性」欄判斷種類
    （第一類＝五段、第二類＝一段、第三類＝する／来る；名詞・する動詞顯示「〇〇する」的變化），不靠字尾猜。展開與否記在 localStorage
  - 日文頁面元素加 `lang="ja"`，`theme.css` 的 `:lang(ja)` 換成日文字型（同一個漢字中日字形不同）
  - 單字測驗：例句裡用 `[寫法|讀音]` 標出填空處（`vocab_quiz.find_cloze_ja`），**漢字或假名都算對**（題目 JSON 的 `accept`），
    比對用 `normalize_ja`（片假名＝平假名、全半形統一；不能用 `normalize`，它會把濁音點去掉）；
    前端 `normJa()` 要一致。打字題有 `kana_keyboard.js`：鍵盤打羅馬拼音自動變假名、五十音鍵盤可以點，
    鍵盤上方可切換「ひらがな／カタカナ」（片假名模式下點的、羅馬拼音轉的都是片假名，選擇記在 localStorage）
- 學發音（`phonics.py`）：**2026-11 使用者要求「不要這麼複雜」，只留 KK 音標和單字怎麼唸**。選零基礎／一般英文主題，
  上方大卡片顯示單字、KK 音標（`pronunciation/kk.json`，含重音符號 ˈ）、中文，按「聽」（正常速度）或「慢慢聽」（rate 0.55）；
  下方列出整個主題的字（單字＋KK＋中文），點一下就唸。上次練到的主題和位置記在 localStorage。
  原本的 ABC 字母、發音規則課、聽音選字、音節拆解、跟讀評分都已拿掉，不要再加回去，除非使用者要求。
  同一個選單最下面有「常見字尾」（`phonics.SUFFIXES`：-tion、-sion、-ing、-ed 的三種念法、-es、-er、-or、-ture、-ly、-y、-ful、-less、-ness、-ment、-ous），
  `/phonics/<id>/words?suffix=tion` 回 `{suffix, words}`；畫面把單字結尾的字尾和 KK 結尾的念法標顏色，所以**例字的 KK 一定要以該念法結尾**
  （kk.json 沒有的變化形如 jumped、boxes，KK 直接寫在 SUFFIXES 裡）
  加新單字後要重跑 `python tools/make_pronunciation.py cmudict.dict`

## 驅勢英日韓公開官網（school_site.py）

- 補習班品牌是「**驅勢英日韓**」（驅勢語言教育中心），使用者有時打成「趨勢」，網頁上一律用「驅勢」
- Logo 在 `static/images/site/`（logo.png 原圖、emblem.png 頁首小圖騰、favicon.png）；英文名 Trinity Language。標語與簡介是使用者提供的文字整理改寫
- 課程的上課時間、師資、費用使用者說「請學生諮詢」：空白時課程頁顯示諮詢區塊（不再顯示待填）；營業時間、Email 先不放，空白就不顯示
- 五個校區（台北站前、桃園站前、桃園南崁、中壢站前、新竹站前；大直內湖校已沒開）的地址電話在 `site_info.json`，台北是館前路 36 號 3 樓（使用者確認）；`map_url` 空白會自動用地址產生 Google 地圖連結

2026-11 使用者要求：原本官網 www.tlc.tw 掛掉（DNS 指向補習班自己一台 Windows Server 2012 R2，網站已不在、https 憑證無效；
tlc.tw 的 DNS 在 cyberdns.tw，**MX 是 Google Workspace，動 DNS 時信箱紀錄一定要保留**），新官網直接做在這個網站裡：

- **官網介紹學員線上學習系統**（2026-11 使用者決定單字學習與模考系統上線，原本「先不提」取消）：`_m.html` 的 `system_block`（`#system`，`.h-sys`），**每個功能寫清楚、改編原版排版、強調 AI 並有 AI 視覺化**（使用者要求）：上面淺色科技感 AI 區（使用者不要深色底；狀態列「AI TUTOR · N MODULES ONLINE」、格線與掃描光，每個 AI 功能一張卡：`ai_viz()` 小圖（對話框、長條圖、批改、聲波、折線、節點）、名稱、說明、適用科目），中間淺色學習功能卡，下面是原版的各科一列短標籤（`COURSES` 的 `sys`，只在主頁面）。資料在 `school_site.SYSTEM_FEATURES`（`exams` 哪些科目有、`detail` 各科專屬頁面改用的說明），**只寫系統真的有的功能**；主頁面列全部，各科專屬頁面（`?exam=`）與課程頁只列該科有的，托福系統還沒做不顯示；區塊底下有「學員登入」（`/login`）。已登入的學生開 `/` 也是看官網；
  **版面與配色（2026-11 使用者給兩張參考圖改版）**：米白底 `--brand-bg`、近黑字與按鈕 `--brand-ink`、細灰分隔線 `--brand-line`、黑色頁尾，重點色是低彩度的芥末黃 `--brand-gold`（眉標短線、編號、招生區淺底）與霧藍 `--brand-ai`（AI 元素），使用者要求兩色「不能太搶眼」（變數都在 `theme.css` 開頭）；
  大字粗體標題、細線分隔、不用圓角大卡片與陰影。首頁 `home.html`（`h-*` 樣式）照參考圖：主視覺（左側直排細欄＋大字標題「你的多益實力有幾分？」（科技感動態：進場每個字解碼定格、滑鼠附近亮起細格線，site.js 的 `heroTitle`；**固定是多益、不輪播**（2026-11 使用者要求「先多益就好，不要輪播」）；**廣告連結決定最上面是哪個考試**（使用者要求：之後下廣告，從多益廣告進來最上面就是多益並加上簡單課程介紹，以此類推）：`/?exam=toeic|ielts|toefl|jlpt|topik`（也認 `utm_content`／`utm_campaign` 等於考試代號，`school_site.hero_course`），標題與按鈕換成該考試（托福沒有模考，按鈕是諮詢）；**廣告進來的版本在諮詢表單下面先接「學校＋該課程介紹」`#intro`（`.h-adi`：關於驅勢、三個為什麼選驅勢、課程卡片：課程說明、開課校區、時間費用請諮詢，照片 class.jpg），再接「學員心得」`#reviews`（`.h-rev`），然後才是 AI 線上模考等**（2026-11 使用者要求）；這時頁面下方的「為什麼選驅勢」「關於」不顯示（不重複）；**各科專屬頁面只放那一科的模考入口**（`.h-acc.is-one`，不是展開式；托福沒有模考就整區不顯示），**也不放其他課程的入口**（01～05 課程列表 `#courses` 不顯示），主頁面（沒帶參數）維持四科模考與課程列表都放（2026-11 使用者要求）。學員心得讀 `site_info.json` 的 `testimonials`（course、name、result、text，`school_site.reviews_for` 同課程排前、**每科最多 9 則，一次看 3 則、左右滑或按箭頭**（2026-11 使用者要求）），**只放補習班提供的真實心得，不要自己編**（目前 14 則取自使用者硬碟「Trinity 學員心得」裡已公開的文章，名字中間用 O 遮，資料夾標示不能公開的不用；**每則有去背照片** `photo`（`static/images/site/reviews/<考試>-<n>.webp`，硬碟裡補習班已去背的生活照，沒有的用 rembg 從已發佈的海報摳圖），卡片上方人像站在淺金半圓上），沒資料顯示待填；沒帶參數就是多益、沒有這兩塊；canonical 一律是首頁）＋黑按鈕與圓圈箭頭連結，**右側是科技感面板**（2026-11 使用者要求把 AI 模考卡片的 `tech_panel` 樣式結合到最上方，取代原本的大照片：藍黑底、電路線、聲波、分數環，大字是該科英文代號，跟著 `?exam=` 換，上面小字固定是「實體課 · 線上課 · 專屬 AI 學習系統」（使用者要求），**文字排版要有科技感**（使用者要求）：三個小字排成一行白字、中間用 × 隔開：實體課 × 線上課 × 專屬 AI 學習系統（使用者要求不要編號、不要框框、整行白色），大字考試代號用等寬字＋外框殘影（偶爾輕微閃動），下面一行等寬字系統狀態「AI MOCK TEST · INSTANT SCORE_」；`tech_panel(…, h=270, cls='h-hero-tech', tx=44, chips=[…])`，樣式在 site.css 的 `.h-hero-tech .t-chip-*`、`.t-label-mono`、`.t-status`），交界壓旋轉的圓形 AI 徽章）；主按鈕 `.h-go` 靠右、**橘底黑字膠囊形**（使用者指定 Claude 的橘 `--brand-orange`、圓角，右邊黑色圓形箭頭），「其他模考」在左
  → **諮詢表單 `#consult`**（使用者要求主視覺結束後直接接個資表單、展開著可以直接填：姓名、電話、校區、課程、同意個資；送到 `/contact` 共用同一套檢查與 csrf，填錯在諮詢頁顯示並保留內容；課程勾選框日檢、韓檢顯示成「日文」「韓文」（`COURSES` 的 `form` 欄位，名單也記這個名字，2026-11 使用者要求）；廣告進來時該課程先勾好，`source` 記「首頁表單（某某廣告）」；**表單框框都圓角**（使用者要求：外框、輸入框、下拉選單、按鈕，`.s-form` 共用，諮詢頁也一樣））
  → AI 線上模考（**展開卡片**：使用者給影片要的互動，**預設全部閉合、四張平均分寬佔滿整排**（橫排大字考試代號＋說明），滑鼠移到哪張（停 0.12 秒）它才展開、其他縮成 104px 直條，滑鼠離開整排就回到平均；也可以點或用鍵盤 Tab；不自動輪播；展開 0.75 秒（使用者要「用原本的速度」）；舞台高 500px、超出內文寬到 1360px；淺色細格線舞台（使用者不要深色底）；`.h-acc`，site.js 加 `.is-ready` 才變展開式；手機（760px 以下）四條上下排列，預設平均高度（依畫面高度算 `--bar`），點哪條就展開哪條、其他縮成細條，展開高度由 site.js 量內容寫進 `--open-h`，展開後自動捲到看得到（使用者要求「手機也是直條，點哪個展開哪個，大小配合介面」，取代原本的左右滑動卡片）；卡片右邊是 `_m.html` 的 `tech_panel` 科技感面板：藍黑底 `--brand-tech`、電路線、聲波、分數環，使用者要求「強調 AI 不是放 AI 字樣，要有科技感」）→ 課程（左照片＋學習地圖 STEP 1 英文零基礎／STEP 2 檢定衝刺・高分，右邊 01～05 大字編號列表，**點了連到各科專屬頁面 `/?exam=`**（使用者要求））
  → 為什麼選驅勢（**取自補習班手冊「Trinity is the best choice」的前六點**（使用者要求只放前六個），**第七點「實體課＋線上直播課」**（原本的「課程招生中」區塊使用者要求拿掉，線上課改寫在這裡，佔滿一整列），2026-11 使用者說「這裡面的內容都可以用」：`school_site.WHY`（標題、說明、短說明），主頁面三欄，各科專屬頁面的學校介紹用短說明，排成橫向小卡、每點前面配線條小圖（`WHY` 第 4 欄是圖示名稱，2026-11 使用者要求不要直列清單））→ **程度分級制度 `#levels`（`.h-cefr`，只在主頁面）**：手冊「TRINITY 專業程度分級制度」，**照手冊做成長條圖**（使用者要求「還是放圖表」）：LEVEL 1～6 六色長條（`theme.css` 的 `--lv1`～`--lv6`）由低到高、條內是課程內容，下面是程度名稱與 CEFR A1～C2，再下面各檢定（GEPT、TOEIC、IELTS、TOEFL-iBT）分數對齊 B1～C2 那四欄，最底是雙語教學／全英教學→國外語言學校；手機整張圖左右滑。資料在 `school_site.CEFR_LEVELS`、`CEFR_EXAMS`，只寫手冊上有的。**各科專屬頁面與課程頁放該科的 CEFR 對照**（`_m.html` 的 `cefr_block`，`#cefr`，A1～C2 六格，資料 `CEFR_BY_EXAM`）：多益、雅思、托福照手冊，日檢照官方 2025 年 12 月起成績單附的 CEFR 參考等級（依總分），韓檢官方沒有對照不放 → 關於（左文右照片）。照片不重複使用；舊的底部測驗區塊已拿掉（AI 線上模考已有入口，不重複）。
  **新版官網要使用者在預覽確認後才上線**（2026-11 使用者說「先檢查確定可以後再上線」）：預覽在櫃台電腦 `C:\Users\TLC-5\Desktop\quiz-preview`（git worktree，5001 埠，只有本機看得到，桌面捷徑「預覽新版官網」）。
  **科技感互動**（2026-11 使用者要求「整個網站的交互設計改得更有科技感」）：`static/site.js`＋`site.css` 最後的「科技感互動」段：捲到才浮現、眉標打字游標、編號解碼、卡片跟滑鼠的霧藍光暈與四角 HUD 框、照片格線與掃描線、頁首閱讀進度線、頁尾流光；
  首頁「關於」照片上疊 AI 圓環（`.t-hud-ring`）。電腦設定減少動態時不跑動畫，沒有 JS 內容照常顯示。
  **AI 元素只放在真的有 AI 的地方**（迷你模考、AI 弱點診斷）：`_m.html` 的 `ai_chip()` 晶片圖示、`.s-ai-pill` 藍色 AI 標籤。
  2026-11 使用者兩次要求拿掉重複：本頁目錄、重點數字、地球圖、底部聯絡區塊、每列「看課程」、學習地圖按鈕、選單的「免費諮詢」都拿掉了（頁首已有「預約諮詢」）。
  **同樣的內容不要重複**（使用者要求；例如「實體＋線上」「零基礎～高階」只出現在一個地方）。**首頁不另放校區區塊**（使用者要求），
  **頁首選單最前面是「首頁」，細線隔開後是各科主頁入口**（2026-11 使用者要求：多益、雅思、托福、日檢、韓檢，連到 `/?exam=…`，和廣告進來的版本一樣，目前那科畫底線），細線隔開後是「課程介紹」「校區」；頂端「課程介紹」捲到首頁的課程區 `#courses`（使用者要求不跳到 /courses），「校區」連到頁尾的校區欄。重點文字取自補習班自己的 IG 海報。照片只能用可免費商用的圖庫（來源見 `static/images/site/README.md`）
- **零基礎英文算一個科目**（2026-11 使用者要求）：`COURSES` 的 `basic`（選單、`/?exam=basic`、`/courses/basic`、課程列表 06、諮詢表單都有），內容是系統的英文零基礎＋一般英文；沒有迷你模考，主視覺標題用 `hero` 欄位（「零基礎英文／從發音開始學」）、按鈕是諮詢；CEFR 對照放手冊的 LEVEL 1、2
- 公開頁：`/` 首頁、`/courses`、`/courses/<toeic|ielts|toefl|jlpt|topik|basic>`、`/campus/<校區>`、
  `/mock-test`（迷你模考總覽；**入口放在各課程頁**（使用者要求，hero 按鈕＋課程資訊上方的卡片）與首頁，頂端選單不放；多益、雅思、日檢、韓檢都有，`school_site.MOCKS_READY`、說明文字 `MOCK_BLURB`）、`/contact` 免費諮詢表單、`/privacy` 個資蒐集說明
- 樣板在 `templates/site/`、樣式 `static/site.css`；顏色照樣用 `theme.css` 變數（托福 `.exam-tone-toefl`、LINE 綠 `--line-green`）
- **補習班資料在 `public_site/site_info.json`**（電話、地址、LINE 連結、各課程上課時間／師資／費用…）。空白欄位網頁顯示黃色「待填」，
  結構化資料會略過。**不要自己編課程內容、價格、學員見證**，只寫網站真的有的東西（字數、模考回數）
- SEO：每頁 title／description／keywords／canonical（用 `site_url`）／Open Graph、JSON-LD（EducationalOrganization、各校區、Course、
  BreadcrumbList）、`/sitemap.xml`、`/robots.txt`。**非公開頁（學生系統、後台、登入）一律回 `X-Robots-Tag: noindex`**（`noindex_private`），
  新增公開頁要把網址開頭加進 `PUBLIC_PREFIXES` 和 sitemap
- 諮詢名單是個資：存在 **`instance/leads.db`（獨立檔、不進 git；quiz.db 有進 git 所以不能放那裡）**。表單有 csrf、隱藏欄位擋機器人、
  同 IP 一小時 5 次、必須勾同意個資說明。工作人員後台 `/admin/leads` 看名單、標已聯絡、寫備註、下載 CSV（擋 Excel 公式注入）
- **新名單自動寄信通知**（2026-11 使用者要求寄到 service@wkedu.com.tw）：`lead_mail.py`，收件人是 `site_info.json` 的 `notify_email`（逗號分隔可多個）；
  寄件帳號存在 `instance/mail.json`（不進 git），由櫃台電腦雙擊 `set_mail.bat` 設定（Gmail／Workspace 的應用程式密碼，會先寄測試信成功才存檔）。
  免費諮詢、模考解鎖都會寄；在背景寄，失敗不影響存檔，結果記在 `instance/mail_log.txt`。
  **沒寄成功的會補寄**（使用者要求「存在裡面的也都寄過去」）：`leads.mailed` 記寄過沒有，`set_mail.bat` 設定成功時、以及每次新名單寄出時，
  `lead_mail.send_unsent` 會把還沒寄的一起寄。`set_mail` 的密碼輸入看得到（Windows 視窗裡 getpass 貼不進去），465 連不上會改試 587

### 官網迷你模考（school_mock.py）

- 四份，題目原創、在 `public_site/mock/<考試>.json`：多益 22 題 12 分鐘（聽力應答、簡短獨白＋閱讀三種）、雅思 20 題 15 分鐘（聽力對話、獨白＋閱讀 TFNG、選擇與填空）、
  **日檢 25 題、韓檢 24 題不分級**（2026-11 使用者要求）：題目由簡單排到難，每題標 `lv`（N5～N1 各 5 題、1～6 級各 4 題）
- 聽力音檔：`/mock-test/<考試>/audio/<組>/<句>` 由伺服器用 edge-tts 產生（共用 `word_audio` 快取），**錄音文字不送到前端**；每段最多播 2 次。
  句子開頭寫「男：」「女：」會換成 json `voices` 的聲音（`school_mock.speaker`），沒寫用 `accent` 的預設聲音
- 交卷由伺服器批改，作答存在 `leads.db` 的 `mock_attempts`（代碼 token 當網址）。結果頁 `/mock-test/result/<代碼>`（noindex）
  **一開始只顯示正確率和第 `free_explains`（1）題解析**，其餘模糊；**預估成績也要留資料後才顯示**（2026-11 使用者要求，沒解鎖時是虛線框「留下資料就能看」，首頁與模考頁文案寫「交卷後留下資料，馬上看預估分數」）；**CEFR 參考等級也一樣留資料才顯示**（`school_mock.cefr_of`：多益、雅思照手冊門檻，日檢照官方對照，韓檢沒有官方對照不給）；填姓名、電話、Email（＋同意個資）才解鎖預估成績、CEFR、全部解析、各題型正確率、AI 弱點診斷
- 預估成績 `school_mock.estimate()` 依 json 設定三種算法：`score_scale`（多益，各部分 5～495 取 5 的倍數）、`band_scale`（雅思，[答對率下限, Band] 查表，聽讀平均進位到 0.5）、
  `level_scale`（日檢、韓檢：由最簡單的級數往上看，該級答對 `pass`（六成）以上才算有那級程度，遇到沒過就停；另給 100 分制得分，解鎖後顯示各級數正確率）。頁面都註明只是參考
- **AI 弱點診斷**（使用者要求官網強調 AI）：解鎖後成績頁用 JS 呼叫 `POST /mock-test/result/<代碼>/ai`，程式算好數字、把錯題與解析交給 `writing_bank.ask_json(light=True)`，
  AI 只寫總評、做得好的地方、弱點與練習方法、兩週建議；結果存在 `mock_attempts.ai_report`（同一份成績只呼叫一次）。全站一天最多 `AI_DAILY_CAP`（300）次、同 IP 一小時 10 次。
  AI 沒設定或失敗時頁面照舊顯示 json 的 `advice`（正確率低於 70% 的題型）；AI 寫好就藏起 `advice`，不重複。頁面保留「AI 產生的內容可能有錯」
- 解鎖時寫一筆諮詢名單（`source`＝某某迷你模考，`mock` 欄位是成績摘要），工作人員在 `/admin/leads` 看得到、CSV 也有「模考成績」欄
- 新增其他考試：加 `public_site/mock/<考試>.json`（格式照現有的），把 key 加進 `MOCKS_READY` 與 `MOCK_BLURB`

## 日檢模擬考（jlpt_mock.py）

- 每級各 10 回（2026-11 完成，共 50 回；**各回題目不能重複**，`check_jlpt_mock.py` 會比對題幹、考的字、選項組、文章句子、台詞），題目原創；一回一個檔：第 1 回 `jlpt_mock/N5.txt`，第 2 回起 `N5-2.txt`、`N5-3.txt`（`jlpt_mock.rounds()` 看有哪些檔；格式、題數、計分見 `jlpt_mock/README.md`）。
  網址第 1 回是 `/jlpt-mock/<id>/N5/<節>`，第 2 回起 `/N5-2/<節>`；作答紀錄 `JlptMockAttempt.rnd` 記第幾回。新增一回只要加題庫檔、跑檢查、產生音檔
- 入口在日檢功能選單的「模擬考」；要後台開通「B 模考」（功能代號 `mock`），開哪幾回在審核頁「模考開放的回數」逐回勾選
  （存在 access 的 `mock_open`，例如 `["N5", "N5-2"]`，判斷用 `exams.open_mock_tests`），和單字等級分開；
  沒有逐回設定過的學生照舊看單字等級（`exams.open_levels`），該級每回都開。沒開的回數回 403、首頁顯示「另有 N 回尚未開通」
- 一個科目交一次卷（`JlptMockAttempt` 一筆），交卷後同一頁變成檢討：正解、學生選的、中文解析、聽解台詞；
  全部科目都交過才顯示 180 分的估計分數與是否達合格標準（標明是估計）
- 聽解音檔由題庫台詞用 edge-tts 產生（`tools/make_jlpt_audio.py`，一回一個 mp3：`N5.mp3`、`N5-2.mp3`，不進 git）；沒有音檔時頁面會提示雙擊 `jlpt_audio.bat`
- 改題目後一定要跑 `python tools/check_jlpt_mock.py`

## 韓檢模擬考（topik_mock.py）

- TOPIK I（聽力 30＋閱讀 40 題，200 分）、TOPIK II（聽力 50＋寫作 4＋閱讀 50 題，300 分）各十回，題目原創；
  題型、題號、配分、時間比照正式考試，見 `topik_mock/README.md`
- 一回一個檔：第 1 回 `topik_mock/TOPIK1.txt`，第 2 回起 `TOPIK1-2.txt`～`TOPIK1-10.txt`（`topik_mock.rounds()` 看有哪些檔）。
  網址第 1 回是 `/topik-mock/<id>/t1/<節>`，第 2 回起 `/t1-2/<節>`；作答紀錄 `TopikMockAttempt.rnd` 記第幾回。
  **各回題目不能重複**：`check_topik_mock.py` 會比對所有回的文章句子、題幹、選項組、台詞與寫作題（短題幹與主題它比不到，出新回前要自己搜尋前幾回避開）
- 入口在韓檢功能選單的「模擬考」；後台審核頁韓檢的「TOPIK I 模考」（功能 `mock1`）、「TOPIK II 模考」（`mock2`）分開開通，
  和單字的 1～6 級無關。`FEATURE_PATHS` 的 `/topik-mock/` 對應一組功能（開了其中一個就能進首頁），每一回再個別檢查，沒開回 403。
  開哪幾回在審核頁「模考開放的回數」逐回勾選（存在 access 的 `mock_open`，例如 `["TOPIK1", "TOPIK1-2"]`，判斷用 `exams.open_mock_tests`）；
  沒有逐回設定過的學生，開了該級模考就每回都開
- 一節交一次卷（`TopikMockAttempt`），交卷後同一頁變成檢討：正解、學生選的、中文解析、聽力原文；
  全部科目都交過才顯示總分與級數（TOPIK I 80／140 分 1／2 級；TOPIK II 120／150／190／230 分 3～6 級）
- 寫作交卷後按「請 AI 老師批改」：`writing_bank.ask_json`（和雅思寫作共用金鑰與 Gemini／Claude 呼叫），
  四題一次批改，分數在 Python 端加總；頁面保留「AI 老師的評分不等於真實考試」。寫作可用螢幕韓文鍵盤（`HangulKeyboard.attachAll`）
- 聽力音檔由題庫台詞用 edge-tts 產生（`tools/make_topik_audio.py`，一回一個 mp3，不進 git）；沒有音檔時頁面提示雙擊 `topik_audio.bat`
- 改題目後一定要跑 `python tools/check_topik_mock.py`

## AI 學習教練（ai_tutor.py）

2026-11 加入，四個功能都沿用寫作 AI 老師的金鑰與 `writing_bank.ask_json`（Claude 用 `effort='low'`，回得快也省）：

- **AI 解釋錯題**：雅思聽力／閱讀成績頁、錯題本、日檢／韓檢模擬考檢討頁、背單字神器成績頁，答錯的題目下面有「問 AI 老師：我為什麼錯？」。
  樣板寫 `{{ ai_slot('ielts', section=..., test_key=..., qno=..., attempt_id=...) }}`（`jlpt`／`topik` 帶 `attempt_id, n`；
  背單字神器在 JS 用 `AITutor.slot()`）。**題目內容由伺服器從題庫與作答紀錄自己找**（`explain_payload`），不收前端送的題目，
  答對的題目、別人的紀錄一律 404。AI 回：為什麼錯、正解根據、陷阱、判斷方法，加一題「再練一題」小選擇題
- **AI 弱點練習** `/ai/<id>/practice`：`weak_profile()` 在 Python 端統計弱點（雅思各題型錯誤率、錯題本、寫作／口說上次 AI 建議、
  不熟的字、背單字神器各題型答對率、日檢／韓檢模擬考各科答對率），AI 只負責依弱點出 8 題；`clean_questions()` 擋掉格式不對的題、
  打散選項（是非題 TRUE／FALSE／NOT GIVEN 不打散），作答頁不帶答案，交卷由伺服器批改（`AiPractice`）
- **AI 學習報告** `/ai/<id>/report`：給家長與工作人員，數字由程式算，AI 只寫總評、強弱項、兩週計畫、給家長的話；可列印成 PDF。每人每考試每天一份
- **AI 記憶法**：單字卡（`ielts.html`）上的按鈕，口訣、字根、更多例句、搭配詞、易混字
- 快取 `AiCache`：錯題解釋依「題目＋學生的錯誤答案」、記憶法依「課程＋拼字」大家共用，第二個人按不用再呼叫 AI
- 每個學生每天最多 `DAILY_LIMIT`（60）次真的呼叫 AI（快取不算，工作人員登入不限），示範帳號的分享連結也受限，避免被刷爆費用
- **每月次數**（2026-11 使用者要求）：雅思寫作批改、雅思口說評分、韓檢寫作批改、AI 學習報告**每項每月 1 次**（原本 6 次，同一天改成 1 次）
  （`ai_tutor.MONTHLY_LIMIT`、`MONTHLY_FEATURES`，記在 `AiUsage`，台灣時間每月 1 號恢復；空白卷沒呼叫 AI 不算；工作人員不限；
  示範帳號也算）。成績頁用 `{{ ai_quota_note(student.id, 'writing') }}` 顯示本月剩幾次；用完回 429
- **不另開 AI 區域**（2026-11 使用者要求，融進現有功能）：學習報告是主選單歡迎看板右上角的「學習報告」；弱點練習的入口（`.ai-cta`，樣式在 `ui.css`）放在背單字神器首頁、雅思模擬考首頁的錯題本下面、日檢／韓檢模擬考首頁。頁面都要保留「AI 產生的內容可能有錯，以老師講解為準」
- 改完跑 `python tools/check_ai_tutor.py`（在資料庫複本上、用假的 AI 檢查；加 `--real` 用真金鑰實測）

## 學生帳號與開通權限（accounts.py、exams.py）

- 學生在 `/register` 填學號、名字、電子郵件（和原本報名選課系統同一個，表單有提示）、電話、校區（台北・桃園・中壢・南崁・新竹）、
  報名課程（多益全方位、雅思全方位、托福全方位、韓文、日文，可複選）、密碼。送出後 `Student.status='pending'`，什麼都不能用
- 工作人員用管理員密碼登入後台，`/admin`（＝`/admin/students`）是審核開通頁：依學生買的課，每個考試勾「開通」、功能、等級
  （韓檢 1～6 級、日檢 N5～N1）、開通日期、課程開始日、課程結束日。日檢的項目是「A 單字學習與測驗」與「B 模考」（日檢模擬考）。
  托福網站內容還沒開發，只記錄報名；可以加開一般英文、零基礎給學生。也能改學生資料、重設密碼、退回、停用
- 開通內容存在 `Student.access`（JSON，格式見 `exams.py`），判斷都在 `exams.py`：`access_of`、`entry_state`（台灣日期）、
  `features_for`、`exams_for`、`open_levels`。**頁面要判斷權限一律走這幾個函式**
- `accounts.guard()` 在每個請求前檢查：網址（或 API 的 JSON）帶的學生編號要是登入的那個學生；`FEATURE_PATHS` 列出網址開頭對應的功能，
  沒開通就導回選擇考試頁（`?locked=考試名`）。新增帶學生編號的功能頁時，記得把網址開頭加進 `FEATURE_PATHS`。
  樣板用 `has_feature('vocab_quiz')` 藏起沒開通的按鈕
- **示範帳號**（`status='demo'`）：不用登入、全部開放。加上註冊功能前就有的學生（王小明，編號 1）自動變成示範帳號，
  給主管的分享連結 `/dashboard/1` 才不會中斷；後台「退回／停用／示範」分頁可以停用
- 工作人員登入時可以預覽任何學生的畫面；工作人員登入 8 小時失效，學生登入維持 30 天，重設密碼後學生其他裝置的登入失效
- 舊的 `/login?token=…` 照樣可以用（會順便記住登入）

## 後台題庫編輯（admin_bank.py、bank_store.py）—— 目前暫停

- 2026-11 起後台改成學生審核開通，單字與題庫編輯的網址會導回審核頁（`admin.EDITOR_ENABLED = False`）。程式與 `instance/bank_edits/` 都保留，改成 True 就恢復


- **所有讀題庫的程式都要走 `bank_store`**，不要直接開 `listening/`、`reading/` 的檔案，否則讀不到後台改的內容
- 後台存檔寫到 `instance/bank_edits/<技能>/<測驗>/`，原始題庫檔不動，所以 `run.bat` 的 `git pull` 不會衝突；
  每次覆寫前舊版留在 `_history/`（每個檔留 20 份），測驗頁的「還原」會回到原始題庫
- 新增的測驗代號是 LX01、RX01、WX01、SX01（多一個 X，避免和之後進 git 的 L03、R02 撞名），先是草稿，檢查通過才能上架
- 聽力、閱讀存檔時依頁面順序把整回重新編號（`renumber_test`），「Questions 1–6」也一起更新；學生舊成績的分數不變，
  但檢討頁顯示的是新題目
- 存檔檢查：缺答案、答案不是有效選項、圖表數據數量不符等會擋住；答案或引句在原文找不到、沒寫解析只提醒
- 聽力改逐字稿後，測驗頁會出現「重新產生音檔」（背景跑 `tools/make_listening_audio.py`）；地圖題的圖片不能在後台換

## 管理員後台（admin.py）

- 網址 `/admin`，入口在登入頁最下面「工作人員登入」。目前只開學生審核開通（單字、題庫編輯暫停）
- **一定要密碼**：網站會用公開連結分享、學生靠網址編號辨識，不能讓拿到連結的人改資料。
  第一次設定密碼只能在櫃台電腦本機（看 `Cf-Connecting-Ip` 等標頭分辨是不是經過 Cloudflare 通道）；
  密碼雜湊存 `instance/admin.json`、session 金鑰存 `instance/secret_key.txt`（都不進 git）；
  輸錯 5 次鎖 10 分鐘；改密碼後其他裝置的登入失效；表單都帶 csrf
- **刪除不是真的刪**：課程改成 `TRASH:原課程`，所有用課程篩選的查詢自然就看不到，學生的學習紀錄、收藏不動，
  回收區可以救回。不要改成真的刪除，學生紀錄綁在 vocab_id 上
- **後台動過的字不會被 run.bat 的匯入蓋回去**：`Vocabulary.admin_locked` 標記，`src_key` 記下第一次動它之前
  在單字檔裡的「課程|主題|單字」。`import_sheet.py` 依編號、`src_key`、或（課程,主題,單字）找到的字只要是
  admin_locked 就跳過，所以改拼字、換主題、刪除之後都不會被重新加回來；`dedupe_vocab.py` 合併時優先留後台改過的那筆
- 同一課程不能有重複拼字（新增、改拼字、救回時都會檢查）
- 新增的零基礎／一般英文單字沒有 KK 音標，要重跑 `tools/make_pronunciation.py`

## 建構式字彙：字根字首（word_roots.py）

- 2026-11 使用者要求：單字庫拿掉 A–Z 分頁，英文加入「建構式字彙」，學到一個字時同字根、同字首的字會跳出來推薦
- **英文主題不分頁**：A–Z 分頁拿掉後，使用者也不要「1–200、201–311」這種頁碼，整個主題一頁看完（`pages_by_letter()` 只對日韓回 True）；
  日檢、韓檢照舊依字首（あ行、ㄱ）分頁（`pages_by_letter()`）
- 資料在 `morphology/roots.txt`：`種類|字形|意思|單字…`，約 190 組（字首、字根、字尾）。**每組的字都依字源人工挑**，
  不用字串比對自動猜（opportunity、passport 的 port 是「港口」，不算進 port＝拿；important 卻算）。加字前先查字源，改完跑 `python tools/check_word_roots.py`
- 只顯示目前考試字庫裡有的字（`course_words`）；只有英文的考試（雅思、多益、零基礎、一般英文）有，日檢、韓檢不顯示
- **每個英文字點開都有「字的組成」**（2026-11 使用者要求「英文的都要」）：列出字首／字根／字尾和意思，去掉字首或字尾後是字庫裡的字就寫成
  `happiness ＝ happy（快樂的）＋ -ness`（`stem_of`，找字時看所有英文考試的字 `all_english_words`）；沒得拆的字顯示「沒有常見的字首、字根、字尾」。
  -tion、-ment、-ness、-ly 等 20 個常見字尾是先用「去掉字尾後還是一個字」的規則找、再逐字人工刪改，資料寫成 `happiness=happy`；
  超過 `BIG_SUFFIX`（40）字的大字尾只顯示組成，不列同組字、也不推薦整組背
- 單字卡（`ielts.html`）下方「同一家族的字」：`/learn/<id>/roots/api/word/<vocab_id>`，還沒學、不熟的字優先，最多 3 組、每組 8 字；
  單字卡模式可點開，滑卡模式點一下聽發音。滑完一輪的結算頁依剛滑過的字推薦整組接著背（`recommend_api`）
- 單字庫首頁只有「字根字首」按鈕（總覽 `/learn/<id>/roots`）；首頁原本的「同字根推薦」2026-11 使用者要求拿掉，不要加回去；
  每組一頁 `/learn/<id>/roots/<代號>`，可以「一起背這組字」滑卡；從組裡點開的單字卡（`from=root&root=代號`）可以在同一組前後翻

## 單字測驗區怎麼運作

- 介面名稱：單字學習區叫「**單字庫**」、單字測驗區叫「**背單字神器**」（2026-11 改名，按鈕「開始闖關」），新文字請用同一組名稱

- 網址 `/vocab-quiz/<學生id>`，入口在主介面、單字學習區首頁、滑卡結算頁（主題圖鑑頁不放，按鈕只留「開始」和「只練不熟區」）
- **只考學過的字**（`LearningProgress` 有紀錄的，熟或不熟），不熟的優先；同拼字只出一題
- 題型：拼寫、聽寫（`UI.speak` 發音）、例句填空、選意思、選單字。例句填空只給例句裡
  找得到這個字的字（`find_cloze` 會處理 -s／-ed／-ing／-ies 等詞形變化）
  （不規則變化如 knelt、fled 抓不到，例句請用原形或規則變化）；作答後回饋區會顯示完整例句和播放鍵
- 選擇題的干擾選項與答案同語言（中文配中文、英文解釋配英文）
- 交卷時伺服器依存在 `VocabQuizAttempt.questions` 的題目重新批改；**答錯的字自動移到不熟區**
  （`set_progress`），回單字學習區滑卡會優先出現
- 前端即時判分的 `norm()` 要和 `vocab_quiz.normalize()` 保持一致
- 打字題（拼寫、聽寫、例句填空，每個語言都一樣）答錯或按「打不出來？看答案」：輸入框上方先顯示正確答案，
  輸入框清空讓學生照著再打一次，打對自動下一題（也可以按「跳過」）。**成績照第一次算**，看答案送出的是空白，算答錯、進不熟區
- 英文打字題的底線提示：題目 JSON 的 `mask`（`letter_mask()`，一個字母一條底線，空白、連字號照原樣；拼寫與填空給第一個字母，
  聽寫不給），前端邊打邊把字母填進底線。日文、韓文沒有 `mask`，照舊用假名數與子音提示

## 聽力題庫怎麼運作

**核心原則：音檔由逐字稿產生，所以音檔內容與題目必定一致。** 不要手動配音檔。

每個 Part 的 JSON 有三塊：

- `cues` — 逐字稿。`v` 是說話者代號（`narrator` / `f1` / `m1` …），
  `v: "pause"` 代表停頓，`t` 是秒數
- `groups` — 題組。型別有 `gapfill`（表格或筆記填空，用 `{3}` 標記空格）、
  `mcq`（單選）、`matching`（配對，選項 A–F）、`map`（地圖題，配 SVG 圖）
- `questions` — 每題的 `answers`（可接受答案陣列）、`explain`（解析，可含 HTML）、
  `quote`（原文引用）

### 新增一回測驗

1. 在 `listening/` 下建 `L02/`，寫 `meta.json` 與 `part1~4.json`
2. 在 `listening/tests.json` 加一筆
3. 跑 `python tools/check_listening.py` — **必過才能繼續**。它會驗證每題答案都
   真的出現在對應 Part 的逐字稿裡、題號 1–40 完整、選項字母有效
4. 跑 `python tools/make_listening_audio.py L02` 產生音檔（每回約 4 分鐘）

### 音檔

用 `edge-tts`（免註冊、免金鑰，就是 Edge 那套微軟神經語音）。
語音對應表在 `tools/make_listening_audio.py` 的 `VOICES`。

注意：**微軟的英式語音只有 Ryan 和 Thomas 兩個男聲**。需要第二個男性角色時
用其他英語系口音（愛爾蘭 Connor、紐西蘭 Mitchell、澳洲 William）——雅思聽力
本來就混用口音，這樣反而更真實。腳本會在合成前先驗證語音存在。

產生的 mp3 不進 git（`.gitignore` 排除 `static/audio/listening/`），
因為 10 回約 80MB，而且隨時可以重新產生。

## 閱讀題庫怎麼運作

每篇文章一個 JSON（`reading/R01/passage1.json`…），三塊內容：

- `paragraphs` — 文章段落，`label` 是段落字母（A、B…，不需要時留空字串）
- `groups` — 題組。型別有 `tfng`（TRUE/FALSE/NOT GIVEN）、`ynng`（YES/NO/NOT GIVEN）、
  `mcq`（單選 A–D）、`matching`（配對）、`headings`（段落標題 i–x）、
  `gapfill`（筆記／句子／摘要填空，用 `{3}` 標空格；有 `options` 時變成摘要選詞下拉選單）
- `questions` — 與聽力相同：`answers`、`explain`、`quote`（引句必須逐字出自同一篇文章）

新增一回：建 `reading/R02/`、在 `reading/tests.json` 加一筆，然後跑
`python tools/check_reading.py`，**必過**（填空題的第一個答案要逐字出自文章，後面可列其他可接受的拼法）。正式考試比照：3 篇共 40 題（13／13／14），
每篇約 700–900 字，題型混搭，NOT GIVEN 與干擾項的陷阱要在解析裡點明。

## 寫作題庫與 AI 老師

- 作答頁 `write_test.html` 比照雅思電腦考：上方考生列與倒數 60 分鐘、左題目右作答、
  下方 Part 1／Part 2 切換、字數即時統計、關閉拼字檢查、時間到自動交卷。
  草稿每 15 秒存到 `WritingDraft`，本機另有 localStorage 暫存
- `task1.json` 的 `chart` 是圖表資料（`line` 或 `bar`），由 `writing_bank.chart_svg` 畫圖，
  同一份資料也以文字表格交給 AI 老師，所以 AI 看到的數據與學生看到的圖必定一致
- 交卷存成 `WritingSubmission`，結果頁再呼叫 `/grade` 請 AI 批改（兩個 Task 同時送），
  結果存進資料庫，重開不會重複扣費
- **免費額度用完自動改用付費**：主要金鑰是免費 Gemini，回 429 時（`writing_bank.FreeQuotaError`）
  `writing_bank.run_ai` 改用 `paid_config()` 的備用付費金鑰（`ai_key_paid.txt`，雙擊 `set_ai_paid_key.bat` 設定；
  可以是 Claude 或有開帳單的 Gemini 專案）再問一次，每次記在 `instance/ai_paid_log.txt`。所有 AI 呼叫都要走 `run_ai`／`ask_json`；
  備用是 Claude 時口說作答頁也會開瀏覽器語音辨識（Claude 聽不到錄音）
- AI 老師支援兩家，依金鑰開頭自動判斷：Google Gemini（`AIza` 或新格式 `AQ.`，免費額度，模型依序試
  `GEMINI_MODELS`，可用環境變數 `GEMINI_MODEL` 指定）與 Anthropic Claude（`sk-ant-`，
  模型 `claude-sonnet-5-5`，中階、比 Opus 便宜一半；AI 學習教練的錯題解釋、練習題、記憶法用 `ask_json(light=True)` 走最便宜的 `claude-haiku-5-5`，學習報告維持 Sonnet）。金鑰讀 `ai_key.txt`，其次是環境變數 `GEMINI_API_KEY`／
  `ANTHROPIC_API_KEY`。兩家共用同一份評分規則 `writing_bank.SYSTEM_PROMPT`（刻意從嚴）與
  JSON 輸出格式；
  Task 分數與總分（Task 2 兩倍權重）在 Python 端計算，不讓 AI 自己算
- 頁面一定要保留「AI 老師的評分不等於真實考試，只是模擬」的提示

## 口說題庫與 AI 老師

- 每回一個 `speaking/S01/test.json`：`part1`（3 個話題，第一個固定是住所或工作／學業，每個 3–4 題）、
  `part2`（`cue` 題卡、`points` 三個 You should say、`final` and explain…、`followups` 收尾問題）、
  `part3`（2 個延伸 Part 2 的抽象議題，每個 3 題）。新增一回後在 `speaking/tests.json` 加一筆
- `speaking_bank.build_steps` 把題庫展開成考官逐句台詞（含官方流程的開場、轉場、Part 2 指示語），
  作答頁 `speak_test.html` 用瀏覽器語音唸出（`UI.speak`，Edge 最自然）。題目文字預設模糊，比照考場只用聽的
- 每題用 MediaRecorder 錄一段（32kbps），有上限秒數（`LIMITS`，Part 2 到 2 分鐘自動停）；Part 2 有 1 分鐘準備與筆記。
  交卷時一次上傳全部錄音，存在 `instance/speaking_audio/<交卷 id>/`（不進 git），紀錄在 `SpeakingSubmission`
- AI 老師依金鑰自動選：**Gemini 直接聽錄音**（自己做逐字稿、發音真的有聽）；
  **Claude 聽不到音檔**，作答時改用瀏覽器語音辨識（Edge 送微軟、Chrome 送 Google）產生逐字稿，發音分數標示「推估」
- 四項標準 FC／LR／GRA／P 由 AI 給整數 Band，總分在 Python 端平均後進位
- 頁面一定要保留「AI 評分不等於真實考試，只是模擬」；用 Gemini 時要提醒「免費方案的內容可能被 Google 使用」，
  並請學生不要在錄音裡說個資（問姓名時用英文名或化名）
- 麥克風只能在 https 或本機網址（127.0.0.1）使用：手機要用 `share.bat` 的 https 網址

## 出題要求

雅思聽說讀寫目標各 10 回（2026-11 起逐回增加，寫好一回上線一回）。**各回內容不能重複**：
`tools/check_ielts_unique.py` 比對主題、逐字稿與文章句子、題幹、選項組、填空句、地圖地點、寫作題目（關鍵字重疊太高也擋）、
口說每一題與話題，聽力與閱讀之間也互相比。出新的一回前先看各 `tests.json` 的主題避開，寫完必跑。

題目全部原創，**不要**從任何市售教材或考古題轉錄內容。
（專案原本有一回從採購書轉錄的 Test 3，已在 PR #15 全部移除。資料庫裡
`test_key='test3'` 的舊紀錄沒刪，但一律從成績與錯題本過濾，見
`RETIRED_TEST_KEYS`。）

出題時比照正式雅思：

- Part 1 日常對話（表格填空）、Part 2 日常獨白（單選＋地圖）、
  Part 3 學術對話（單選＋配對）、Part 4 學術講座（筆記填空）
- 每個 Part 約 700 字逐字稿、10 題，整回約 24 分鐘
- **一定要埋干擾項**：先說一個答案再更正、用 `but` 轉折、被否定的選項。
  解析要明確點出陷阱在哪，這是學生最需要的部分
- 答案要能在逐字稿中逐字找到（`check_listening.py` 會驗）

## 全站視覺與色系

- 顏色全部來自 `static/theme.css` 的變數：主色 `--primary`（雅思紫色學院風，各考試各一色）＋同色系深色 `--deep`。
  **深色只佔小部分**（標題字、返回鈕、橫幅文字），不要拿來塗大面積的底色；零基礎是橘配咖啡。
  其他變數：標題橫幅 `--hero`、文字 `--ink`／`--muted`、
  框線 `--line`、底色 `--bg`，以及狀態色 `--ok`（對）、`--bad`（錯）、`--warn`（提醒）、`--star`（收藏），各有 `-50` 淺底與 `-ink` 深字
- 標題橫幅是淺色平塗（`--hero`）配深色字（`--hero-ink` = `--deep`），**不用漸層**；層次**不用模糊陰影**，改用邊框疊：
  一般卡片 `box-shadow: var(--edge)`、滑過或選取 `var(--edge-raised)`、橫幅 `var(--edge-hero)`、浮動面板 `var(--edge-pop)`
- **不用 emoji**，圖示一律用線條圖示：樣板寫 `{{ icon('book-open') }}`，JS 寫 `UI.icon('book-open')`，
  圖示在 `static/icons.svg`（缺的就照格式加一個 symbol）。✓ ✗ ★ ☆ 這類文字符號可以照用
- 新頁面或新樣式**不要寫死色碼**，一律用 `var(--…)`；白色 `#fff` 可以直接寫
- 新樣板的 `<head>` 第一個樣式表要是 `theme.css`，再接 `ui.css`／`exam.css`
- 考試作答頁（聽讀寫說）維持比照雅思電腦考的版面，只套色系
- 寫作 PDF 輸出畫在 canvas 上，`writing_export.js` 用 `themeColor()` 讀同一組變數

## 開發慣例

- 改完一定要實測。本機起 server 後用 `curl` 確認路由、實際送出表單驗證批改
- 有畫面的改動要截圖看過（無頭 Chrome `--screenshot`）
- 每個功能開一個 branch，開 PR 合併進 main，不要直接推 main
- commit 訊息用繁體中文，說明「為什麼改」而不只是「改了什麼」
- **不要用行號範圍刪除大段程式碼**。曾經這樣移除 Test 3，結果把夾在中間的
  單字學習函式一起刪掉（PR #15 後的 hotfix 829156d）。用函式名稱定位

## 目前進度

- ✅ 單字學習與圖鑑（滑卡、熟／不熟分區、收藏、音效動畫）；搜尋在單字學習區首頁，跨主題邊打邊搜，拼法相近（打錯字）也找得到，中文意思字不連在一起也算（`learn_search`）；主題圖鑑裡還沒學的字直接顯示單字與意思（灰色卡片，可點開單字卡），熟（綠）、不熟（橘）；單字卡（`learn_word`，`ielts.html` 的 view 模式）從圖鑑、收藏（from=favorites）、搜尋（from=search＆q）點進來都帶整份清單，**可以直接滑卡**（右滑熟、左滑不熟、鍵盤左右鍵也是，標完自動換下一張），另有「上一個／下一個」只翻不標，順序和來源頁一樣
- ✅ 雅思高頻字庫（原 11，4,324 字）拆進各主題：主題字庫 01–10、12，加上新增的 13 人物性格與情緒、14 日常生活與物品、
  15 通用核心字彙（放不進特定主題的常用字）。改的是 `vocab_master.xlsx` 的「主題」欄，靠「編號」原地更新，學習紀錄不動；
  和主題原本重複的約 240 字放進同一主題，`theme_words` 同拼字只顯示一張卡、字數也只算一次
- ✅ 雅思字庫每個字都有中文意思、詞性、原創例句與中譯（原 11 的 4,080 字原本只有英文解釋，2026-11 補齊，見 `ielts/README.md`）
- ✅ 雅思字庫擴充到 **7,037 個不重複單字**（2026-11 從多益、一般英文字庫補 2,004 字＋新寫 33 字，跨考試重複沒關係，見 `ielts/README.md`）；先前到 5,000 字：從 NGSL 補 488 字（原創中文意思與例句，CC BY-SA 4.0），
  重複字合併成一筆。`run.bat` 匯入後會跑 `tools/dedupe_vocab.py`：同課程同拼字只留一筆（內容最完整、編號最小），
  學習紀錄、收藏、測驗作答與題目 JSON 都轉到留下的那筆。**雅思字庫不能有重複字**，換主題改「主題」欄就好
- ✅ 單字測驗區（拼寫、聽寫、例句填空、選擇題；答錯回不熟區）
- ✅ 建構式字彙：英文字根字首約 190 組（依字源人工挑字），單字卡顯示同家族的字並推薦整組背；英文單字庫拿掉 A–Z 分頁
- ✅ 考試類型選擇頁；多益區（藍色）：5,005 字單字學習＋單字測驗（TSL＋BSL＋NGSL）
- ✅ 英文零基礎（橘色）：學發音（單字＋KK 音標＋正常／慢速發音），加上 2,006 字單字學習＋單字測驗
- ✅ 一般英文（青綠色）：4,032 個日常生活字單字學習＋單字測驗（和零基礎不重複）
- ✅ 管理員後台：單字新增、編輯、刪除（回收區可救回），密碼保護
- ✅ 後台編輯題庫（聽說讀寫）：新增、編輯、刪除題目與整份測驗，草稿上架、回收區可救回
- ✅ 韓檢（莓果紅）：1～6 級分級字庫＋單字學習＋單字測驗（韓語發音、韓文鍵盤、逐級開通的資料欄位）
  - 1～6 級全部完成（6,630 字：795／1,055／936／1,409／1,537／898）
- ✅ 日檢（抹茶綠）：N5～N1 分級字庫＋單字學習＋單字測驗（讀音、日語發音、羅馬拼音輸入、逐級開通）
  - N5～N1 完成，共 10,097 字（682＋774＋2,420＋3,260＋2,961）：Waller 字表 7,430 字＋JMdict 常用字補充 2,667 字；2026-11 依常用度與漢字難度重新分級，1,240 字換等級（見 `jlpt/README.md`）。
    換等級只要改 CSV 的「主題」，`import_sheet.py` 會把同課程唯一的同拼字搬過去，不會多出重複字
- ✅ 學生註冊／登入與工作人員審核開通（依課程開功能、等級、開通與課程日期）；原本的單字、題庫編輯後台暫停
- ✅ 韓檢模擬考 TOPIK I、TOPIK II 各十回（2026-11 從三回逐回補到十回，每回 70／104 題，各回題目不重複；交卷顯示正解與解析、總分與級數；寫作 AI 批改；聽力音檔在櫃台電腦雙擊 `topik_audio.bat` 產生）
- ✅ 日檢模擬考 N5～N1 各 10 回（共 50 回，每回 67／85／102／105／107 題，各回題目不重複）（交卷顯示正解與解析、估計分數；聽解音檔在櫃台電腦雙擊 `jlpt_audio.bat` 產生）
- ⬜ 托福（後台已有開關，內容還沒開發）
- ✅ 聽力題庫 **10 回**（L01–L10 完成，各 40 題解析；音檔在櫃台電腦雙擊 `listening_audio.bat` 產生）
- ✅ 閱讀題庫 **10 回**（R01–R10 完成，各 3 篇 40 題含解析；主題不重複，也避開聽力題庫的主題）
- ✅ 寫作題庫 **10 回**（W01–W10 完成；Task 1 線圖與長條圖輪替、Task 2 題型涵蓋同意與否／正反討論／原因對策／雙問題，主題不重複也避開聽力閱讀；電腦考作答介面＋AI 老師批改，作答可輸出 PDF／圖片）
- ✅ 口說題庫 **10 回**（S01–S10；Part 1–3 話題互不重複；比照官方 Part 1–3 流程、錄音作答、AI 老師辨識語音並依四項標準評分）

## 常用指令

```bash
python tools/check_listening.py          # 檢查題庫一致性（改完題目必跑）
python tools/check_ielts_unique.py       # 檢查雅思聽說讀寫各回內容不重複（出新的一回必跑）
python tools/make_listening_audio.py L01 # 產生某回音檔
python tools/make_listening_audio.py --voices   # 列出可用語音
python tools/check_jlpt_mock.py          # 檢查日檢模擬考題庫（改完題目必跑）
python tools/make_jlpt_audio.py          # 產生日檢模擬考聽解音檔
python tools/check_topik_mock.py         # 檢查韓檢模擬考題庫（改完題目必跑）
python tools/check_word_roots.py         # 檢查字根字首資料（改完 morphology/roots.txt 必跑）
python tools/make_topik_audio.py         # 產生韓檢模擬考聽力音檔
python tools/check_ai_tutor.py           # 檢查 AI 學習教練（假 AI，不花錢；--real 用真金鑰）
python app.py                            # 直接起 server（平常用 run.bat）
```
