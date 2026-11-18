/* 管理員後台：題庫編輯頁。資料都放在 data 物件裡，輸入框直接改它，按儲存時整份送回伺服器。 */
(function () {
    const cfg = JSON.parse(document.getElementById('be-config').textContent);
    const data = JSON.parse(document.getElementById('be-data').textContent);
    const root = document.getElementById('be-root');
    const msg = document.getElementById('be-msg');
    const LETTERS = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'.split('');
    const ROMAN = ['i', 'ii', 'iii', 'iv', 'v', 'vi', 'vii', 'viii', 'ix', 'x', 'xi', 'xii', 'xiii', 'xiv', 'xv'];
    const closed = new Set();       // 使用者收起來的區塊，重畫畫面時維持收起
    let dirty = false;
    let lastGap = null;             // 上一個點過的填空輸入框，「插入空格」會插在這裡

    function touch() { dirty = true; msg.textContent = '有修改還沒儲存'; }

    function h(tag, attrs, ...kids) {
        const el = document.createElement(tag);
        Object.entries(attrs || {}).forEach(([k, v]) => {
            if (k === 'class') el.className = v;
            else if (k.startsWith('on')) el.addEventListener(k.slice(2), v);
            else if (k === 'value') el.value = v;
            else if (v !== false && v !== null && v !== undefined) el.setAttribute(k, v);
        });
        kids.flat(Infinity).forEach(c => { if (c !== null && c !== undefined && c !== false) el.append(c); });
        return el;
    }

    function rerender() {
        const y = window.scrollY;
        root.replaceChildren(...build().flat(Infinity).filter(Boolean));
        window.scrollTo(0, y);
    }
    function change(fn) { return () => { fn(); touch(); rerender(); }; }

    function growable(el) {
        const fit = () => { el.style.height = 'auto'; el.style.height = (el.scrollHeight + 4) + 'px'; };
        el.addEventListener('input', fit);
        requestAnimationFrame(fit);
        return el;
    }
    function input(obj, key, opts) {
        opts = opts || {};
        const write = e => { obj[key] = e.target.value; touch(); if (opts.after) opts.after(e); };
        const value = obj[key] === undefined || obj[key] === null ? '' : obj[key];
        if (opts.multi) {
            return growable(h('textarea', { class: opts.cls || 'grow', value, placeholder: opts.placeholder, 'aria-label': opts.label, oninput: write, onfocus: opts.focus }));
        }
        return h('input', { type: 'text', class: opts.cls || 'grow', value, placeholder: opts.placeholder, 'aria-label': opts.label, oninput: write, onfocus: opts.focus });
    }
    function field(label, obj, key, opts) {
        opts = opts || {};
        return h('div', null, h('label', { class: 'f' }, label, opts.tip ? h('span', { class: 'tip' }, opts.tip) : null),
            input(obj, key, Object.assign({ label }, opts)));
    }
    function btn(text, fn, cls) { return h('button', { type: 'button', class: cls || 'btn ghost small be-add', onclick: fn }, text); }
    function mini(text, fn, del) {
        return h('button', { type: 'button', class: 'be-mini' + (del ? ' del' : ''), onclick: fn }, text);
    }
    function block(id, title, tip, kids, startClosed) {
        if (startClosed && !closed.has('seen:' + id)) { closed.add('seen:' + id); closed.add(id); }
        const d = h('details', { class: 'be-block', open: !closed.has(id) },
            h('summary', null, title, tip ? h('span', { class: 'tip' }, tip) : null), h('div', { class: 'be-body' }, kids));
        d.addEventListener('toggle', () => { d.open ? closed.delete(id) : closed.add(id); });
        return d;
    }
    function move(list, i, step) {
        const j = i + step;
        if (j < 0 || j >= list.length) return;
        [list[i], list[j]] = [list[j], list[i]];
    }

    /* ---------- 題目與答案 ---------- */
    const hasQuestions = cfg.section === 'listening' || cfg.section === 'reading';

    function gapNos(g) {
        const out = [];
        const scan = t => { for (const m of String(t || '').matchAll(/\{(\d+)\}/g)) out.push(+m[1]); };
        (g.rows || []).forEach(r => scan(r.text));
        (g.sections || []).forEach(s => s.lines.forEach(scan));
        return out;
    }
    function groupNos(g) { return g.type === 'gapfill' ? gapNos(g) : (g.items || []).map(i => i.no); }
    function allNos() { return data.groups.flatMap(groupNos); }
    function nextNo() { return Math.max(0, ...allNos(), ...data.questions.map(q => q.no)) + 1; }
    function Q(no) {
        let q = data.questions.find(x => x.no === no);
        if (!q) { q = { no, answers: [], explain: '', quote: '' }; data.questions.push(q); }
        return q;
    }
    function dropQ(no) { data.questions = data.questions.filter(q => q.no !== no); }

    function splitAnswers(s) {
        return s.split(/\s+\/\s+|(?<!\d)\/|\/(?!\d)|\n/).map(x => x.trim()).filter(Boolean);
    }
    function pickAnswer(no, choices, labels) {
        const q = Q(no);
        const cur = q.answers[0] || '';
        return h('div', null, h('label', { class: 'f' }, '正確答案 ', h('span', { class: 'req' }, '*')),
            h('select', { 'aria-label': `第 ${no} 題的正確答案`, onchange: e => { q.answers = e.target.value ? [e.target.value] : []; touch(); } },
                h('option', { value: '' }, '請選答案'),
                choices.map(c => h('option', { value: c, selected: c === cur }, labels && labels[c] ? `${c}　${labels[c]}` : c))));
    }
    function typeAnswer(no) {
        const q = Q(no);
        return h('div', null, h('label', { class: 'f' }, '正確答案 ', h('span', { class: 'req' }, '*'),
            h('span', { class: 'tip' }, '有多種寫法時用 / 隔開，例如 nurse / a nurse')),
            h('input', { type: 'text', value: q.answers.join(' / '), 'aria-label': `第 ${no} 題的正確答案`, oninput: e => { q.answers = splitAnswers(e.target.value); touch(); } }));
    }
    function explainFields(no) {
        const q = Q(no);
        return [field('解析', q, 'explain', { multi: true, tip: '可以用 <b>粗體</b>、<br> 換行' }),
            field(cfg.section === 'listening' ? '逐字稿原句' : '文章原句', q, 'quote', { multi: true, tip: '要和原文一模一樣' })];
    }

    /* 選項方框（配對、段落標題、摘要選詞共用） */
    function setOptions(g, rows) {
        const keys = g.type === 'headings' ? ROMAN : LETTERS;
        const out = {}, map = {};
        rows.forEach((r, i) => { out[keys[i]] = r.text; map[r.key] = keys[i]; });
        g.options = out;
        groupNos(g).forEach(no => { const q = Q(no); q.answers = q.answers.map(a => map[a]).filter(Boolean); });
    }
    function optionBox(g) {
        const rows = () => Object.entries(g.options).map(([key, text]) => ({ key, text }));
        return h('div', null, h('label', { class: 'f' }, '選項'),
            Object.keys(g.options).map(key => h('div', { class: 'be-row' }, h('span', { class: 'key' }, key),
                input(g.options, key, { label: `選項 ${key}`, after: () => {} }),
                mini('刪除', change(() => setOptions(g, rows().filter(r => r.key !== key))), true))),
            btn('＋ 新增選項', change(() => setOptions(g, rows().concat({ key: '_new', text: '' })))));
    }
    function itemHead(g, item, i, label) {
        return h('div', { class: 'be-q-head' }, label, h('span', { class: 'sp' }),
            mini('上移', change(() => move(g.items, i, -1))), mini('下移', change(() => move(g.items, i, 1))),
            mini('刪除', change(() => { g.items.splice(i, 1); dropQ(item.no); }), true));
    }

    function mcqEditor(g) {
        const setItemOptions = (it, rows) => {
            const out = {}, map = {};
            rows.forEach((r, i) => { out[LETTERS[i]] = r.text; map[r.key] = LETTERS[i]; });
            it.options = out;
            const q = Q(it.no); q.answers = q.answers.map(a => map[a]).filter(Boolean);
        };
        return [g.items.map((it, i) => {
            const rows = () => Object.entries(it.options).map(([key, text]) => ({ key, text }));
            return h('div', { class: 'be-q' }, itemHead(g, it, i, `第 ${it.no} 題`),
                field('題目', it, 'stem', { multi: true }),
                h('label', { class: 'f' }, '選項'),
                Object.keys(it.options).map(key => h('div', { class: 'be-row' }, h('span', { class: 'key' }, key),
                    input(it.options, key, { label: `第 ${it.no} 題選項 ${key}` }),
                    mini('刪除', change(() => setItemOptions(it, rows().filter(r => r.key !== key))), true))),
                btn('＋ 新增選項', change(() => setItemOptions(it, rows().concat({ key: '_new', text: '' })))),
                pickAnswer(it.no, Object.keys(it.options), it.options), explainFields(it.no));
        }), btn('＋ 新增一題', change(() => {
            const no = nextNo(); g.items.push({ no, stem: '', options: { A: '', B: '', C: '' } }); Q(no);
        }))];
    }
    function listEditor(g, choices, labels) {
        return [g.items.map((it, i) => h('div', { class: 'be-q' }, itemHead(g, it, i, `第 ${it.no} 題`),
            field('題目', it, 'text', { multi: true }), pickAnswer(it.no, choices(), labels && labels()), explainFields(it.no))),
        btn('＋ 新增一題', change(() => { const no = nextNo(); g.items.push({ no, text: '' }); Q(no); }))];
    }

    /* 填空題：文字裡的 {3} 就是空格，下方自動列出每個空格的答案欄 */
    const gapBoxes = new Map();
    function gapAnswers(g) {
        const letters = g.options ? Object.keys(g.options) : null;
        const nos = gapNos(g);
        if (!nos.length) return [h('p', { class: 'be-tip' }, '還沒有空格。點一下要放空格的位置，再按「插入空格」。')];
        return nos.map(no => h('div', { class: 'be-q' }, h('div', { class: 'be-q-head' }, `空格 {${no}}`),
            letters ? pickAnswer(no, letters, g.options) : typeAnswer(no), explainFields(no)));
    }
    function refreshGaps(g) {
        const keep = new Set(allNos());
        data.questions = data.questions.filter(q => keep.has(q.no));
        const box = gapBoxes.get(g);
        if (box) box.replaceChildren(...gapAnswers(g));
    }
    function gapLine(g, obj, key, label) {
        return input(obj, key, {
            multi: true, label, focus: e => { lastGap = { el: e.target, g, obj, key }; },
            after: e => {
                lastGap = { el: e.target, g, obj, key };
                if (obj[key].includes('{}')) {                 // 直接打 {} 也算插入空格
                    const pos = e.target.selectionStart;
                    const tag = `{${nextNo()}}`;
                    obj[key] = obj[key].replace('{}', tag);
                    e.target.value = obj[key];
                    e.target.selectionStart = e.target.selectionEnd = pos + tag.length - 2;
                }
                refreshGaps(g);
            },
        });
    }
    function insertGap(g) {
        if (!lastGap || lastGap.g !== g || !lastGap.el.isConnected) {
            msg.textContent = '請先點一下要放空格的那一行';
            return;
        }
        const { el, obj, key } = lastGap;
        const tag = `{${nextNo()}}`;
        const at = el.selectionStart;
        obj[key] = obj[key].slice(0, at) + tag + obj[key].slice(el.selectionEnd);
        el.value = obj[key];
        el.focus();
        el.selectionStart = el.selectionEnd = at + tag.length;
        touch();
        refreshGaps(g);
    }
    function gapEditor(g) {
        const box = h('div', null, gapAnswers(g));
        gapBoxes.set(g, box);
        const kids = [];
        (g.sections || []).forEach((s, si) => kids.push(h('div', { class: 'be-sec' },
            h('div', { class: 'be-row' }, input(s, 'heading', { label: '小標題', placeholder: '小標題（可留白）' }),
                mini('刪除這段', change(() => { g.sections.splice(si, 1); refreshGaps(g); }), true)),
            s.lines.map((_, li) => h('div', { class: 'be-row' }, gapLine(g, s.lines, li, `第 ${li + 1} 行`),
                mini('刪除', change(() => { s.lines.splice(li, 1); refreshGaps(g); }), true))),
            btn('＋ 新增一行', change(() => s.lines.push(''))))));
        (g.rows || []).forEach((r, ri) => kids.push(h('div', { class: 'be-row' },
            r.label !== undefined ? input(r, 'label', { cls: 'sec', label: '欄位名稱', placeholder: '欄位' }) : null,
            gapLine(g, r, 'text', `第 ${ri + 1} 句`),
            mini('刪除', change(() => { g.rows.splice(ri, 1); refreshGaps(g); }), true))));
        return [kids,
            h('div', { class: 'be-tools' }, btn('插入空格', () => insertGap(g), 'btn small'),
                g.sections ? btn('＋ 新增一段', change(() => g.sections.push({ heading: '', lines: [''] }))) : null,
                g.rows ? btn('＋ 新增一句', change(() => g.rows.push(g.rows[0] && g.rows[0].label !== undefined ? { label: '', text: '' } : { text: '' }))) : null),
            h('p', { class: 'be-tip' }, '{3} 代表一個空格，開頭寫「- 」是接在上一點後面的句子，{ex:Fraser} 是範例答案。'),
            g.options ? optionBox(g) : null, box];
    }

    const NEW_GROUP = {
        gapfill: () => Object.assign({ type: 'gapfill', range: '', instruction: 'Complete the notes below.', limit: 'Write <b>ONE WORD ONLY</b> for each answer.', title: '', sections: [{ heading: '', lines: [''] }] }, cfg.section === 'listening' ? { layout: 'notes' } : {}),
        mcq: () => ({ type: 'mcq', range: '', instruction: 'Choose the correct letter, <b>A</b>, <b>B</b> or <b>C</b>.', items: [] }),
        matching: () => ({ type: 'matching', range: '', instruction: 'Choose the correct answer for each question.', limit: '', optionsTitle: '', options: { A: '', B: '', C: '' }, items: [] }),
        headings: () => ({ type: 'headings', range: '', instruction: 'Choose the correct heading for each paragraph from the list of headings below.', limit: '', optionsTitle: 'List of Headings', options: { i: '', ii: '', iii: '' }, items: [] }),
        tfng: () => ({ type: 'tfng', range: '', instruction: 'Do the following statements agree with the information given in the passage?', limit: 'Write<br><b>TRUE</b> if the statement agrees with the information<br><b>FALSE</b> if the statement contradicts the information<br><b>NOT GIVEN</b> if there is no information on this', items: [] }),
        ynng: () => ({ type: 'ynng', range: '', instruction: 'Do the following statements agree with the claims of the writer?', limit: 'Write<br><b>YES</b> if the statement agrees with the claims of the writer<br><b>NO</b> if the statement contradicts the claims of the writer<br><b>NOT GIVEN</b> if it is impossible to say what the writer thinks about this', items: [] }),
    };

    function groupBlock(g, i) {
        const name = cfg.types[g.type] || g.type;
        let body;
        if (g.type === 'mcq') body = mcqEditor(g);
        else if (g.type === 'gapfill') body = gapEditor(g);
        else if (g.type === 'map') body = listEditor(g, () => g.options);
        else if (g.type === 'tfng' || g.type === 'ynng') body = listEditor(g, () => cfg.judge[g.type]);
        else body = [optionBox(g), listEditor(g, () => Object.keys(g.options), () => g.options)];
        return block('g' + i, `題組 ${i + 1}：${name}`, g.range || '', [
            field('作答說明', g, 'instruction', { multi: true }),
            g.limit !== undefined ? field('作答限制', g, 'limit', { multi: true }) : null,
            g.title !== undefined ? field('標題', g, 'title') : null,
            g.optionsTitle !== undefined ? field('選項方框標題', g, 'optionsTitle') : null,
            g.type === 'map' ? h('p', { class: 'be-tip' }, '地圖圖片目前不能在後台更換，只能修改題目與答案。') : null,
            body,
            h('div', { class: 'be-tools' }, mini('上移題組', change(() => move(data.groups, i, -1))), mini('下移題組', change(() => move(data.groups, i, 1))),
                mini('刪除這個題組', () => {
                    if (!confirm('確定要刪除這個題組和裡面的題目嗎？')) return;
                    change(() => { const nos = groupNos(g); data.groups.splice(i, 1); nos.forEach(dropQ); })();
                }, true)),
        ]);
    }
    function addGroupTools() {
        const sel = h('select', { 'aria-label': '題型' }, Object.entries(cfg.types).filter(([k]) => k !== 'map').map(([k, v]) => h('option', { value: k }, v)));
        return h('div', { class: 'panel be-tools' }, h('b', null, '新增題組'), sel,
            btn('＋ 新增', change(() => {
                const g = NEW_GROUP[sel.value]();
                if (g.items) {
                    const no = nextNo();
                    g.items.push(g.type === 'mcq' ? { no, stem: '', options: { A: '', B: '', C: '' } } : { no, text: '' });
                    Q(no);
                }
                data.groups.push(g);
            }), 'btn small'));
    }

    /* ---------- 聽力與閱讀 ---------- */
    function cueRow(c, i) {
        const pause = c.v === 'pause';
        return h('div', { class: 'be-row' },
            h('select', { class: 'who', 'aria-label': '說話者', onchange: change(() => {}), oninput: e => { c.v = e.target.value; if (c.v === 'pause' && !/^\d+$/.test(c.t)) c.t = '5'; } },
                Object.entries(cfg.speakers).map(([k, v]) => h('option', { value: k, selected: k === c.v }, v)),
                h('option', { value: 'pause', selected: pause }, '停頓（秒）')),
            pause ? input(c, 't', { cls: 'sec', label: '停頓秒數' }) : input(c, 't', { multi: true, label: `第 ${i + 1} 句` }),
            mini('下方加一句', change(() => data.cues.splice(i + 1, 0, { v: c.v === 'pause' ? 'narrator' : c.v, t: '' }))),
            mini('刪除', change(() => data.cues.splice(i, 1)), true));
    }
    function listeningView() {
        return [block('info', '基本資料', '', [field('情境說明', data, 'context')]),
            block('cues', `逐字稿（${data.cues.length} 句）`, '改過後要重新產生音檔', [data.cues.map(cueRow),
                btn('＋ 新增一句', change(() => data.cues.push({ v: 'narrator', t: '' })))], data.cues.length > 0),
            data.groups.map(groupBlock), addGroupTools()];
    }
    function paragraphRow(p, i) {
        return h('div', { class: 'be-row' }, input(p, 'label', { cls: 'sec', label: '段落字母', placeholder: '字母' }),
            input(p, 'text', { multi: true, label: `第 ${i + 1} 段` }),
            mini('上移', change(() => move(data.paragraphs, i, -1))), mini('下移', change(() => move(data.paragraphs, i, 1))),
            mini('刪除', change(() => data.paragraphs.splice(i, 1)), true));
    }
    function readingView() {
        return [block('info', '基本資料', '', [field('文章標題', data, 'title'), field('中文主題', data, 'context')]),
            block('paras', `文章內容（${data.paragraphs.length} 段）`, '', [data.paragraphs.map(paragraphRow),
                btn('＋ 新增一段', change(() => data.paragraphs.push({ label: '', text: '' })))], data.paragraphs.length > 0),
            data.groups.map(groupBlock), addGroupTools()];
    }

    /* ---------- 寫作 ---------- */
    function csv(obj, key, label, tip) {
        return h('div', null, h('label', { class: 'f' }, label, tip ? h('span', { class: 'tip' }, tip) : null),
            h('input', { type: 'text', value: (obj[key] || []).join(', '), 'aria-label': label, oninput: e => { obj[key] = e.target.value.split(/[,，]/).map(x => x.trim()).filter(Boolean); touch(); } }));
    }
    function chartEditor(c) {
        return [h('div', { class: 'row2' },
            h('div', null, h('label', { class: 'f' }, '圖表類型'), h('select', { 'aria-label': '圖表類型', onchange: e => { c.type = e.target.value; touch(); } },
                h('option', { value: 'line', selected: c.type !== 'bar' }, '折線圖'), h('option', { value: 'bar', selected: c.type === 'bar' }, '長條圖'))),
            field('圖表標題', c, 'title')),
        csv(c, 'x', 'X 軸項目', '用逗號隔開，例如 2004, 2008, 2012'),
        field('Y 軸名稱', c, 'y_label'),
        h('div', { class: 'row2' }, field('Y 軸最大值', c, 'y_max'), field('Y 軸間隔', c, 'y_step')),
        h('label', { class: 'f' }, '數據'),
        c.series.map((s, i) => h('div', { class: 'be-sec' }, h('div', { class: 'be-row' }, input(s, 'name', { label: '數據名稱', placeholder: '數據名稱' }),
            mini('刪除', change(() => c.series.splice(i, 1)), true)), csv(s, 'values', '數值', '數量要和 X 軸項目一樣'))),
        btn('＋ 新增一組數據', change(() => c.series.push({ name: '', values: [] })))];
    }
    function writingView() {
        const blank = { type: 'line', title: '', x: [], y_label: '', y_max: 100, y_step: 10, series: [] };
        return [block('task', `Task ${data.no} 題目`, '', [field('題目', data, 'prompt', { multi: true }), field('作答指示', data, 'instruction', { multi: true }),
            h('div', { class: 'row2' }, field('建議時間（分鐘）', data, 'minutes'), field('最少字數', data, 'min_words'))]),
        block('chart', '圖表', '', data.chart ? [chartEditor(data.chart), btn('這題不要圖表', change(() => { delete data.chart; }))]
            : [h('p', { class: 'be-tip' }, '這題沒有圖表。'), btn('＋ 加上圖表', change(() => { data.chart = blank; }))])];
    }

    /* ---------- 口說 ---------- */
    function strings(list, label) {
        return [list.map((_, i) => h('div', { class: 'be-row' }, input(list, i, { label: `${label} ${i + 1}` }),
            mini('上移', change(() => move(list, i, -1))), mini('下移', change(() => move(list, i, 1))),
            mini('刪除', change(() => list.splice(i, 1)), true))),
        btn(`＋ 新增${label}`, change(() => list.push('')))];
    }
    function topics(list, field_, label, blank) {
        return [list.map((t, i) => h('div', { class: 'be-q' }, h('div', { class: 'be-q-head' }, `${label} ${i + 1}`, h('span', { class: 'sp' }),
            mini('刪除', change(() => list.splice(i, 1)), true)), field(`${label}名稱`, t, field_), h('label', { class: 'f' }, '問題'), strings(t.questions, '問題'))),
        btn(`＋ 新增${label}`, change(() => list.push(blank())))];
    }
    function speakingView() {
        return [block('p1', 'Part 1 日常問答', '', topics(data.part1, 'topic', '話題', () => ({ topic: '', questions: [''] }))),
            block('p2', 'Part 2 題卡', '', [field('話題名稱', data.part2, 'topic'), field('題卡題目', data.part2, 'cue', { multi: true }),
                h('label', { class: 'f' }, 'You should say'), strings(data.part2.points, '要點'),
                field('and explain…', data.part2, 'final'), h('label', { class: 'f' }, '收尾問題'), strings(data.part2.followups, '收尾問題')]),
            block('p3', 'Part 3 深入討論', '', topics(data.part3, 'theme', '議題', () => ({ theme: '', questions: [''] })))];
    }

    function build() {
        gapBoxes.clear();
        return { listening: listeningView, reading: readingView, writing: writingView, speaking: speakingView }[cfg.section]();
    }

    /* ---------- 儲存 ---------- */
    const errorBox = document.getElementById('be-errors');
    function showErrors(list) {
        errorBox.hidden = false;
        errorBox.replaceChildren(h('b', null, '還不能儲存，請先修正：'), h('ul', null, list.map(e => h('li', null, e))));
        errorBox.scrollIntoView({ behavior: 'smooth', block: 'center' });
        msg.textContent = '有問題要修正';
    }
    const saveBtn = document.getElementById('be-save');
    saveBtn.addEventListener('click', async () => {
        errorBox.hidden = true;
        saveBtn.disabled = true;
        msg.textContent = '儲存中…';
        if (hasQuestions) {
            const keep = new Set(allNos());
            data.questions = data.questions.filter(q => keep.has(q.no));
        }
        const form = new FormData();
        form.append('csrf', document.getElementById('be-csrf').value);
        form.append('data', JSON.stringify(data));
        try {
            const res = await fetch(cfg.saveUrl, { method: 'POST', body: form, credentials: 'same-origin' });
            const type = res.headers.get('content-type') || '';
            if (res.redirected || !type.includes('json')) {
                showErrors(['登入已過期。請另開一個分頁重新登入後，回到這裡再按一次儲存（這頁的內容還在）。']);
            } else {
                const out = await res.json();
                if (out.ok) { dirty = false; location.href = out.redirect; return; }
                showErrors(out.errors);
            }
        } catch (e) {
            showErrors(['連不上網站，請確認網站還開著，再按一次儲存。']);
        }
        saveBtn.disabled = false;
    });
    window.addEventListener('beforeunload', e => { if (dirty) { e.preventDefault(); e.returnValue = ''; } });

    rerender();
})();
