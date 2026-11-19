// 韓文輸入：給沒有安裝韓文輸入法的電腦用（例如櫃台電腦），韓檢的單字測驗打字題會用到。
//
// - 「韓文鍵盤」打開時，實體鍵盤照韓文 2 벌식（標準）鍵位打字：r=ㄱ、k=ㅏ… 自動組成 가；
//   Shift+r=ㄲ。已經裝了韓文輸入法的電腦或手機，關掉這個就能用自己的輸入法
// - 下方也有螢幕鍵盤可以用滑鼠或手指點
// - 用法：HangulKeyboard.attach(input)，每一題換新的輸入框時再 attach 一次；
//   一頁有好幾個輸入框時用 HangulKeyboard.attachAll([框…], 放鍵盤的元素)
(function () {
    const CHO = 'ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ';
    const JUNG = 'ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ';
    const JONG = ' ㄱㄲㄳㄴㄵㄶㄷㄹㄺㄻㄼㄽㄾㄿㅀㅁㅂㅄㅅㅆㅇㅈㅊㅋㅌㅍㅎ';
    const VOWEL_PAIR = { 'ㅗㅏ': 'ㅘ', 'ㅗㅐ': 'ㅙ', 'ㅗㅣ': 'ㅚ', 'ㅜㅓ': 'ㅝ', 'ㅜㅔ': 'ㅞ', 'ㅜㅣ': 'ㅟ', 'ㅡㅣ': 'ㅢ' };
    const FINAL_PAIR = { 'ㄱㅅ': 'ㄳ', 'ㄴㅈ': 'ㄵ', 'ㄴㅎ': 'ㄶ', 'ㄹㄱ': 'ㄺ', 'ㄹㅁ': 'ㄻ', 'ㄹㅂ': 'ㄼ', 'ㄹㅅ': 'ㄽ',
                         'ㄹㅌ': 'ㄾ', 'ㄹㅍ': 'ㄿ', 'ㄹㅎ': 'ㅀ', 'ㅂㅅ': 'ㅄ' };
    const SPLIT = {};
    Object.entries(VOWEL_PAIR).forEach(([k, v]) => { SPLIT[v] = [k[0], k[1]]; });
    Object.entries(FINAL_PAIR).forEach(([k, v]) => { SPLIT[v] = [k[0], k[1]]; });
    // 2 벌식鍵位（小寫＝一般、大寫＝Shift）
    const KEYMAP = {
        q: 'ㅂ', w: 'ㅈ', e: 'ㄷ', r: 'ㄱ', t: 'ㅅ', y: 'ㅛ', u: 'ㅕ', i: 'ㅑ', o: 'ㅐ', p: 'ㅔ',
        a: 'ㅁ', s: 'ㄴ', d: 'ㅇ', f: 'ㄹ', g: 'ㅎ', h: 'ㅗ', j: 'ㅓ', k: 'ㅏ', l: 'ㅣ',
        z: 'ㅋ', x: 'ㅌ', c: 'ㅊ', v: 'ㅍ', b: 'ㅠ', n: 'ㅜ', m: 'ㅡ',
        Q: 'ㅃ', W: 'ㅉ', E: 'ㄸ', R: 'ㄲ', T: 'ㅆ', O: 'ㅒ', P: 'ㅖ'
    };
    const ROWS = [['ㅂ', 'ㅈ', 'ㄷ', 'ㄱ', 'ㅅ', 'ㅛ', 'ㅕ', 'ㅑ', 'ㅐ', 'ㅔ'],
                  ['ㅁ', 'ㄴ', 'ㅇ', 'ㄹ', 'ㅎ', 'ㅗ', 'ㅓ', 'ㅏ', 'ㅣ'],
                  ['ㅋ', 'ㅌ', 'ㅊ', 'ㅍ', 'ㅠ', 'ㅜ', 'ㅡ']];
    const SHIFTED = { 'ㅂ': 'ㅃ', 'ㅈ': 'ㅉ', 'ㄷ': 'ㄸ', 'ㄱ': 'ㄲ', 'ㅅ': 'ㅆ', 'ㅐ': 'ㅒ', 'ㅔ': 'ㅖ' };
    const isVowel = (j) => JUNG.includes(j);
    const isCons = (j) => CHO.includes(j);

    // 一串字母（ㄱ、ㅏ…）組成韓文字：ㄱㅏㅇ → 강、ㄱㅏㅇㅏ → 가아
    function compose(keys) {
        let out = '', cho = null, jung = null, jong = null;
        const flush = () => {
            if (cho && jung) out += String.fromCharCode(0xAC00 + (CHO.indexOf(cho) * 21 + JUNG.indexOf(jung)) * 28 + (jong ? JONG.indexOf(jong) : 0));
            else out += (cho || '') + (jung || '');
            cho = jung = jong = null;
        };
        for (const k of keys) {
            if (isCons(k)) {
                if (cho && jung && !jong && JONG.includes(k)) jong = k;
                else if (cho && jung && jong && FINAL_PAIR[jong + k]) jong = FINAL_PAIR[jong + k];
                else { flush(); cho = k; }
            } else if (isVowel(k)) {
                if (jong) {
                    // 前一個字的收尾音移去當下一個字的初聲（ㄱㅏㄴㅏ → 가나）；複合收尾音只移後半（ㅇㅣㄹㄱㅓ → 일거）
                    let carry;
                    if (SPLIT[jong]) { carry = SPLIT[jong][1]; jong = SPLIT[jong][0]; } else { carry = jong; jong = null; }
                    flush(); cho = carry; jung = k;
                } else if (jung && VOWEL_PAIR[jung + k]) jung = VOWEL_PAIR[jung + k];
                else if (cho && !jung) jung = k;
                else { flush(); jung = k; }
            } else { flush(); out += k; }
        }
        flush();
        return out;
    }
    // 韓文字拆回字母（讓已經打好的字也能繼續用螢幕鍵盤修改）
    function decompose(text) {
        const keys = [];
        for (const ch of text) {
            const o = ch.charCodeAt(0) - 0xAC00;
            if (o < 0 || o >= 11172) { (SPLIT[ch] || [ch]).forEach(k => keys.push(k)); continue; }
            keys.push(CHO[Math.floor(o / 588)]);
            const v = JUNG[Math.floor((o % 588) / 28)];
            (SPLIT[v] || [v]).forEach(k => keys.push(k));
            const f = o % 28;
            if (f) (SPLIT[JONG[f]] || [JONG[f]]).forEach(k => keys.push(k));
        }
        return keys;
    }

    const STORE = 'quiz-hangul-keyboard';
    let on = true;
    try { on = localStorage.getItem(STORE) !== '0'; } catch (e) { /* ignore */ }
    let input = null, panel = null, shift = false;

    // 在游標位置打字：只把游標前面那一個韓文字拆開重組（ㄱ＋ㅏ→가、간＋ㅏ→가나），
    // 所以長篇作文（韓檢寫作）也能在中間插字；游標在最後時和以前整串重組的結果一樣
    function type(k) {
        if (!input || input.readOnly) return;
        const v = input.value;
        const s = input.selectionStart == null ? v.length : input.selectionStart;
        const e = input.selectionEnd == null ? s : input.selectionEnd;
        let before = v.slice(0, s);
        const after = v.slice(e);
        let ks = [];
        if (s === e && /[ㄱ-ㅣ가-힣]$/.test(before)) { ks = decompose(before.slice(-1)); before = before.slice(0, -1); }
        if (k === 'back') {
            if (ks.length) ks.pop();
            else if (s === e) before = before.slice(0, -1);
        } else ks.push(k);
        const mid = compose(ks);
        input.value = before + mid + after;
        const pos = before.length + mid.length;
        try { input.setSelectionRange(pos, pos); } catch (err) { /* ignore */ }
        input.dispatchEvent(new Event('input', { bubbles: true }));
    }

    function onKey(e) {
        input = e.target;
        if (!on || e.ctrlKey || e.metaKey || e.altKey || e.isComposing) return;
        if (e.key === 'Backspace') {
            const s = input.selectionStart, end = input.selectionEnd;
            if (s === end && /[ㄱ-ㅣ가-힣]$/.test(input.value.slice(0, s))) { e.preventDefault(); type('back'); }
            return;
        }
        const j = KEYMAP[e.key] || (e.shiftKey ? null : KEYMAP[e.key.toLowerCase()]);
        if (j) { e.preventDefault(); type(j); }
    }

    function render() {
        if (!panel) return;
        // 用螢幕鍵盤時不要再跳出手機自己的鍵盤（擋住題目）；關掉就恢復用手機或電腦的輸入法
        if (input) { if (on && window.matchMedia('(pointer: coarse)').matches) input.setAttribute('inputmode', 'none'); else input.removeAttribute('inputmode'); }
        panel.innerHTML = `
            <div class="hk-head">
                <label class="hk-switch"><input type="checkbox" ${on ? 'checked' : ''}> 韓文鍵盤</label>
                <span class="hk-note">${on ? '實體鍵盤照韓文鍵位打（r=ㄱ、k=ㅏ），或點下面的按鍵' : '關閉：使用電腦或手機自己的韓文輸入法'}</span>
            </div>
            ${on ? `<div class="hk-keys">${ROWS.map((row, i) => `<div class="hk-row">${i === 2 ? `<button type="button" class="hk-key wide ${shift ? 'on' : ''}" data-k="shift">Shift</button>` : ''}${row.map(j => {
                const s = shift && SHIFTED[j] ? SHIFTED[j] : j;
                return `<button type="button" class="hk-key" data-k="${s}">${s}</button>`;
            }).join('')}${i === 2 ? '<button type="button" class="hk-key wide" data-k="back">刪除</button>' : ''}</div>`).join('')}
                <div class="hk-row"><button type="button" class="hk-key space" data-k=" ">空白</button></div></div>` : ''}`;
        panel.querySelector('.hk-switch input').addEventListener('change', (e) => {
            on = e.target.checked;
            try { localStorage.setItem(STORE, on ? '1' : '0'); } catch (err) { /* ignore */ }
            render();
            if (input) input.focus();
        });
        panel.querySelectorAll('.hk-key').forEach(b => {
            b.addEventListener('mousedown', (e) => e.preventDefault());   // 不要讓輸入框失去焦點
            b.addEventListener('click', () => {
                const k = b.dataset.k;
                if (k === 'shift') { shift = !shift; render(); return; }
                type(k);
                if (shift && k !== 'back') { shift = false; render(); }
            });
        });
    }

    function listen(el) {
        el.setAttribute('lang', 'ko');
        el.addEventListener('keydown', onKey);
        el.addEventListener('focus', () => { input = el; render(); });
    }

    function attach(el) {
        input = el;
        listen(el);
        panel = document.createElement('div');
        panel.className = 'hk-panel';
        el.closest('.answer-row').after(panel);
        render();
    }

    // 一頁好幾個輸入框共用一個螢幕鍵盤（韓檢寫作）：按鍵打進目前游標所在的框
    function attachAll(els, holder) {
        els.forEach(listen);
        input = els[0] || null;
        panel = document.createElement('div');
        panel.className = 'hk-panel';
        holder.appendChild(panel);
        render();
    }

    window.HangulKeyboard = { attach, attachAll, compose, decompose };
})();
