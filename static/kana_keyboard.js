// 日文輸入：給沒有安裝日文輸入法的電腦用（例如櫃台電腦），日檢的單字測驗打字題會用到。
//
// - 直接用鍵盤打羅馬拼音，會自動變成平假名：gakkou → がっこう、nihon → にほん、kya → きゃ、- → ー
//   （片假名的字打平假名也算對，カメラ打 かめら 就好；漢字或假名都算對）
// - 鍵盤上方可以切換「ひらがな／カタカナ」：切到片假名後，五十音鍵盤和羅馬拼音打出來的都是片假名（kamera → カメラ）
// - 下方有五十音鍵盤可以用滑鼠或手指點：゛把前一個字變濁音（か→が）、゜變半濁音（は→ぱ）、小 變小字（つ→っ）
// - 已經裝了日文輸入法的電腦或手機，直接用自己的輸入法打也可以（組字中不會被轉換）
// - 用法：KanaKeyboard.attach(input)，每一題換新的輸入框時再 attach 一次；送出前呼叫 KanaKeyboard.flush(input)
(function () {
    const T = {
        a: 'あ', i: 'い', u: 'う', e: 'え', o: 'お',
        ka: 'か', ki: 'き', ku: 'く', ke: 'け', ko: 'こ', ca: 'か', cu: 'く', co: 'こ', qa: 'くぁ', qi: 'くぃ', qe: 'くぇ', qo: 'くぉ',
        sa: 'さ', si: 'し', shi: 'し', su: 'す', se: 'せ', so: 'そ',
        ta: 'た', ti: 'ち', chi: 'ち', tu: 'つ', tsu: 'つ', te: 'て', to: 'と',
        na: 'な', ni: 'に', nu: 'ぬ', ne: 'ね', no: 'の',
        ha: 'は', hi: 'ひ', hu: 'ふ', fu: 'ふ', he: 'へ', ho: 'ほ',
        ma: 'ま', mi: 'み', mu: 'む', me: 'め', mo: 'も',
        ya: 'や', yu: 'ゆ', yo: 'よ', ye: 'いぇ',
        ra: 'ら', ri: 'り', ru: 'る', re: 'れ', ro: 'ろ', la: 'ら', li: 'り', lu: 'る', le: 'れ', lo: 'ろ',
        wa: 'わ', wi: 'うぃ', we: 'うぇ', wo: 'を', nn: 'ん', "n'": 'ん', xn: 'ん',
        ga: 'が', gi: 'ぎ', gu: 'ぐ', ge: 'げ', go: 'ご',
        za: 'ざ', zi: 'じ', ji: 'じ', zu: 'ず', ze: 'ぜ', zo: 'ぞ',
        da: 'だ', di: 'ぢ', du: 'づ', de: 'で', do: 'ど',
        ba: 'ば', bi: 'び', bu: 'ぶ', be: 'べ', bo: 'ぼ',
        pa: 'ぱ', pi: 'ぴ', pu: 'ぷ', pe: 'ぺ', po: 'ぽ',
        va: 'ゔぁ', vi: 'ゔぃ', vu: 'ゔ', ve: 'ゔぇ', vo: 'ゔぉ',
        fa: 'ふぁ', fi: 'ふぃ', fe: 'ふぇ', fo: 'ふぉ', fyu: 'ふゅ',
        sha: 'しゃ', shu: 'しゅ', she: 'しぇ', sho: 'しょ', sya: 'しゃ', syu: 'しゅ', syo: 'しょ',
        cha: 'ちゃ', chu: 'ちゅ', che: 'ちぇ', cho: 'ちょ', tya: 'ちゃ', tyu: 'ちゅ', tyo: 'ちょ', cya: 'ちゃ', cyu: 'ちゅ', cyo: 'ちょ',
        ja: 'じゃ', ju: 'じゅ', je: 'じぇ', jo: 'じょ', jya: 'じゃ', jyu: 'じゅ', jyo: 'じょ', zya: 'じゃ', zyu: 'じゅ', zyo: 'じょ',
        dya: 'ぢゃ', dyu: 'ぢゅ', dyo: 'ぢょ', thi: 'てぃ', dhi: 'でぃ', twu: 'とぅ', dwu: 'どぅ', tsa: 'つぁ',
        xa: 'ぁ', xi: 'ぃ', xu: 'ぅ', xe: 'ぇ', xo: 'ぉ', xya: 'ゃ', xyu: 'ゅ', xyo: 'ょ', xtu: 'っ', xtsu: 'っ', xwa: 'ゎ',
        ltu: 'っ', ltsu: 'っ', lya: 'ゃ', lyu: 'ゅ', lyo: 'ょ',
        '-': 'ー',
    };
    // 拗音：kya きゃ、nyu にゅ…
    const YOON = { k: 'き', g: 'ぎ', n: 'に', h: 'ひ', b: 'び', p: 'ぴ', m: 'み', r: 'り', l: 'り' };
    Object.entries(YOON).forEach(([c, k]) => { T[c + 'ya'] = k + 'ゃ'; T[c + 'yu'] = k + 'ゅ'; T[c + 'yo'] = k + 'ょ'; T[c + 'ye'] = k + 'ぇ'; });
    const PREFIXES = new Set();
    Object.keys(T).forEach(k => { for (let i = 1; i < k.length; i++) PREFIXES.add(k.slice(0, i)); });

    // 平假名 ↔ 片假名（兩組字在 Unicode 裡剛好差 0x60）
    const toKata = (t) => t.replace(/[\u3041-\u3096]/g, c => String.fromCharCode(c.charCodeAt(0) + 0x60));
    const toHira = (t) => t.replace(/[\u30a1-\u30f6]/g, c => String.fromCharCode(c.charCodeAt(0) - 0x60));
    const isKata = (c) => /[\u30a1-\u30f6]/.test(c || '');

    const T_KATA = Object.fromEntries(Object.entries(T).map(([k, v]) => [k, toKata(v)]));

    // 羅馬拼音轉平假名。final=true 時，最後剩下的 n 也轉成 ん（送出答案時）；
    // katakana=true 時新轉出來的字用片假名（原本已經在輸入框裡的假名不動）
    function romajiToKana(text, final, katakana) {
        const s = text;
        const src = katakana ? T_KATA : T;
        const SOKUON = katakana ? 'ッ' : 'っ', N = katakana ? 'ン' : 'ん';
        let out = '', i = 0;
        while (i < s.length) {
            const c = s[i].toLowerCase();
            if (!/[a-z'\-]/.test(c)) { out += s[i]; i++; continue; }
            // 促音：子音重複（kk → っk），n 除外
            const c2 = (s[i + 1] || '').toLowerCase();
            if (c === c2 && /[bcdfghjklmpqrstvwxyz]/.test(c)) { out += SOKUON; i++; continue; }
            if (c === 't' && c2 === 'c') { out += SOKUON; i++; continue; }   // tch → っch
            if (c === 'n' && c2 === 'n') {   // nn：後面接母音時第二個 n 屬於下一個字（onna → おんな），否則 nn＝ん
                out += N; i += /[aiueoy]/.test((s[i + 2] || '').toLowerCase()) ? 1 : 2; continue;
            }
            let matched = false;
            for (let len = 4; len >= 1; len--) {
                const chunk = s.slice(i, i + len).toLowerCase();
                if (chunk.length === len && src[chunk]) {
                    // n 後面接母音或 y 時是な行、にゃ，要等下一個字母；nn、n' 才是ん
                    out += src[chunk]; i += len; matched = true; break;
                }
            }
            if (matched) continue;
            if (c === 'n') {
                // n 後面接子音（不是 y）→ ん；在最後面 → 等下一個字母（final 才轉）
                if (c2 && !/[aiueoy'n]/.test(c2)) { out += N; i++; continue; }
                if (!c2) { out += final ? N : s[i]; i++; continue; }
            }
            const rest = s.slice(i).toLowerCase();
            if (!final && PREFIXES.has(rest)) { out += s.slice(i); break; }   // 還沒打完的（例如 ky）先留著
            out += s[i]; i++;
        }
        return out;
    }

    const COLS = [['あ', 'い', 'う', 'え', 'お'], ['か', 'き', 'く', 'け', 'こ'], ['さ', 'し', 'す', 'せ', 'そ'],
                  ['た', 'ち', 'つ', 'て', 'と'], ['な', 'に', 'ぬ', 'ね', 'の'], ['は', 'ひ', 'ふ', 'へ', 'ほ'],
                  ['ま', 'み', 'む', 'め', 'も'], ['や', '', 'ゆ', '', 'よ'], ['ら', 'り', 'る', 'れ', 'ろ'],
                  ['わ', '', 'を', '', 'ん']];
    const DAKU = { か: 'が', き: 'ぎ', く: 'ぐ', け: 'げ', こ: 'ご', さ: 'ざ', し: 'じ', す: 'ず', せ: 'ぜ', そ: 'ぞ',
                   た: 'だ', ち: 'ぢ', つ: 'づ', て: 'で', と: 'ど', は: 'ば', ひ: 'び', ふ: 'ぶ', へ: 'べ', ほ: 'ぼ', う: 'ゔ' };
    const HANDAKU = { は: 'ぱ', ひ: 'ぴ', ふ: 'ぷ', へ: 'ぺ', ほ: 'ぽ', ば: 'ぱ', び: 'ぴ', ぶ: 'ぷ', べ: 'ぺ', ぼ: 'ぽ' };
    const SMALL = { あ: 'ぁ', い: 'ぃ', う: 'ぅ', え: 'ぇ', お: 'ぉ', つ: 'っ', や: 'ゃ', ゆ: 'ゅ', よ: 'ょ', わ: 'ゎ' };
    const UNDO = {};
    [DAKU, HANDAKU, SMALL].forEach(m => Object.entries(m).forEach(([k, v]) => { if (!UNDO[v]) UNDO[v] = k; }));

    const STORE = 'quiz-kana-keyboard', STORE_KATA = 'quiz-kana-katakana';
    let on = true, kata = false;   // kata：現在打的是片假名
    try { on = localStorage.getItem(STORE) !== '0'; kata = localStorage.getItem(STORE_KATA) === '1'; } catch (e) { /* ignore */ }
    let input = null, panel = null;

    function setValue(v) {
        input.value = v;
        input.dispatchEvent(new Event('input', { bubbles: true }));
    }
    function convert(final) {
        if (!input) return;
        const v = romajiToKana(input.value, final, kata);
        if (v !== input.value) {
            const atEnd = input.selectionStart === input.value.length;
            input.value = v;
            if (atEnd) input.setSelectionRange(v.length, v.length);
        }
    }
    // 把最後一個字換成濁音／半濁音／小字（再按一次換回來）
    function modify(map) {
        const v = input.value;
        const shown = v.slice(-1);
        const last = toHira(shown);                       // 對照表是平假名，片假名先轉過來查
        const put = (c) => setValue(v.slice(0, -1) + (isKata(shown) ? toKata(c) : c));
        if (map[last]) put(map[last]);
        else if (map === DAKU && HANDAKU[UNDO[last]] === last) put(DAKU[UNDO[last]]);
        else if (UNDO[last] && (map[UNDO[last]] === last)) put(UNDO[last]);
    }
    function press(k) {
        if (!input || input.readOnly) return;
        convert(true);
        if (k === 'back') setValue(input.value.slice(0, -1));
        else if (k === 'daku') modify(DAKU);
        else if (k === 'handaku') modify(HANDAKU);
        else if (k === 'small') modify(SMALL);
        else setValue(input.value + (kata ? toKata(k) : k));
    }

    function render() {
        if (!panel) return;
        panel.innerHTML = `
            <div class="hk-head">
                <label class="hk-switch"><input type="checkbox" ${on ? 'checked' : ''}> 五十音鍵盤</label>
                <span class="hk-mode" role="group" aria-label="假名種類">
                    <button type="button" class="hk-mode-btn ${kata ? '' : 'on'}" data-kata="0">ひらがな</button>
                    <button type="button" class="hk-mode-btn ${kata ? 'on' : ''}" data-kata="1">カタカナ</button>
                </span>
                <span class="hk-note">鍵盤打羅馬拼音會自動變假名（${kata ? 'kamera → カメラ' : 'gakkou → がっこう'}），平假名、片假名、漢字都算對</span>
            </div>
            ${on ? `<div class="hk-keys kana-keys">${[0, 1, 2, 3, 4].map(r => `<div class="hk-row">${COLS.map(col => col[r]
                ? `<button type="button" class="hk-key" data-k="${col[r]}">${kata ? toKata(col[r]) : col[r]}</button>`
                : '<span class="hk-key blank"></span>').join('')}</div>`).join('')}
                <div class="hk-row">
                    <button type="button" class="hk-key wide" data-k="back">刪除</button>
                    <button type="button" class="hk-key wide" data-k="daku" title="濁音：${kata ? 'カ→ガ' : 'か→が'}">゛</button>
                    <button type="button" class="hk-key wide" data-k="handaku" title="半濁音：${kata ? 'ハ→パ' : 'は→ぱ'}">゜</button>
                    <button type="button" class="hk-key wide" data-k="small" title="小字：${kata ? 'ツ→ッ、ヤ→ャ' : 'つ→っ、や→ゃ'}">小</button>
                    <button type="button" class="hk-key wide" data-k="ー" title="長音">ー</button>
                </div></div>` : ''}`;
        panel.querySelector('.hk-switch input').addEventListener('change', (e) => {
            on = e.target.checked;
            try { localStorage.setItem(STORE, on ? '1' : '0'); } catch (err) { /* ignore */ }
            render();
        });
        panel.querySelectorAll('.hk-mode-btn').forEach(b => {
            b.addEventListener('mousedown', (e) => e.preventDefault());
            b.addEventListener('click', () => {
                convert(true);                                   // 切換前先把還沒轉完的羅馬拼音定下來
                kata = b.dataset.kata === '1';
                try { localStorage.setItem(STORE_KATA, kata ? '1' : '0'); } catch (err) { /* ignore */ }
                render();
            });
        });
        panel.querySelectorAll('button.hk-key').forEach(b => {
            b.addEventListener('mousedown', (e) => e.preventDefault());   // 不要讓輸入框失去焦點
            b.addEventListener('click', () => press(b.dataset.k));
        });
    }

    function attach(el) {
        input = el;
        el.setAttribute('lang', 'ja');
        el.addEventListener('input', (e) => { if (!e.isComposing) convert(false); });
        el.addEventListener('compositionend', () => convert(false));
        panel = document.createElement('div');
        panel.className = 'hk-panel';
        el.closest('.answer-row').after(panel);
        render();
    }

    function flush(el) {
        if (el) input = el;
        convert(true);
    }

    window.KanaKeyboard = { attach, flush, romajiToKana };
})();
