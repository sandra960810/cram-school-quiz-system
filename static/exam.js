/* 測驗作答頁共用：計時、已作答題數、交卷提醒、離開前提醒、作答暫存 */
(function () {
    const form = document.getElementById('examForm');
    if (!form) return;

    const section = form.getAttribute('action').includes('/reading/') ? 'reading' : 'listening';
    const DRAFT_KEY = 'exam-draft-test3-' + section;
    const total = new Set([...form.querySelectorAll('[data-q]')].map(el => el.dataset.q)).size;
    const doneEl = document.getElementById('done');
    let submitted = false;

    function answeredCount() {
        const done = new Set();
        form.querySelectorAll('[data-q]').forEach(el => {
            if (el.type === 'radio') { if (el.checked) done.add(el.dataset.q); }
            else if (String(el.value || '').trim()) done.add(el.dataset.q);
        });
        return done;
    }

    function refresh() {
        const done = answeredCount();
        if (doneEl) doneEl.innerText = done.size;
        saveDraft();
        return done;
    }

    // 作答暫存：不小心關掉或重新整理也不會全部不見
    function saveDraft() {
        const data = {};
        form.querySelectorAll('[data-q]').forEach(el => {
            if (el.type === 'radio') { if (el.checked) data[el.dataset.q] = el.value; }
            else if (String(el.value || '').trim()) data[el.dataset.q] = el.value;
        });
        try { localStorage.setItem(DRAFT_KEY, JSON.stringify(data)); } catch (e) { /* ignore */ }
    }

    function loadDraft() {
        let data;
        try { data = JSON.parse(localStorage.getItem(DRAFT_KEY) || '{}'); } catch (e) { return; }
        if (!data || !Object.keys(data).length) return;
        form.querySelectorAll('[data-q]').forEach(el => {
            const v = data[el.dataset.q];
            if (v === undefined) return;
            if (el.type === 'radio') el.checked = (el.value === v);
            else el.value = v;
        });
    }

    form.addEventListener('input', refresh);
    form.addEventListener('change', refresh);

    // 計時（只是參考，不會自動交卷）
    const timerEl = document.getElementById('timer');
    if (timerEl) {
        const limit = parseInt(timerEl.dataset.limit || '0', 10);   // 分鐘，0 表示不限
        const start = Date.now();
        setInterval(() => {
            const s = Math.floor((Date.now() - start) / 1000);
            timerEl.innerText = String(Math.floor(s / 60)).padStart(2, '0') + ':' + String(s % 60).padStart(2, '0');
            if (limit && s > limit * 60) timerEl.classList.add('over');
        }, 1000);
        if (limit) timerEl.title = `建議作答時間 ${limit} 分鐘`;
    }

    form.addEventListener('submit', (e) => {
        const done = answeredCount();
        if (done.size < total) {
            const miss = [];
            form.querySelectorAll('[data-q]').forEach(el => {
                if (!done.has(el.dataset.q) && !miss.includes(el.dataset.q)) miss.push(el.dataset.q);
            });
            if (!confirm(`還有 ${total - done.size} 題沒作答（第 ${miss.slice(0, 8).join('、')}${miss.length > 8 ? '…' : ''} 題）。\n確定要交卷嗎？`)) {
                e.preventDefault();
                return;
            }
        }
        submitted = true;
        try { localStorage.removeItem(DRAFT_KEY); } catch (err) { /* ignore */ }
    });

    window.addEventListener('beforeunload', (e) => {
        if (!submitted && answeredCount().size) { e.preventDefault(); e.returnValue = ''; }
    });

    loadDraft();
    refresh();
})();
