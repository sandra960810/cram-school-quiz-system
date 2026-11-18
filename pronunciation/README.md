# 單字音標資料

`kk.json`：零基礎與一般英文單字的 KK 音標、發音音節、重音與拼字音節，給「單字發音教學」頁（`/phonics/<學生id>`）用。

```json
"banana": {"kk": "bəˈnænə", "syl": ["bə", "næ", "nə"], "stress": [0, 1, 0], "spell": ["ba", "na", "na"]}
```

- `stress`：1 是主重音、2 是次重音、0 不重讀
- `spell`：拼字拆音節；音節數和發音對不上時不提供，頁面就顯示整個字

## 怎麼產生

```bash
python tools/make_pronunciation.py 路徑/cmudict.dict
```

加了新單字（`basic/basic_vocab.csv`、`general/general_vocab.csv`）後重跑一次即可。

- 音標：**CMU Pronouncing Dictionary**（<https://github.com/cmusphinx/cmudict>，美式發音），
  ARPAbet 轉成台灣課本常用的 KK 音標。授權是 BSD 式條款，可自由使用與改作，需保留版權聲明：
  Copyright (C) 1993-2015 Carnegie Mellon University. All rights reserved.
- 拼字斷音節：**pyphen**（LibreOffice 的英文斷字字典），對不上時改用簡單的拼字規則
- 字典沒有的複合字（toothache、schoolbag…）拆成兩個字查，英式拼法（organise、jewellery）改美式查；
  少數字（smoothie、hoodie…）在腳本的 `EXTRA` 手動補
