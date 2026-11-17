# 一般英文（General English）單字資料

## 檔案

- `general_vocab.csv` — 網站實際匯入的一般英文單字（4,032 字）。欄位和 `vocab_master.xlsx` 相同，
  `run.bat` 會用 `import_sheet.py general\general_vocab.csv` 匯入，課程是 `GENERAL`
- 主題 G01–G15（人際與家庭、居家生活…通用名詞與概念），定義在 `app.py` 的 `OFFICIAL_THEMES`
- 定位是「零基礎之後的下一步」：和零基礎（`basic/basic_vocab.csv`）**完全不重複**，
  兩區加起來約 6,000 個日常生活常用字

## 怎麼選字

與零基礎相同的兩份開放字頻資料：**NGSL 1.01** 的排名，加上 **OpenSubtitles 2018 英文字頻表**
（電影與影集字幕，最接近日常口語）。依頻率由高到低，扣掉零基礎已收的字，
再去掉人名、地名、縮寫、粗話與不適合學生的字。

## 來源與授權

- Browne, C., Culligan, B., & Phillips, J. *The New General Service List.* <https://www.newgeneralservicelist.com/new-general-service-list>
- Dave, H. *FrequencyWords*（OpenSubtitles 2018 字頻）<https://github.com/hermitdave/FrequencyWords>

兩份來源都是 **CC BY-SA 4.0**（<https://creativecommons.org/licenses/by-sa/4.0/>），
所以 `general_vocab.csv`（單字清單＋本專案的主題分類、詞性、中文意思、原創例句與中譯）整份以 **CC BY-SA 4.0** 授權。

## 本專案做的改動

- **中文意思、詞性、例句、例句中譯**：全部自行撰寫，例句是原創的生活情境短句，沒有引用市售教材
- **例句一定含有這個字**（或它的詞形變化），單字測驗的例句填空才出得了題
