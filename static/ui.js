/* 共用互動：點擊音效、按壓漣漪、換頁淡出、靜音切換。
 * 音效用 Web Audio 即時合成，不需要音檔。
 * 其他頁面可以呼叫 UI.play('tap' | 'right' | 'left' | 'star' | 'unstar' | 'done' | 'error')。
 */
(function () {
    const STORE_KEY = 'quiz-sound-on';
    let ctx = null;
    let soundOn = true;
    try { soundOn = localStorage.getItem(STORE_KEY) !== '0'; } catch (e) { /* 無痕模式等情況 */ }

    function audio() {
        if (!ctx) {
            const AC = window.AudioContext || window.webkitAudioContext;
            if (!AC) return null;
            ctx = new AC();
        }
        if (ctx.state === 'suspended') ctx.resume();
        return ctx;
    }

    // 一個音：頻率、開始時間（秒，相對現在）、長度、音量、波形
    function tone(freq, start, dur, vol, type, slideTo) {
        const a = audio();
        if (!a) return;
        const t0 = a.currentTime + start;
        const osc = a.createOscillator();
        const gain = a.createGain();
        osc.type = type || 'sine';
        osc.frequency.setValueAtTime(freq, t0);
        if (slideTo) osc.frequency.exponentialRampToValueAtTime(slideTo, t0 + dur);
        gain.gain.setValueAtTime(0.0001, t0);
        gain.gain.exponentialRampToValueAtTime(vol, t0 + 0.012);
        gain.gain.exponentialRampToValueAtTime(0.0001, t0 + dur);
        osc.connect(gain).connect(a.destination);
        osc.start(t0);
        osc.stop(t0 + dur + 0.02);
    }

    const SOUNDS = {
        tap:    () => tone(660, 0, 0.07, 0.08, 'triangle'),
        nav:    () => { tone(520, 0, 0.06, 0.07, 'triangle'); tone(780, 0.05, 0.08, 0.07, 'triangle'); },
        right:  () => { tone(660, 0, 0.1, 0.12, 'sine'); tone(880, 0.08, 0.1, 0.12, 'sine'); tone(1320, 0.16, 0.16, 0.1, 'sine'); },
        left:   () => tone(392, 0, 0.22, 0.12, 'sine', 262),
        star:   () => { tone(988, 0, 0.08, 0.09, 'sine'); tone(1319, 0.06, 0.14, 0.09, 'sine'); },
        unstar: () => tone(700, 0, 0.12, 0.07, 'sine', 440),
        done:   () => [523, 659, 784, 1047].forEach((f, i) => tone(f, i * 0.09, 0.22, 0.11, 'triangle')),
        error:  () => { tone(220, 0, 0.12, 0.1, 'square'); tone(196, 0.12, 0.16, 0.1, 'square'); },
    };

    function play(name) {
        if (!soundOn || !SOUNDS[name]) return;
        try { SOUNDS[name](); } catch (e) { /* 音效失敗不影響操作 */ }
    }

    function ripple(el, x, y) {
        const rect = el.getBoundingClientRect();
        const r = document.createElement('span');
        const size = Math.max(rect.width, rect.height);
        r.className = 'ui-ripple';
        r.style.width = r.style.height = size + 'px';
        r.style.left = (x - rect.left - size / 2) + 'px';
        r.style.top = (y - rect.top - size / 2) + 'px';
        if (getComputedStyle(el).position === 'static') el.style.position = 'relative';
        el.classList.add('ui-ripple-host');
        el.appendChild(r);
        setTimeout(() => r.remove(), 600);
    }

    // 可以互動的元素：按鈕、連結、或標了 data-sound 的元素
    const CLICKABLE = 'a[href], button, [data-sound]';

    document.addEventListener('pointerdown', (e) => {
        const el = e.target.closest(CLICKABLE);
        if (!el || el.disabled || el.classList.contains('disabled')) return;
        if (el.dataset.ripple !== 'off') ripple(el, e.clientX, e.clientY);
    });

    document.addEventListener('click', (e) => {
        const el = e.target.closest(CLICKABLE);
        if (!el || el.disabled) return;
        if (el.classList.contains('disabled')) { play('error'); return; }
        const sound = el.dataset.sound;   // data-sound="none" 表示由頁面自己播
        if (sound !== 'none') play(sound || (el.matches('a[href]') ? 'nav' : 'tap'));

        // 站內連結：先播音效和淡出，再換頁
        if (el.matches('a[href]') && !e.defaultPrevented && e.button === 0
            && !e.metaKey && !e.ctrlKey && !e.shiftKey && !e.altKey && el.target !== '_blank') {
            const url = new URL(el.href, location.href);
            const raw = el.getAttribute('href');
            if (url.origin === location.origin && !raw.startsWith('#') && !raw.startsWith('javascript:')) {
                e.preventDefault();
                document.body.classList.add('ui-leaving');
                setTimeout(() => { location.href = url.href; }, 170);
            }
        }
    });

    // 從上一頁「返回」回來時，瀏覽器可能保留淡出狀態，要清掉
    window.addEventListener('pageshow', () => document.body.classList.remove('ui-leaving'));


    // ------------------------------------------------------------------
    // 英文發音：從瀏覽器的語音裡挑最像真人的（Natural / Neural / Google 等）
    // ------------------------------------------------------------------
    // 韓檢頁面（<html data-exam="topik">）唸韓文、日檢（jlpt）唸日文，其他頁面唸英文；各語言的發音設定分開存
    const FOREIGN = {
        topik: { name: '韓文', re: /^ko[-_]/i, store: '-ko', bcp: 'ko-KR', accent: 'KR', test: '안녕하세요? 한국어 공부를 시작해 볼까요?' },
        jlpt: { name: '日文', re: /^ja[-_]/i, store: '-ja', bcp: 'ja-JP', accent: 'JP', test: 'こんにちは。日本語の勉強を始めましょう。' },
    }[document.documentElement.dataset.exam] || null;
    const LANG_RE = FOREIGN ? FOREIGN.re : /^en[-_]/i;
    const VOICE_KEY = 'quiz-voice-settings' + (FOREIGN ? FOREIGN.store : '');
    let voiceSettings = { accent: 'GB', rate: 'normal', voiceName: '' };
    try { Object.assign(voiceSettings, JSON.parse(localStorage.getItem(VOICE_KEY) || '{}')); } catch (e) { /* ignore */ }
    const RATES = { slow: 0.75, normal: 0.95 };

    // 分數越高越像真人；accent 是 'GB'（英國，雅思常用）或 'US'
    function voiceScore(v, accent) {
        if (!LANG_RE.test(v.lang)) return -1;
        const n = v.name.toLowerCase();
        let score = 10;
        if (n.includes('natural')) score += 100;
        if (n.includes('neural')) score += 90;
        if (n.includes('online')) score += 40;
        if (n.includes('google')) score += 50;
        if (n.includes('premium') || n.includes('enhanced')) score += 45;
        if (n.includes('siri')) score += 35;
        if (/(desktop|espeak|robot|compact)/.test(n)) score -= 30;
        const lang = v.lang.replace('_', '-').toUpperCase();
        if (FOREIGN) score += 0;
        else if (lang === 'EN-' + accent) score += 25;
        else if (lang === 'EN-AU' || lang === 'EN-GB' || lang === 'EN-US') score += 5;
        if (!v.localService) score += 3;
        return score;
    }

    function englishVoices() {
        if (!window.speechSynthesis) return [];
        return speechSynthesis.getVoices().filter(v => voiceScore(v, voiceSettings.accent) >= 0);
    }

    function pickVoice() {
        const voices = englishVoices();
        if (voiceSettings.voiceName) {
            const chosen = voices.find(v => v.name === voiceSettings.voiceName);
            if (chosen) return chosen;
        }
        return voices.sort((a, b) => voiceScore(b, voiceSettings.accent) - voiceScore(a, voiceSettings.accent))[0] || null;
    }

    function saveVoiceSettings() {
        try { localStorage.setItem(VOICE_KEY, JSON.stringify(voiceSettings)); } catch (e) { /* ignore */ }
    }

    // ---------- 發音 ----------
    // 有神經語音的瀏覽器（例如櫃台電腦的 Edge）直接用瀏覽器語音，最快；
    // 其他裝置（特別是 Android 手機：連續播放時會一直唸同一個字）改播伺服器產生的音檔
    // （/tts，見 word_audio.py），產生失敗才退回瀏覽器語音。
    const IS_ANDROID = /android/i.test(navigator.userAgent || '');
    let player = null;       // 共用的 <audio>，播下一個字前先停掉上一個
    let speakSeq = 0;        // 每次發音的編號，舊的回呼不會干擾新的發音
    let serverTtsOk = true;  // 伺服器產生失敗過一次，這個分頁就不再試

    function useServerAudio() {
        if (!serverTtsOk || !window.Audio) return false;
        if (IS_ANDROID) return true;
        if (voiceSettings.voiceName) return false;          // 自己在發音設定選了語音，就照選的
        return voiceQuality() !== 'neural';
    }

    function stopSpeaking() {
        speakSeq += 1;
        if (player) { player.onended = player.onerror = null; player.pause(); }
        if (window.speechSynthesis) speechSynthesis.cancel();
    }

    function speak(text, opts) {
        opts = opts || {};
        const done = opts.onend || (() => {});
        if (!text) { done(); return; }
        stopSpeaking();
        const seq = speakSeq;
        if (useServerAudio()) {
            speakServer(text, opts, seq).catch(() => {
                if (seq !== speakSeq) return;       // 已經換下一個字了
                serverTtsOk = false;
                speakBrowser(text, opts, seq);
            });
        } else {
            speakBrowser(text, opts, seq);
        }
    }

    function speakServer(text, opts, seq) {
        return new Promise((resolve, reject) => {
            if (!player) { player = new Audio(); player.preload = 'auto'; }
            const accent = FOREIGN ? FOREIGN.accent : (voiceSettings.accent === 'US' ? 'US' : 'GB');
            player.onended = () => { if (seq === speakSeq && opts.onend) opts.onend(); };
            player.onerror = () => reject(new Error('音檔載入失敗'));
            player.src = `/tts?accent=${accent}&text=${encodeURIComponent(text)}`;
            const rate = opts.rate || (voiceSettings.rate === 'slow' ? RATES.slow : 1);
            player.defaultPlaybackRate = player.playbackRate = rate;
            if ('preservesPitch' in player) player.preservesPitch = true;
            const p = player.play();
            if (p && p.then) p.then(resolve, (e) => {
                // 瀏覽器擋自動播放（使用者還沒點過頁面）不算伺服器壞掉，不改用瀏覽器語音
                if (e && e.name === 'NotAllowedError') { resolve(); if (opts.onend) setTimeout(opts.onend, 300); return; }
                reject(e);
            });
            else resolve();
        });
    }

    function speakBrowser(text, opts, seq) {
        if (!window.speechSynthesis) { if (opts.onend) opts.onend(); return; }
        const u = new SpeechSynthesisUtterance(text);
        const voice = pickVoice();
        // Android 的 Chrome 指定 voice 時常常出錯，只指定語言比較穩
        if (voice && !IS_ANDROID) { u.voice = voice; u.lang = voice.lang; } else { u.lang = voice ? voice.lang : (FOREIGN ? FOREIGN.bcp : 'en-GB'); }
        voiceQualityWarning();
        // 神經語音本來就唸得自然，用正常速度；機械語音放慢一點比較聽得懂
        let rate = opts.rate || RATES[voiceSettings.rate] || 0.95;
        if (isNatural(voice) && voiceSettings.rate !== 'slow' && !opts.rate) rate = 1;   // 呼叫端指定速度（例如聽寫的慢速）時照指定
        u.rate = rate;
        u.pitch = 1;
        // 口說測驗要知道考官什麼時候唸完，才能開始錄音
        if (opts.onend) { u.onend = u.onerror = () => { if (seq === speakSeq) opts.onend(); }; }
        window.__lastUtterance = u;   // 留住參照，避免某些瀏覽器把還沒唸完的發音回收掉
        // 剛 cancel 就馬上 speak，Android／Chrome 有時會吃掉新的字或重唸舊的字，稍等一下再唸
        setTimeout(() => { if (seq === speakSeq) speechSynthesis.speak(u); }, IS_ANDROID ? 120 : 30);
    }

    // 語音分三級：
    //   neural 神經語音（Edge 的 Natural、iOS 的 Siri）— 最接近真人
    //   good   品質不錯（Chrome 的 Google 網路語音、Premium/Enhanced）— 堪用，但不如神經語音
    //   poor   機械式（Zira Desktop、eSpeak 這類舊語音）
    function voiceTier(v) {
        if (!v) return 'poor';
        const n = v.name.toLowerCase();
        if (/natural|neural|siri/.test(n)) return 'neural';
        if (/google|premium|enhanced/.test(n)) return 'good';
        return 'poor';
    }
    function isNatural(v) { return voiceTier(v) === 'neural'; }

    // 目前這個瀏覽器最好能做到什麼程度
    function voiceQuality() {
        const v = pickVoice();
        return v ? voiceTier(v) : 'none';
    }

    // 只在這個分頁提醒一次，不要一直跳
    // 線條圖示（static/icons.svg），和樣板的 {{ icon('名稱') }} 輸出一樣
    function icon(name) {
        return /^[a-z-]+$/.test(name) ? `<svg class=ui-ic aria-hidden=true><use href=/static/icons.svg#i-${name}></use></svg>` : '';
    }

    const WARN_KEY = 'quiz-voice-warned';
    function voiceQualityWarning() {
        const q = voiceQuality();
        if (q === 'neural' || q === 'good') return;
        try { if (sessionStorage.getItem(WARN_KEY)) return; sessionStorage.setItem(WARN_KEY, '1'); } catch (e) { /* ignore */ }
        const t = document.createElement('div');
        t.className = 'ui-toast';
        t.innerHTML = q === 'none'
            ? icon('alert') + ` 沒有${FOREIGN ? FOREIGN.name : '英文'}語音，請改用 <b>Edge</b> 開啟。`
            : icon('volume') + ' 語音較生硬，改用 <b>Edge</b> 發音更自然。';
        document.body.appendChild(t);
        setTimeout(() => t.remove(), 9000);
    }

    // 語音設定面板（右下角的說話圖示）
    function buildVoicePanel() {
        const btn = document.createElement('button');
        btn.className = 'ui-voice-toggle';
        btn.dataset.sound = 'tap';
        // 一顆有字的按鈕就好：以前右下角兩顆沒字的圓鈕，學生看不懂是什麼
        btn.innerHTML = icon('volume') + '<span>聲音</span>';
        btn.title = '聲音設定（音效、發音）';
        btn.setAttribute('aria-label', '聲音設定');
        const panel = document.createElement('div');
        panel.className = 'ui-voice-panel';
        panel.hidden = true;
        document.body.append(btn, panel);

        function render() {
            const voices = englishVoices().sort((a, b) => voiceScore(b, voiceSettings.accent) - voiceScore(a, voiceSettings.accent));
            const current = pickVoice();
            const mark = { neural: '★ ', good: '☆ ', poor: '' };
            const opt = (v) => `<option value="${v.name.replace(/"/g, '&quot;')}" ${current && v.name === current.name ? 'selected' : ''}>${mark[voiceTier(v)]}${v.name.replace(/</g, '&lt;')}</option>`;
            panel.innerHTML = `
                <div class="vp-title">${icon('volume')} 聲音設定</div>
                <label>按鈕音效
                    <select data-k="sfx">
                        <option value="1" ${soundOn ? 'selected' : ''}>開</option>
                        <option value="0" ${soundOn ? '' : 'selected'}>關</option>
                    </select></label>
                ${FOREIGN ? '' : `<label>口音
                    <select data-k="accent">
                        <option value="GB" ${voiceSettings.accent === 'GB' ? 'selected' : ''}>英國腔（雅思常用）</option>
                        <option value="US" ${voiceSettings.accent === 'US' ? 'selected' : ''}>美國腔</option>
                    </select></label>`}
                <label>語速
                    <select data-k="rate">
                        <option value="normal" ${voiceSettings.rate === 'normal' ? 'selected' : ''}>正常</option>
                        <option value="slow" ${voiceSettings.rate === 'slow' ? 'selected' : ''}>慢速</option>
                    </select></label>
                <label>語音 ${voices.length ? '' : `<span class="vp-bad">（找不到${FOREIGN ? FOREIGN.name : '英文'}語音）</span>`}
                    <select data-k="voiceName" ${voices.length ? '' : 'disabled'}>
                        <option value="">自動挑最像真人的</option>${voices.map(opt).join('')}
                    </select></label>
                <div class="vp-note">${voices.length ? ({
                        neural: icon('check-circle') + ' 真人級語音：' + (current ? current.name.replace(/</g, '&lt;') : ''),
                        good: icon('smile') + ' 品質不錯：' + (current ? current.name.replace(/</g, '&lt;') : '')
                              + '<br>改用 <b>Edge</b> 更自然。',
                        poor: icon('alert') + ' 目前是機械式語音：' + (current ? current.name.replace(/</g, '&lt;') : '')
                              + '<br>改用 <b>Edge</b> 發音更自然。'
                    }[voiceTier(current)])
                    : `沒有${FOREIGN ? FOREIGN.name : '英文'}語音，請改用 <b>Edge</b> 開啟。`}</div>
                <button class="vp-test" data-sound="none">${icon('volume')} 試聽</button>`;
            panel.querySelectorAll('select').forEach(sel => sel.addEventListener('change', () => {
                if (sel.dataset.k === 'sfx') {
                    soundOn = sel.value === '1';
                    try { localStorage.setItem(STORE_KEY, soundOn ? '1' : '0'); } catch (e) { /* ignore */ }
                    play('tap');
                    return;
                }
                voiceSettings[sel.dataset.k] = sel.value;
                if (sel.dataset.k === 'accent') voiceSettings.voiceName = '';
                saveVoiceSettings();
                render();
            }));
            panel.querySelector('.vp-test').addEventListener('click', () =>
                speak(FOREIGN ? FOREIGN.test : 'The climate is becoming warmer. Welcome to your IELTS practice.'));
        }
        btn.addEventListener('click', () => { panel.hidden = !panel.hidden; if (!panel.hidden) render(); });
        document.addEventListener('click', (e) => {
            if (!panel.hidden && !panel.contains(e.target) && !btn.contains(e.target)) panel.hidden = true;
        });
        if (window.speechSynthesis) speechSynthesis.addEventListener('voiceschanged', () => { if (!panel.hidden) render(); });
    }
    // 有些瀏覽器要先呼叫一次才會開始載入語音清單
    if (window.speechSynthesis) speechSynthesis.getVoices();

    // 音效開關併進「聲音」面板（右下角只留一顆按鈕）
    document.addEventListener('DOMContentLoaded', buildVoicePanel);

    // 長單字（administrative、authorization…）在手機上會被硬切成兩行。
    // fitText 讓文字維持一行、依可用寬度自動縮小字級；縮到 min 還放不下才在空白處換行（片語），
    // 再放不下（沒有空白的超長字）才允許字中斷行，總之絕不超出卡片。
    // 可用寬度＝外層寬度扣掉旁邊的按鈕；opts.avoid 是疊在上面的浮動元素（例如收藏星星），
    // 和這一行上下重疊時兩邊各讓出它佔的寬度，文字維持置中。
    // 量寬度時扣掉卡片進場動畫的縮放，而且反覆縮到真的放得下：
    // Android 手機把「字型大小」調大時，瀏覽器會再放大字級，只算一次會不夠小（2026-11 長單字跑出卡片）。
    // 視窗大小、外層寬度改變、字型載入完成時都會自動重算。
    const fitted = new Map();
    function fitText(el, opts) {
        if (!el || !el.parentElement) return;
        if (typeof opts === 'number') opts = { min: opts };
        opts = Object.assign({ min: 18, avoid: [] }, fitted.get(el), opts || {});
        fitted.set(el, opts);
        watchBox(el);
        Object.assign(el.style, { fontSize: '', whiteSpace: 'nowrap', wordBreak: 'normal', overflowWrap: 'normal', flexShrink: '0', minWidth: '', maxWidth: '' });
        const box = el.parentElement, cs = getComputedStyle(box);
        const gap = parseFloat(cs.columnGap) || 0;
        let avail = box.clientWidth - parseFloat(cs.paddingLeft || 0) - parseFloat(cs.paddingRight || 0);
        // 卡片進場動畫有縮放：量到的寬度除以外層的縮放比例，換回排版寬度
        const br = box.getBoundingClientRect();
        const k = (box.offsetWidth && br.width / box.offsetWidth) || 1;
        const widthOf = (n) => n.getBoundingClientRect().width / k;
        for (const c of box.children) {
            if (c !== el && getComputedStyle(c).position !== 'absolute') avail -= widthOf(c) + (gap || 8);
        }
        // 浮動按鈕（收藏星星）和這一行上下重疊時，兩邊各讓出它伸進來的寬度
        for (const a of opts.avoid) {
            if (!a || !a.isConnected || a.offsetParent === null) continue;
            const r = a.getBoundingClientRect();
            if (r.bottom <= br.top || r.top >= br.bottom) continue;
            const into = Math.max(0, Math.min(br.right, r.right) - Math.max(br.left, r.left));
            const fromEdge = Math.min(r.right - br.left, br.right - r.left);   // 靠哪一邊就從哪一邊算
            if (into > 0) avail -= (2 * Math.min(fromEdge, br.width / 2)) / k + 4;
        }
        if (avail <= 0) return;   // 還沒排版（隱藏中），之後再算
        let size = parseFloat(getComputedStyle(el).fontSize);
        const shrinkTo = (min) => {
            for (let i = 0; i < 8 && widthOf(el) > avail && size > min; i++) {
                size = Math.max(min, Math.floor(size * avail / widthOf(el) * 100) / 100 - 0.5);
                el.style.fontSize = size + 'px';
            }
        };
        shrinkTo(opts.min);
        // 片語到最小字級就在空白處換行；沒有空白的超長單字再縮小一點
        if (!/\s/.test(el.textContent.trim())) shrinkTo(Math.min(opts.min, 13));
        if (widthOf(el) > avail + 1) {
            // 最小字級還放不下（很長的片語）：先只在空白處換行，真的不行才讓字斷開
            Object.assign(el.style, { whiteSpace: 'normal', flexShrink: '1', minWidth: '0', maxWidth: avail + 'px' });
            if (el.scrollWidth > el.clientWidth + 1) el.style.overflowWrap = 'anywhere';
        }
    }
    function refitAll() { fitted.forEach((o, el) => el.isConnected ? fitText(el) : fitted.delete(el)); }
    // 外層寬度改變（版面晚一步排好、手機轉向、字型放大）時重算
    const ro = window.ResizeObserver ? new ResizeObserver(() => { clearTimeout(fitTimer); fitTimer = setTimeout(refitAll, 60); }) : null;
    const watched = new WeakSet();
    function watchBox(el) {
        const box = el.parentElement;
        if (ro && box && !watched.has(box)) { watched.add(box); ro.observe(box); }
    }
    let fitTimer = null;
    window.addEventListener('resize', () => { clearTimeout(fitTimer); fitTimer = setTimeout(refitAll, 100); });
    if (document.fonts && document.fonts.ready) document.fonts.ready.then(refitAll);

    window.UI = { icon, play, ripple, speak, voiceScore, voiceQuality, voiceTier, fitText };
})();
