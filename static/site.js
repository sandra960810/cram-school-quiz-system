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

    /* 首頁 AI 線上模考的展開卡片：點直條換它展開；每 6 秒自動換下一張，
       滑鼠移上去、點過、捲出畫面時停住（減少動態時不自動換） */
    document.querySelectorAll('[data-acc]').forEach(function (acc) {
        var items = Array.prototype.slice.call(acc.querySelectorAll('[data-acc-item]'));
        if (items.length < 2) return;
        var cur = 0, stopped = false, hover = false, seen = false, AUTO = 6000, timer = null;
        acc.classList.add('is-ready');
        acc.style.setProperty('--auto', AUTO + 'ms');
        function open(i) {
            items.forEach(function (it, j) {
                var on = j === i;
                it.classList.toggle('is-on', on);
                it.querySelector('.h-acc-tab').setAttribute('aria-expanded', on ? 'true' : 'false');
                it.querySelector('.h-acc-body').inert = !on;
            });
            cur = i;
        }
        function schedule() {
            clearTimeout(timer);
            var go = !reduce && !stopped && !hover && seen;
            acc.classList.toggle('is-auto', go);
            if (go) timer = setTimeout(function () { open((cur + 1) % items.length); schedule(); }, AUTO);
        }
        items.forEach(function (it, i) {
            it.querySelector('.h-acc-tab').addEventListener('click', function () { stopped = true; open(i); schedule(); });
        });
        acc.addEventListener('pointerenter', function () { hover = true; schedule(); });
        acc.addEventListener('pointerleave', function () { hover = false; schedule(); });
        acc.addEventListener('focusin', function () { stopped = true; schedule(); });
        if ('IntersectionObserver' in window) {
            new IntersectionObserver(function (es) { seen = es[0].isIntersecting; schedule(); }, { threshold: 0.4 }).observe(acc);
        }
        open(0);
    });

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
