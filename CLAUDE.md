# 補習班雅思測驗系統

給 Claude 的專案說明。接手前請先讀完這份。

## 這是什麼

一套給補習班學生用的雅思練習網站，用 Flask + SQLite 寫成，跑在補習班櫃台那台
Windows 電腦上（`C:\Users\TLC-5\Desktop\quiz-system`），需要給主管或遠端學生看時，
用 `share.bat` 開 Cloudflare 臨時通道產生公開網址。

兩大功能：

1. **單字學習與圖鑑** — 依主題滑卡學單字（右滑熟、左滑不熟），雅思 5,000 個不重複單字，分在 01–10、12–15 共 14 個主題（來源見 `ielts/README.md`）
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
`static/ui.js` 會自動挑最好的語音，挑不到神經語音時會提示改用 Edge。

其他裝置（**特別是 Android 的 Chrome：連續播放時會一直唸同一個字**）改播伺服器產生的音檔：
`UI.speak` 在瀏覽器沒有神經語音或是 Android 時，改用 `/tts?text=…`（`word_audio.py` 用 edge-tts 產生並快取），
產生失敗才退回瀏覽器語音。所以櫃台電腦要能連上微軟語音服務，`run.bat` 會裝 `edge-tts`。

## 程式結構

```
app.py              Flask 主程式：資料模型、單字學習、測驗區路由
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
set_ai_key.bat      在櫃台電腦設定 AI 老師的 API 金鑰（存進 ai_key.txt，不進 git）
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
phonics.py          英文零基礎的 ABC 字母、自然發音、聽音選字教學頁 /phonics/<學生id>（資料寫在檔案裡）
basic/、general/    英文零基礎、一般英文的單字 CSV 與來源授權說明（README.md）
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
- 多益單字在 `toeic/toeic_vocab.csv`（TSL＋BSL＋NGSL 三份開放字表共 4,002 字，CC BY-SA 4.0，來源與改動見 `toeic/README.md`），
  `run.bat` 會匯入
- 零基礎單字在 `basic/basic_vocab.csv`（2,006 字，國中小程度、例句刻意很短），一般英文在 `general/general_vocab.csv`
  （4,032 個日常生活字）。**兩區互不重複**，各自也沒有重複字；來源是 NGSL＋OpenSubtitles 字頻（CC BY-SA 4.0），
  中文意思與例句原創，見各資料夾的 `README.md`。`run.bat` 會匯入。加字時兩份都要檢查不重複
- ABC 與發音教學（`phonics.py`）：電腦語音唸不出單獨的 /k/ 這種音，所以字母的音用「代表單字」示範，
  加注音近似音與嘴型說明；單字寫成 `"c.a.t"` 拆格，`*` 開頭的格子不發音（Magic e）

## 單字測驗區怎麼運作

- 網址 `/vocab-quiz/<學生id>`，入口在主介面、單字學習區首頁、各主題圖鑑、滑卡結算頁
- **只考學過的字**（`LearningProgress` 有紀錄的，熟或不熟），不熟的優先；同拼字只出一題
- 題型：拼寫、聽寫（`UI.speak` 發音）、例句填空、選意思、選單字。例句填空只給例句裡
  找得到這個字的字（`find_cloze` 會處理 -s／-ed／-ing／-ies 等詞形變化）
- 選擇題的干擾選項與答案同語言（中文配中文、英文解釋配英文）
- 交卷時伺服器依存在 `VocabQuizAttempt.questions` 的題目重新批改；**答錯的字自動移到不熟區**
  （`set_progress`），回單字學習區滑卡會優先出現
- 前端即時判分的 `norm()` 要和 `vocab_quiz.normalize()` 保持一致

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
`python tools/check_reading.py`，**必過**。正式考試比照：3 篇共 40 題（13／13／14），
每篇約 700–900 字，題型混搭，NOT GIVEN 與干擾項的陷阱要在解析裡點明。

## 寫作題庫與 AI 老師

- 作答頁 `write_test.html` 比照雅思電腦考：上方考生列與倒數 60 分鐘、左題目右作答、
  下方 Part 1／Part 2 切換、字數即時統計、關閉拼字檢查、時間到自動交卷。
  草稿每 15 秒存到 `WritingDraft`，本機另有 localStorage 暫存
- `task1.json` 的 `chart` 是圖表資料（`line` 或 `bar`），由 `writing_bank.chart_svg` 畫圖，
  同一份資料也以文字表格交給 AI 老師，所以 AI 看到的數據與學生看到的圖必定一致
- 交卷存成 `WritingSubmission`，結果頁再呼叫 `/grade` 請 AI 批改（兩個 Task 同時送），
  結果存進資料庫，重開不會重複扣費
- AI 老師支援兩家，依金鑰開頭自動判斷：Google Gemini（`AIza` 或新格式 `AQ.`，免費額度，模型依序試
  `GEMINI_MODELS`，可用環境變數 `GEMINI_MODEL` 指定）與 Anthropic Claude（`sk-ant-`，
  模型 `claude-opus-5-5`）。金鑰讀 `ai_key.txt`，其次是環境變數 `GEMINI_API_KEY`／
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

- 顏色全部來自 `static/theme.css` 的變數：主色 `--primary`（紫色學院風）、標題橫幅 `--hero`、文字 `--ink`／`--muted`、
  框線 `--line`、底色 `--bg`，以及狀態色 `--ok`（對）、`--bad`（錯）、`--warn`（提醒）、`--star`（收藏），各有 `-50` 淺底與 `-ink` 深字
- 標題橫幅是淺紫平塗（`--hero`）配深紫字，**不用漸層**；層次**不用模糊陰影**，改用邊框疊：
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

- ✅ 單字學習與圖鑑（滑卡、熟／不熟分區、收藏、音效動畫）
- ✅ 雅思高頻字庫（原 11，4,324 字）拆進各主題：主題字庫 01–10、12，加上新增的 13 人物性格與情緒、14 日常生活與物品、
  15 通用核心字彙（放不進特定主題的常用字）。改的是 `vocab_master.xlsx` 的「主題」欄，靠「編號」原地更新，學習紀錄不動；
  和主題原本重複的約 240 字放進同一主題，`theme_words` 同拼字只顯示一張卡、字數也只算一次
- ✅ 雅思字庫擴充到 **5,000 個不重複單字**：從 NGSL 補 488 字（原創中文意思與例句，CC BY-SA 4.0），
  重複字合併成一筆。`run.bat` 匯入後會跑 `tools/dedupe_vocab.py`：同課程同拼字只留一筆（內容最完整、編號最小），
  學習紀錄、收藏、測驗作答與題目 JSON 都轉到留下的那筆。**雅思字庫不能有重複字**，換主題改「主題」欄就好
- ✅ 單字測驗區（拼寫、聽寫、例句填空、選擇題；答錯回不熟區）
- ✅ 考試類型選擇頁；多益區（藍色）：4,002 字單字學習＋單字測驗（TSL＋BSL＋NGSL）
- ✅ 英文零基礎（橘色）：ABC 字母、自然發音 6 課、聽音選字，加上 2,006 字單字學習＋單字測驗
- ✅ 一般英文（青綠色）：4,032 個日常生活字單字學習＋單字測驗（和零基礎不重複）
- ⬜ 韓檢、日檢；學生登入與後台開通權限
- ✅ 聽力題庫 **2 / 10 回**（L01、L02 完成，各 40 題解析；音檔在櫃台電腦雙擊 `listening_audio.bat` 產生）
- ⬜ 聽力 L03–L10
- ✅ 閱讀題庫 **1 / 10 回**（R01 完成，3 篇 40 題含解析）
- ⬜ 閱讀 R02–R10
- ✅ 寫作題庫 **1 / 10 回**（W01 完成；電腦考作答介面＋AI 老師批改，作答可輸出 PDF／圖片）
- ⬜ 寫作 W02–W10
- ✅ 口說題庫 **3 / 10 回**（S01–S03；比照官方 Part 1–3 流程、錄音作答、AI 老師辨識語音並依四項標準評分）
- ⬜ 口說 S04–S10

## 常用指令

```bash
python tools/check_listening.py          # 檢查題庫一致性（改完題目必跑）
python tools/make_listening_audio.py L01 # 產生某回音檔
python tools/make_listening_audio.py --voices   # 列出可用語音
python app.py                            # 直接起 server（平常用 run.bat）
```
