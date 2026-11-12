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
    });

    window.UI = { play, ripple };
})();
