# 補習班雅思測驗系統

給 Claude 的專案說明。接手前請先讀完這份。

## 這是什麼

一套給補習班學生用的雅思練習網站，用 Flask + SQLite 寫成，跑在補習班櫃台那台
Windows 電腦上（`C:\Users\TLC-5\Desktop\quiz-system`），需要給主管或遠端學生看時，
用 `share.bat` 開 Cloudflare 臨時通道產生公開網址。

兩大功能：

1. **單字學習與圖鑑** — 依主題滑卡學單字（右滑熟、左滑不熟），4756 個單字
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

## 程式結構

```
app.py              Flask 主程式：資料模型、單字學習、測驗區路由
listening_bank.py   聽力題庫的載入、渲染與批改
listening/          聽力題庫資料（每回一個資料夾）
  tests.json        題庫清單
  L01/meta.json     該回的標題與說明
  L01/part1~4.json  逐字稿、題組、答案、解析
templates/          Jinja 樣板
static/ui.js        共用：音效、動畫、英文發音挑選
static/exam.css     測驗頁共用樣式
tools/              產生音檔與檢查題庫的腳本
import_sheet.py     從 vocab_master.xlsx 匯入單字（run.bat 會跑）
```

資料模型都在 `app.py` 上半部：`Student`、`Vocabulary`、`LearningProgress`、
`Favorite`、`TestAttempt`、`TestAnswer`、`TestMistake`、`WritingDraft`。
啟動時會自動補欄位（`PRAGMA table_info` 檢查後 `ALTER TABLE`），不用寫 migration。

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

## 開發慣例

- 改完一定要實測。本機起 server 後用 `curl` 確認路由、實際送出表單驗證批改
- 有畫面的改動要截圖看過（無頭 Chrome `--screenshot`）
- 每個功能開一個 branch，開 PR 合併進 main，不要直接推 main
- commit 訊息用繁體中文，說明「為什麼改」而不只是「改了什麼」
- **不要用行號範圍刪除大段程式碼**。曾經這樣移除 Test 3，結果把夾在中間的
  單字學習函式一起刪掉（PR #15 後的 hotfix 829156d）。用函式名稱定位

## 目前進度

- ✅ 單字學習與圖鑑（滑卡、熟／不熟分區、收藏、音效動畫）
- ✅ 聽力題庫 **1 / 10 回**（L01 完成，含音檔與 40 題解析）
- ⬜ 聽力 L02–L10
- ⬜ 閱讀題庫（可自動批改，建議優先做）
- ⬜ 寫作題庫（作答可輸出 PDF／圖片的功能已完成，缺題目）
- ⬜ 口說題庫

## 常用指令

```bash
python tools/check_listening.py          # 檢查題庫一致性（改完題目必跑）
python tools/make_listening_audio.py L01 # 產生某回音檔
python tools/make_listening_audio.py --voices   # 列出可用語音
python app.py                            # 直接起 server（平常用 run.bat）
```
