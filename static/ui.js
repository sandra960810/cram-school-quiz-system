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
    const VOICE_KEY = 'quiz-voice-settings';
    let voiceSettings = { accent: 'GB', rate: 'normal', voiceName: '' };
    try { Object.assign(voiceSettings, JSON.parse(localStorage.getItem(VOICE_KEY) || '{}')); } catch (e) { /* ignore */ }
    const RATES = { slow: 0.75, normal: 0.95 };

    // 分數越高越像真人；accent 是 'GB'（英國，雅思常用）或 'US'
    function voiceScore(v, accent) {
        if (!/^en[-_]/i.test(v.lang)) return -1;
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
        if (lang === 'EN-' + accent) score += 25;
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

    function speak(text, opts) {
        if (!text || !window.speechSynthesis) return;
        speechSynthesis.cancel();
        const u = new SpeechSynthesisUtterance(text);
        const voice = pickVoice();
        if (voice) { u.voice = voice; u.lang = voice.lang; } else { u.lang = 'en-GB'; noEnglishWarning(); }
        u.rate = (opts && opts.rate) || RATES[voiceSettings.rate] || 0.95;
        u.pitch = 1;
        speechSynthesis.speak(u);
    }

    let warned = false;
    function noEnglishWarning() {
        if (warned) return;
        warned = true;
        const t = document.createElement('div');
        t.className = 'ui-toast';
        t.innerHTML = '⚠️ 這個瀏覽器沒有英文語音，發音會不自然。<br>建議用 <b>Microsoft Edge</b> 或 <b>Google Chrome</b> 開啟本網站。';
        document.body.appendChild(t);
        setTimeout(() => t.remove(), 7000);
    }

    // 語音設定面板（右下角 🗣️）
    function buildVoicePanel() {
        const btn = document.createElement('button');
        btn.className = 'ui-voice-toggle';
        btn.dataset.sound = 'tap';
        btn.textContent = '🗣️';
        btn.title = '發音設定';
        btn.setAttribute('aria-label', '發音設定');
        const panel = document.createElement('div');
        panel.className = 'ui-voice-panel';
        panel.hidden = true;
        document.body.append(btn, panel);

        function render() {
            const voices = englishVoices().sort((a, b) => voiceScore(b, voiceSettings.accent) - voiceScore(a, voiceSettings.accent));
            const current = pickVoice();
            const opt = (v) => `<option value="${v.name.replace(/"/g, '&quot;')}" ${current && v.name === current.name ? 'selected' : ''}>${v.name.replace(/</g, '&lt;')}</option>`;
            panel.innerHTML = `
                <div class="vp-title">🗣️ 發音設定</div>
                <label>口音
                    <select data-k="accent">
                        <option value="GB" ${voiceSettings.accent === 'GB' ? 'selected' : ''}>英國腔（雅思常用）</option>
                        <option value="US" ${voiceSettings.accent === 'US' ? 'selected' : ''}>美國腔</option>
                    </select></label>
                <label>語速
                    <select data-k="rate">
                        <option value="normal" ${voiceSettings.rate === 'normal' ? 'selected' : ''}>正常</option>
                        <option value="slow" ${voiceSettings.rate === 'slow' ? 'selected' : ''}>慢速</option>
                    </select></label>
                <label>語音 ${voices.length ? '' : '<span class="vp-bad">（找不到英文語音）</span>'}
                    <select data-k="voiceName" ${voices.length ? '' : 'disabled'}>
                        <option value="">自動挑最像真人的</option>${voices.map(opt).join('')}
                    </select></label>
                <div class="vp-note">${voices.length
                    ? (current && /natural|neural|google|premium|enhanced/i.test(current.name)
                        ? '✅ 目前使用：' + current.name.replace(/</g, '&lt;')
                        : '目前使用：' + (current ? current.name.replace(/</g, '&lt;') : '') + '<br>想要更像真人的發音，請用 Microsoft Edge 開啟（有 Natural 真人語音）。')
                    : '這個瀏覽器沒有英文語音。請改用 Microsoft Edge 或 Google Chrome 開啟本網站。'}</div>
                <button class="vp-test" data-sound="none">🔊 試聽</button>`;
            panel.querySelectorAll('select').forEach(sel => sel.addEventListener('change', () => {
                voiceSettings[sel.dataset.k] = sel.value;
                if (sel.dataset.k === 'accent') voiceSettings.voiceName = '';
                saveVoiceSettings();
                render();
            }));
            panel.querySelector('.vp-test').addEventListener('click', () =>
                speak('The climate is becoming warmer. Welcome to your IELTS practice.'));
        }
        btn.addEventListener('click', () => { panel.hidden = !panel.hidden; if (!panel.hidden) render(); });
        document.addEventListener('click', (e) => {
            if (!panel.hidden && !panel.contains(e.target) && e.target !== btn) panel.hidden = true;
        });
        if (window.speechSynthesis) speechSynthesis.addEventListener('voiceschanged', () => { if (!panel.hidden) render(); });
    }
    // 有些瀏覽器要先呼叫一次才會開始載入語音清單
    if (window.speechSynthesis) speechSynthesis.getVoices();

    function renderToggle(btn) {
        btn.textContent = soundOn ? '🔊' : '🔇';
        btn.title = soundOn ? '音效：開（點一下關閉）' : '音效：關（點一下開啟）';
        btn.setAttribute('aria-label', btn.title);
    }

    document.addEventListener('DOMContentLoaded', () => {
        const btn = document.createElement('button');
        btn.className = 'ui-sound-toggle';
        btn.dataset.sound = 'none';
        btn.addEventListener('click', () => {
            soundOn = !soundOn;
            try { localStorage.setItem(STORE_KEY, soundOn ? '1' : '0'); } catch (e) { /* ignore */ }
            renderToggle(btn);
            play('tap');
        });
        renderToggle(btn);
        document.body.appendChild(btn);
        buildVoicePanel();
    });

    window.UI = { play, ripple, speak, voiceScore };
})();
