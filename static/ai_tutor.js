// AI 學習教練的共用前端（程式說明見 ai_tutor.py）
//
// 1. 錯題解釋：樣板用 {{ ai_slot('ielts', section=..., test_key=..., qno=...) }} 放一個 <div class="ai-slot">，
//    這裡把它變成「問 AI 老師」按鈕；動態產生的畫面（背單字神器成績頁）用 AITutor.slot() 產生 HTML，再呼叫 AITutor.mount()。
// 2. 單字記憶法：AITutor.wordHelp(容器, 學生id, 單字id)
// 不用 emoji，圖示用 UI.icon()。
(function () {
    // 和 UI.icon 一樣（模擬考作答頁沒有載入 ui.js，所以自己產生）
    const ic = (n) => /^[a-z-]+$/.test(n) ? `<svg class=ui-ic aria-hidden=true><use href=/static/icons.svg#i-${n}></use></svg>` : '';
    const esc = (s) => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
    const NOTE = 'AI 老師的解釋可能有錯，以題庫解析和老師講解為準。';

    async function post(url, body) {
        let res, data;
        try {
            res = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body || {}) });
            data = await res.json();
        } catch (e) {
            throw new Error('連不上網站，請檢查網路後再按一次。');
        }
        if (!res.ok || !data.ok) throw new Error(data && data.error || ('發生錯誤（' + res.status + '）'));
        return data;
    }

    function waiting(text) {
        return `<div class="ai-wait"><span class="ai-dots"><i></i><i></i><i></i></span>${esc(text || 'AI 老師思考中，大約 10–30 秒…')}</div>`;
    }

    // 「再練一題」：點選項馬上對答案
    function drill(p, langAttr) {
        if (!p) return '';
        return `<div class="ai-drill"><div class="ai-h">${ic('target')} 再練一題</div>
            <div class="ai-q"${langAttr}>${esc(p.question)}</div>
            <div class="ai-opts">${p.options.map((o, i) => `<button class="ai-opt" data-i="${i}" data-sound="tap"${langAttr}>${esc(o)}</button>`).join('')}</div>
            <div class="ai-drill-fb" hidden></div></div>`;
    }

    function bindDrill(box, p) {
        if (!p) return;
        const fb = box.querySelector('.ai-drill-fb');
        box.querySelectorAll('.ai-opt').forEach(b => b.addEventListener('click', () => {
            const i = +b.dataset.i;
            box.querySelectorAll('.ai-opt').forEach(x => {
                x.disabled = true;
                if (+x.dataset.i === p.answer) x.classList.add('right');
                else if (x === b) x.classList.add('wrong');
            });
            if (window.UI) UI.play(i === p.answer ? 'right' : 'error');
            fb.hidden = false;
            fb.className = 'ai-drill-fb ' + (i === p.answer ? 'ok' : 'bad');
            fb.innerHTML = (i === p.answer ? '✓ 答對了！' : '✗ 再想想，正解已標成綠色。') + (p.explain ? ' ' + esc(p.explain) : '');
        }));
    }

    function renderExplain(box, r, lang) {
        const la = lang ? ` lang="${esc(lang)}"` : '';
        const sec = (iconName, title, text) => text ? `<div class="ai-sec"><div class="ai-h">${ic(iconName)} ${title}</div><div class="ai-t">${esc(text)}</div></div>` : '';
        box.innerHTML = `<div class="ai-card">
            <div class="ai-top">${ic('bot')} <b>AI 老師解釋</b></div>
            ${sec('x-circle', '你的答案為什麼不對', r.why_wrong)}
            ${sec('check-circle', '正解的根據', r.why_right)}
            ${sec('alert', '這題的陷阱', r.trap)}
            ${sec('bulb', '下次這樣判斷', r.tip)}
            ${drill(r.practice, la)}
            <div class="ai-note">${NOTE}</div></div>`;
        bindDrill(box, r.practice);
    }

    function mountSlot(slot) {
        if (slot.dataset.mounted) return;
        slot.dataset.mounted = '1';
        const sid = slot.dataset.sid;
        const ref = JSON.parse(slot.dataset.ai || '{}');
        const lang = ref.kind === 'jlpt' ? 'ja' : ref.kind === 'topik' ? 'ko' : (ref.lang || '');
        slot.innerHTML = `<button class="ai-btn" data-sound="tap">${ic('bot')} 問 AI 老師：我為什麼錯？</button><div class="ai-out"></div>`;
        const btn = slot.querySelector('.ai-btn');
        const out = slot.querySelector('.ai-out');
        btn.addEventListener('click', async () => {
            btn.disabled = true;
            out.innerHTML = waiting();
            try {
                const data = await post(`/api/ai/${sid}/explain`, ref);
                btn.remove();
                renderExplain(out, data.result, lang);
            } catch (e) {
                btn.disabled = false;
                out.innerHTML = `<div class="ai-err">${ic('alert')} ${esc(e.message)}</div>`;
            }
        });
    }

    function mount(root) {
        (root || document).querySelectorAll('.ai-slot').forEach(mountSlot);
    }

    // 動態畫面用：產生和 ai_slot() 一樣的 HTML
    function slot(sid, ref) {
        return `<div class="ai-slot" data-sid="${esc(sid)}" data-ai="${esc(JSON.stringify(ref))}"></div>`;
    }

    // ---------- 單字記憶法 ----------
    function renderWord(box, r, lang) {
        const la = lang ? ` lang="${esc(lang)}"` : '';
        const list = (arr, f) => (arr || []).length ? `<ul>${arr.map(f).join('')}</ul>` : '';
        box.innerHTML = `<div class="ai-card ai-wordcard">
            <div class="ai-top">${ic('bot')} <b>AI 記憶法</b></div>
            ${r.mnemonic ? `<div class="ai-sec"><div class="ai-h">${ic('bulb')} 記憶口訣</div><div class="ai-t">${esc(r.mnemonic)}</div></div>` : ''}
            ${r.roots ? `<div class="ai-sec"><div class="ai-h">${ic('puzzle')} 拆解</div><div class="ai-t">${esc(r.roots)}</div></div>` : ''}
            ${(r.examples || []).length ? `<div class="ai-sec"><div class="ai-h">${ic('book-open')} 更多例句</div>${list(r.examples, e => `<li><span${la}>${esc(e.sentence)}</span> <button class="ai-say" data-say="${esc(e.sentence)}" data-sound="none" aria-label="播放例句">${ic('volume')}</button><br><small>${esc(e.zh)}</small></li>`)}</div>` : ''}
            ${(r.collocations || []).length ? `<div class="ai-sec"><div class="ai-h">${ic('tag')} 常用搭配</div>${list(r.collocations, c => `<li><b${la}>${esc(c.phrase)}</b>　${esc(c.zh)}</li>`)}</div>` : ''}
            ${(r.confusables || []).length ? `<div class="ai-sec"><div class="ai-h">${ic('alert')} 別搞混</div>${list(r.confusables, c => `<li><b${la}>${esc(c.word)}</b>：${esc(c.diff)}</li>`)}</div>` : ''}
            <div class="ai-note">AI 產生的內容可能有錯，以老師講解為準。</div></div>`;
        box.querySelectorAll('.ai-say').forEach(b => b.addEventListener('click', (e) => { e.stopPropagation(); if (window.UI) UI.speak(b.dataset.say); }));
    }

    async function wordHelp(box, sid, vocabId, lang) {
        box.innerHTML = waiting('AI 老師正在想記憶方法…');
        try {
            const data = await post(`/api/ai/${sid}/word/${vocabId}`);
            renderWord(box, data.result, lang);
        } catch (e) {
            box.innerHTML = `<div class="ai-err">${ic('alert')} ${esc(e.message)}</div>`;
        }
    }

    window.AITutor = { mount, slot, post, wordHelp, waiting, esc };
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', () => mount());
    else mount();
})();
