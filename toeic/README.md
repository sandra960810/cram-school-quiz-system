# 多益（TOEIC）單字資料

## 檔案

- `toeic_vocab.csv` — 網站實際匯入的多益單字（4,002 字）。欄位和 `vocab_master.xlsx` 相同
  （課程、主題、程度、單字、詞性、中文意思、英文解釋、例句、例句中譯），`run.bat` 會用
  `import_sheet.py toeic\toeic_vocab.csv` 匯入，課程是 `TOEIC`
- `TSL_1.1_stats.csv`、`BSL_1.01_stats.csv`、`NGSL_1.01_stats.csv` — 三份單字來源的原始清單
  （含頻率排名），留存做對照

## 來源與授權

單字清單來自同一組作者的三份開放字表：

| 字表 | 收進來的字 | 說明 |
|---|---|---|
| **TOEIC Service List（TSL）1.1** | 第一批 1,259 字 | 多益考題裡常見、但一般字表沒有的字 |
| **Business Service List（BSL）1.01** | 996 字 | 商業文件與新聞常用字，只收 TSL 沒有的 |
| **New General Service List（NGSL）1.01** | 1,747 字 | 最常用的 2,800 個英文字。TSL 與 BSL 都是 NGSL 的「補充清單」，本身不含 customer、employee、budget 這類最核心的字，所以從 NGSL 補進職場常用的字 |

- Browne, C., & Culligan, B. *The TOEIC Service List.* <https://www.newgeneralservicelist.com/toeic-service-list>
- Browne, C., & Culligan, B. *The Business Service List.* <https://www.newgeneralservicelist.com/business-service-list>
- Browne, C., Culligan, B., & Phillips, J. *The New General Service List.* <https://www.newgeneralservicelist.com/new-general-service-list>

（原始檔取自 [antdurrant/word.lists](https://github.com/antdurrant/word.lists) 收錄的版本；
NGSL 原檔是 xlsx，這裡只留下 NGSL 本體的字、排名與 SFI 三欄）

三份字表都以 **創用 CC 姓名標示－相同方式分享 4.0 國際（CC BY-SA 4.0）** 授權釋出：
<https://creativecommons.org/licenses/by-sa/4.0/>，允許商業使用與改作，但要標示原作者，
改作後的資料也要以相同授權分享。

因此 `toeic_vocab.csv`（單字清單＋本專案加上的主題分類、詞性、中文意思、原創例句與中譯）
整份以 **CC BY-SA 4.0** 授權。

## 本專案做的改動

- **主題分類**：自訂 12 個職場情境主題（T01 辦公室與行政 … T12 通用商務字彙），每個字歸一類
- **中文意思、詞性、例句、例句中譯**：全部自行撰寫，例句都是原創的職場情境句子，沒有引用市售教材
- **詞形**：TSL 為了統計把部分字還原成字根，學習時不自然，改回常用形式：
  headquarter→headquarters、unauthorize→unauthorized、housekeep→housekeeping、
  outdate→outdated、inexperience→inexperienced、overcrowd→overcrowded、pant→pants、
  dissatisfy→dissatisfied、renown→renowned、accustom→accustomed、fundraise→fundraising
- **挑字**：BSL 與 NGSL 裡偏政治、軍事、犯罪、宗教或純學術的字（例如 parliament、missile、
  coefficient）不收，NGSL 裡 the、be、have 這類虛詞也不收，只留職場與日常會用到的字
- **擴充時不動舊資料**：第二批（BSL＋NGSL）只接在檔案後面，原本 1,259 字一字未改，學生的學習紀錄照常保留
- 程度一律標「不分級」（TSL 依考試出現頻率排序，不是難度分級）

修改字卡內容直接改 `toeic_vocab.csv` 再雙擊 `run.bat` 即可，匯入只會新增或更新，不會刪除學生進度。
