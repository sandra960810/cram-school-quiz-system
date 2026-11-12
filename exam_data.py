"""IELTS Exam Practice Test 3 的題目資料。

題目內容與答案來自補習班採購的 IELTS 練習書 Exam Practice Test 3（第 105–123 頁），
答案出自同一套書的 Answer Keys。這裡只存「題號 → 簡短題目說明」，
給成績單與錯題本顯示用；完整題目排版在 templates/exam_*.html。
"""

TEST_KEY = 'test3'
TEST_TITLE = 'IELTS Exam Practice Test 3'

SECTIONS = {
    'listening': {'name': '聽力', 'icon': '🎧', 'total': 40,
                  'desc': 'Parts 1–4，共 40 題（需搭配書本音檔 Track 18–21）'},
    'reading':   {'name': '閱讀', 'icon': '📖', 'total': 40,
                  'desc': 'Passages 1–3，共 40 題，建議 60 分鐘'},
    'writing':   {'name': '寫作', 'icon': '✍️', 'total': 2,
                  'desc': 'Task 1 圖表描述、Task 2 論說文（老師批改）'},
    'speaking':  {'name': '口說', 'icon': '🗣️', 'total': 3,
                  'desc': 'Parts 1–3 口說題目與計時練習'},
}
GRADED_SECTIONS = ('listening', 'reading')

# 每一題的題型標籤（成績單與錯題本用）
QTYPES = {
    'listening': {**{n: '筆記填空' for n in range(1, 11)},
                  **{n: '多選題' for n in range(11, 15)},
                  **{n: '流程圖配對' for n in range(15, 21)},
                  **{n: '單選題' for n in range(21, 26)},
                  **{n: '配對題' for n in range(26, 31)},
                  **{n: '筆記填空' for n in range(31, 41)}},
    'reading':   {**{n: 'TRUE / FALSE / NOT GIVEN' for n in range(1, 7)},
                  **{n: '筆記填空' for n in range(7, 11)},
                  **{n: '簡答題' for n in range(11, 14)},
                  **{n: '段落配對' for n in range(14, 19)},
                  **{n: '人物配對' for n in range(19, 23)},
                  **{n: '句子填空' for n in range(23, 27)},
                  **{n: 'YES / NO / NOT GIVEN' for n in range(27, 32)},
                  **{n: '摘要填空' for n in range(32, 37)},
                  **{n: '單選題' for n in range(37, 41)}},
}

# 題目所屬的大題（成績單分組用）
PARTS = {
    'listening': [('Part 1', 1, 10), ('Part 2', 11, 20), ('Part 3', 21, 30), ('Part 4', 31, 40)],
    'reading': [('Passage 1', 1, 13), ('Passage 2', 14, 26), ('Passage 3', 27, 40)],
}

LABELS = {
    'listening': {
        1: 'submitted before Wednesday, …',
        2: "Don't use any … with experience.",
        3: 'include a child or … this year',
        4: 'get permission for any … used',
        5: 'check that English … contain no mistakes',
        6: 'Focus on the … before doing anything else.',
        7: 'Avoid making a … because not all the judges will like it.',
        8: 'The winner was Greg …',
        9: "The title of Greg's film was …",
        10: 'The best films are shown in the … Theatre.',
        11: 'Which TWO tasks will volunteers be required to do at Eskdale Wood?',
        12: 'Which TWO tasks will volunteers be required to do at Eskdale Wood?',
        13: 'Which TWO things must volunteers bring with them?',
        14: 'Which TWO things must volunteers bring with them?',
        15: 'set up a … for a mobile app',
        16: 'decide on a … for the day of the bird count',
        17: 'organise a … for support',
        18: 'ensure everyone has access to a …',
        19: 'agree on a … for observed birds',
        20: 'submit a … with your collected data',
        21: 'The students agree that the introduction to their presentation should include',
        22: 'When the students visited the museum, they were surprised by',
        23: 'What does Oliver say would put him off a career in art restoration?',
        24: 'What do the students agree about the restored Dutch landscape painting?',
        25: "What is Oliver's attitude to the digital reproduction of famous paintings?",
        26: 'Six Sunflowers',
        27: 'The Concert',
        28: 'Portrait of Sir Winston Churchill',
        29: 'The Water Lilies',
        30: 'Myrto',
        31: 'their blood moves to their head and …',
        32: 'they lose minerals such as …',
        33: 'they have to exercise 2.5 hours to avoid … loss',
        34: 'they may suffer from poor … back on Earth',
        35: 'ways to recycle water, including …',
        36: 'are … enough for transport',
        37: 'metal, brick and possibly … for buildings',
        38: 'find a way to make large …',
        39: 'to visit places like a …',
        40: 'to get a new …',
    },
    'reading': {
        1: 'Dance historians agree about the development of modern American dance.',
        2: 'Dancers in the early 1900s tended to copy the styles of earlier dancers.',
        3: 'Loie Fuller preferred to dance alone on stage.',
        4: 'Isadora Duncan wore complicated clothing when dancing.',
        5: 'Some dancers criticised Isadora Duncan for her choice of music.',
        6: 'Ruth St Denis wished to educate others in her style of dancing.',
        7: 'Martha Graham based her dance on human actions such as breathing and …',
        8: 'Doris Humphrey wrote an important … about her ideas.',
        9: 'Hanya Holm introduced … into dance and musicals.',
        10: 'An influential … outlined the working life of Paul Taylor.',
        11: 'When Pearl Primus gave up dancing, what did she focus on doing?',
        12: "What was an important influence for Mark Morris's The Hard Nut?",
        13: 'Dancers working with Ohad Naharin practise without using what?',
        14: 'the claim that it is very hard for people to pretend to laugh',
        15: 'a reference to research showing that people do not know how often they laugh',
        16: 'the reason why people can sometimes stop themselves laughing',
        17: 'an outline of the health benefits experienced by people when laughing',
        18: 'a reference to a medical condition that stops some people making a noise when laughing',
        19: 'Research has confirmed personal experience by identifying the wide range of subjects '
            'and situations that people find funny.',
        20: 'Ideas about what is amusing have changed considerably over time.',
        21: 'To intentionally make other people laugh requires an unusual combination of skills '
            'and characteristics.',
        22: 'The reasons why we laugh are sometimes misunderstood by ordinary people.',
        23: "the skin around a person's … does not change shape",
        24: 'A … that was produced in ancient Rome contains early examples of attempts to be funny.',
        25: 'an outbreak of mass laughter caused problems in a … in Tanzania',
        26: 'Nikki Sokolov is investigating why … is possible even when a person finds something funny',
        27: 'Many business commentators forget the example of Muhammad Yunus.',
        28: 'Dan Rathbourne provides an accurate assessment of Socially Responsible Businesses (SRBs).',
        29: 'The Quorate Group is a good example of an influential SRB.',
        30: 'Few other businesses will wish to follow the example of the Concern Consultancy.',
        31: 'Professor Drew has correctly identified one reason for the emergence of SRBs.',
        32: 'Renew has made a successful business out of designing …',
        33: 'Indulge wishes to promote …',
        34: 'many large corporations make provision for …',
        35: 'Johann Jensen is experimenting with types of …',
        36: 'Greater Good provides … to a growing market',
        37: "When discussing 'conscious consumers' the writer concludes that",
        38: 'The writer refers to Lucinda Mitchell in order to',
        39: 'What does the writer suggest about the goals of SRBs?',
        40: "Which of the following best summarises the writer's argument in the final paragraph?",
    },
}


def part_of(section, qno):
    for name, lo, hi in PARTS.get(section, []):
        if lo <= qno <= hi:
            return name
    return ''
