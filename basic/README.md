# 英文零基礎（Basic English）單字資料

## 檔案

- `basic_vocab.csv` — 網站實際匯入的零基礎單字（2,006 字，國中小程度）。欄位和 `vocab_master.xlsx` 相同
  （課程、主題、程度、單字、詞性、中文意思、英文解釋、例句、例句中譯），`run.bat` 會用
  `import_sheet.py basic\basic_vocab.csv` 匯入，課程是 `BASIC`，程度都是「基礎級」
- 主題 B01–B13（數字與時間、家人與人物…常用小字），定義在 `app.py` 的 `OFFICIAL_THEMES`
- 和一般英文（`general/general_vocab.csv`）**完全不重複**，同一區裡也沒有重複字

## 怎麼選字

1. 以 **New General Service List（NGSL）1.01** 的頻率排名為主（最常用的英文字）
2. 再參考 **OpenSubtitles 2018 英文字頻表**（hermitdave/FrequencyWords 的 `en_50k`，電影與影集字幕的口語字頻），
   把日常口語常用、但 NGSL 排名較後面的字往前排
3. 加上國中小課本常見的生活主題字（顏色、動物、食物、文具、家人稱呼等），由本專案自行挑選
4. 人名、地名、粗話與不適合學生的字一律不收

沒有使用教育部「國中小 2000 基本字詞」：那份清單的授權條款不明確，所以只用上面兩份開放授權的資料排序，
主題與字的取捨是本專案自己做的。

## 來源與授權

- Browne, C., Culligan, B., & Phillips, J. *The New General Service List.* <https://www.newgeneralservicelist.com/new-general-service-list>
  （CC BY-SA 4.0，原始檔在 `toeic/NGSL_1.01_stats.csv`）
- Dave, H. *FrequencyWords*（OpenSubtitles 2018 字頻）<https://github.com/hermitdave/FrequencyWords>
  （字頻內容 CC BY-SA 4.0，程式 MIT）

兩份來源都是 **創用 CC 姓名標示－相同方式分享 4.0 國際（CC BY-SA 4.0）**：
<https://creativecommons.org/licenses/by-sa/4.0/>。因此 `basic_vocab.csv`
（單字清單＋本專案加上的主題分類、詞性、中文意思、原創例句與中譯）整份以 **CC BY-SA 4.0** 授權。

## 本專案做的改動

- **中文意思、詞性、例句、例句中譯**：全部自行撰寫。零基礎的例句刻意寫得很短、只用簡單的字，
  沒有引用市售教材
- **例句一定含有這個字**（或它的 -s／-ed／-ing 變化），單字測驗的例句填空才出得了題
