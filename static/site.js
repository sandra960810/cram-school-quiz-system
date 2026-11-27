/* 驅勢官網的科技感互動（2026-11 使用者要求「整個網站的交互設計改得更有科技感」）
   - 捲到時才浮現（區塊依序滑入）
   - 眉標像終端機一個字一個字打出來、編號像解碼一樣跳數字
   - 卡片與列表跟著滑鼠的霧藍光暈（--mx、--my）
   - 頁首下緣的閱讀進度線
   使用者電腦設定「減少動態效果」時全部不做，內容照常顯示；沒有 JS 也照常顯示。 */
(function () {
    'use strict';
    var reduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    var root = document.documentElement;
    root.classList.add('s-js');

    /* 跟著滑鼠的光暈：不算動畫，減少動態時也保留 */
    var GLOW = '.h-row, .s-card, .mk-entry, .h-why-cols > div, .h-enroll-list > div, .mk-opts label, .s-foot-go';
    document.addEventListener('pointermove', function (e) {
        var el = e.target.closest && e.target.closest(GLOW);
        if (!el) return;
        var r = el.getBoundingClientRect();
        el.style.setProperty('--mx', (e.clientX - r.left) + 'px');
        el.style.setProperty('--my', (e.clientY - r.top) + 'px');
    }, { passive: true });
    document.querySelectorAll(GLOW).forEach(function (el) { el.classList.add('t-glow'); });

    /* 閱讀進度線 */
    var head = document.querySelector('.s-head');
    if (head) {
        var bar = document.createElement('span');
        bar.className = 's-progress';
        bar.setAttribute('aria-hidden', 'true');
        head.appendChild(bar);
        var tick = function () {
            var max = document.documentElement.scrollHeight - window.innerHeight;
            bar.style.transform = 'scaleX(' + (max > 0 ? Math.min(1, window.scrollY / max) : 0) + ')';
        };
        window.addEventListener('scroll', tick, { passive: true });
        tick();
    }

    /* 首頁 AI 線上模考的展開卡片（電腦）：一開始全部閉合、平均分配寬度佔滿整排；
       滑鼠移到哪張就展開哪張（停 0.12 秒才開，避免滑過去時一路亂開），滑鼠離開整排就全部閉合回平均。
       觸控平板用點的；鍵盤 Tab 到哪張就展開哪張。不自動輪播（2026-11 使用者要求預設全部閉合）。
       手機（760px 以下）四條上下排列，點哪條就展開哪條；展開高度依內容量（--open-h），展開後捲到看得到 */
    var phone = window.matchMedia('(max-width: 760px)');
    document.querySelectorAll('[data-acc]').forEach(function (acc) {
        var items = Array.prototype.slice.call(acc.querySelectorAll('[data-acc-item]'));
        if (items.length < 2) return;
        var intent = null, leave = null;
        acc.classList.add('is-ready');
        function open(i) {
            items.forEach(function (it, j) {
                var on = j === i;
                it.classList.toggle('is-on', on);
                it.querySelector('.h-acc-tab').setAttribute('aria-expanded', on ? 'true' : 'false');
                it.querySelector('.h-acc-body').inert = !on;
            });
            acc.classList.toggle('has-open', i >= 0);
            fit();
        }
        /* 手機：量每張內容的高度，展開就是剛好那麼高 */
        function fit() {
            items.forEach(function (it) {
                if (phone.matches) it.style.setProperty('--open-h', it.querySelector('.h-acc-body').scrollHeight + 'px');
                else it.style.removeProperty('--open-h');
            });
        }
        items.forEach(function (it, i) {
            var tab = it.querySelector('.h-acc-tab');
            tab.addEventListener('click', function () {
                open(i);
                if (!phone.matches) return;
                /* 上面那條收起來後畫面會位移：動畫結束後，展開的那張沒完整露出就捲過去 */
                setTimeout(function () {
                    var r = it.getBoundingClientRect(), head = document.querySelector('.s-head'),
                        top = (head ? head.getBoundingClientRect().bottom : 0) + 12;
                    if (r.top < top || r.bottom > window.innerHeight) window.scrollTo({ top: window.scrollY + r.top - top, behavior: reduce ? 'auto' : 'smooth' });
                }, reduce ? 0 : 780);
            });
            tab.addEventListener('focus', function () { if (!phone.matches) open(i); });
            it.addEventListener('pointerenter', function (e) {
                if (e.pointerType !== 'mouse' || phone.matches) return;
                clearTimeout(leave);
                clearTimeout(intent);
                if (it.classList.contains('is-on')) return;
                intent = setTimeout(function () { open(i); }, 120);
            });
        });
        acc.addEventListener('pointerleave', function (e) {
            if (e.pointerType !== 'mouse' || phone.matches) return;
            clearTimeout(intent);
            leave = setTimeout(function () { open(-1); }, 250);
        });
        acc.addEventListener('focusout', function (e) { if (!acc.contains(e.relatedTarget) && !acc.matches(':hover')) open(-1); });

        phone.addEventListener('change', function () { open(-1); });
        window.addEventListener('resize', fit, { passive: true });
        window.addEventListener('load', fit);
        open(-1);
    });

    /* 首頁標題的科技感動態（2026-11 使用者要求「標題也要有交互、科技感的動態」）：
       1 進場時每個字先跳亂碼再依序定格（解碼）
       2 滑鼠在標題區移動時，背後的細格線跟著滑鼠亮起來
       （原本「多益」會每 3 秒輪播成其他考試，2026-11 使用者要求「先多益就好，不要輪播」，已拿掉） */
    (function heroTitle() {
        var h = document.querySelector('[data-hero-title]');
        if (!h) return;
        var box = h.closest('.h-hero-txt') || h;
        box.addEventListener('pointermove', function (e) {
            var r = box.getBoundingClientRect();
            box.style.setProperty('--hx', (e.clientX - r.left) + 'px');
            box.style.setProperty('--hy', (e.clientY - r.top) + 'px');
        }, { passive: true });
        if (reduce) return;
        var POOL = '01<>/#*+=?%&ABCDEFXZ';
        var segs = Array.prototype.slice.call(h.querySelectorAll('.h-t-seg, .h-t-word'));
        h.setAttribute('aria-label', h.textContent);
        function rnd() { return POOL[Math.floor(Math.random() * POOL.length)]; }
        /* el 的文字從亂碼一個字一個字定格成 to；start 毫秒後開始，每個字間隔 step 毫秒 */
        function decode(el, to, start, step, done) {
            var chars = to.split(''), fixed = 0, t0 = null;
            el.classList.add('is-scr');
            function frame(ts) {
                if (t0 === null) t0 = ts;
                var pass = ts - t0 - start;
                fixed = Math.max(0, Math.min(chars.length, Math.floor(pass / step)));
                var out = '';
                for (var i = 0; i < chars.length; i++) out += i < fixed ? chars[i] : (pass < -120 && i > 0 ? '\u00a0' : rnd());
                el.textContent = out;
                if (fixed < chars.length) requestAnimationFrame(frame);
                else { el.textContent = to; el.classList.remove('is-scr'); if (done) done(); }
            }
            requestAnimationFrame(frame);
        }
        /* 1 進場解碼 */
        var at = 150;
        segs.forEach(function (el) {
            var to = el.textContent;
            el.textContent = to.replace(/./g, '\u00a0');
            decode(el, to, at, 70);
            at += to.length * 70 + 40;
        });
    })();

    if (reduce || !('IntersectionObserver' in window)) return;

    /* 捲到時浮現：同一個父元素裡的依序延遲 */
    var REVEAL = '.h-big, .h-sec-head, .h-acc, .h-row, .h-why-cols > div, .h-enroll-list > div, .h-path li, ' +
                 '.h-story-photo, .h-split-side img, .s-card, .s-steps li, .s-sec h2, .mk-entry, .mk-r, .mk-ai, .mk-est, .s-foot .cols > div';
    var items = Array.prototype.slice.call(document.querySelectorAll(REVEAL));
    var vh = window.innerHeight;
    items.forEach(function (el) {
        if (el.getBoundingClientRect().top < vh * 0.92) return;   // 第一眼看得到的不動，避免閃一下
        var sib = el.parentElement ? Array.prototype.indexOf.call(el.parentElement.children, el) : 0;
        el.classList.add('t-rv');
        el.style.setProperty('--d', Math.min(sib, 6) * 70 + 'ms');
    });
    var io = new IntersectionObserver(function (es) {
        es.forEach(function (en) {
            if (!en.isIntersecting) return;
            en.target.classList.add('t-in');
            io.unobserve(en.target);
        });
    }, { rootMargin: '0px 0px -8% 0px' });
    items.forEach(function (el) { if (el.classList.contains('t-rv')) io.observe(el); });
    /* 列印時全部直接顯示 */
    window.addEventListener('beforeprint', function () { items.forEach(function (el) { el.classList.add('t-in'); }); });

    /* 眉標打字效果、編號解碼效果 */
    var GLYPHS = '0123456789ABCDEF<>/#';
    function typeIn(el) {
        var full = el.textContent;
        el.setAttribute('aria-label', full);
        var i = 0;
        el.classList.add('t-typing');
        el.textContent = '';
        var step = function () {
            i += 1;
            el.textContent = full.slice(0, i);
            if (i < full.length) setTimeout(step, 38);
            else setTimeout(function () { el.classList.remove('t-typing'); }, 900);
        };
        step();
    }
    function decode(el) {
        var full = el.textContent, n = 0;
        var timer = setInterval(function () {
            n += 1;
            if (n > 8) { el.textContent = full; clearInterval(timer); return; }
            el.textContent = full.replace(/[0-9A-Za-z]/g, function () { return GLYPHS[Math.floor(Math.random() * GLYPHS.length)]; });
        }, 45);
    }
    var fx = new IntersectionObserver(function (es) {
        es.forEach(function (en) {
            if (!en.isIntersecting) return;
            fx.unobserve(en.target);
            if (en.target.classList.contains('s-eyebrow')) typeIn(en.target); else decode(en.target);
        });
    }, { rootMargin: '0px 0px -10% 0px' });
    document.querySelectorAll('.s-eyebrow.lined, .h-cat-no, .h-row-no, .h-why-cols span').forEach(function (el) {
        if (el.children.length) return;   // 裡面有圖示或連結的不動
        fx.observe(el);
    });
})();

