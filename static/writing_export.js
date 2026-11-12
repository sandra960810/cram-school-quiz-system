/* 寫作作答輸出：把題目與學生的作文排成 A4 頁面，下載成 PDF 或 PNG 圖片。
   全部在瀏覽器裡完成，不需要額外安裝套件，也不用連網。 */
window.WritingExport = (function () {
    const PAGE_W = 1240, PAGE_H = 1754, MARGIN = 96;      // A4 @150dpi
    const FONT = '"Microsoft JhengHei", "PingFang TC", "Noto Sans CJK TC", Arial, sans-serif';
    const TASKS = [{ n: 1, min: 150 }, { n: 2, min: 250 }];
    let info = { student: '', title: '' };

    function countWords(text) { return (text.trim().match(/[^\s]+/g) || []).length; }

    // 把一段文字依寬度折行：英文以單字為單位，中文可以逐字斷行
    function wrap(ctx, text, maxW) {
        const lines = [];
        text.replace(/\r/g, '').split('\n').forEach(par => {
            if (!par.trim()) { lines.push(''); return; }
            const tokens = par.match(/[⺀-鿿豈-﫿＀-￯]|[^\s⺀-鿿豈-﫿＀-￯]+|\s+/g) || [];
            let line = '';
            tokens.forEach(tok => {
                if (ctx.measureText(line + tok).width <= maxW) { line += tok; return; }
                if (line.trim()) lines.push(line.replace(/\s+$/, ''));
                line = /^\s+$/.test(tok) ? '' : tok;
                while (ctx.measureText(line).width > maxW) {        // 超長的一串字硬切
                    let cut = line.length - 1;
                    while (cut > 1 && ctx.measureText(line.slice(0, cut)).width > maxW) cut--;
                    lines.push(line.slice(0, cut));
                    line = line.slice(cut);
                }
            });
            if (line.trim()) lines.push(line.replace(/\s+$/, ''));
        });
        return lines;
    }

    // 先排出所有要畫的「列」，再分頁
    function layout() {
        const measure = document.createElement('canvas').getContext('2d');
        const maxW = PAGE_W - MARGIN * 2;
        const rows = [];
        const add = (text, o) => rows.push(Object.assign({ text, size: 24, lh: 40, color: '#222', weight: 'normal', indent: 0 }, o));
        const addWrapped = (text, o) => {
            measure.font = `${o.style || ''} ${o.weight || 'normal'} ${o.size || 24}px ${FONT}`;
            wrap(measure, text, maxW - (o.indent || 0) * 2).forEach(l => add(l, o));
        };

        const now = new Date();
        const date = `${now.getFullYear()}/${String(now.getMonth() + 1).padStart(2, '0')}/${String(now.getDate()).padStart(2, '0')}`;
        add(info.title + '｜Writing', { size: 34, lh: 54, weight: 'bold' });
        add(`學生：${info.student}　　輸出日期：${date}`, { size: 22, lh: 40, color: '#555' });
        add('', { lh: 10, rule: true });

        TASKS.forEach(({ n, min }) => {
            const essay = document.getElementById('task' + n).value;
            const promptEl = document.getElementById('prompt' + n);
            const prompt = promptEl ? promptEl.innerText.replace(/[ \t]+/g, ' ').replace(/\n\s*\n+/g, '\n').trim() : '';
            const words = countWords(essay);
            add('', { lh: 26 });
            add(`Writing Task ${n}`, { size: 30, lh: 50, weight: 'bold', color: '#5b48a2', keep: 4 });
            addWrapped(prompt, { size: 20, lh: 32, color: '#555', style: 'italic', indent: 18, bar: true });
            add('', { lh: 18 });
            add(`學生作答（${words} 字／至少 ${min} 字）`, { size: 21, lh: 38, weight: 'bold', color: words >= min ? '#1e8449' : '#ba4a00', keep: 2 });
            if (essay.trim()) addWrapped(essay, { size: 24, lh: 42 });
            else add('（尚未作答）', { color: '#999' });
        });
        return rows;
    }

    function newPage() {
        const c = document.createElement('canvas');
        c.width = PAGE_W; c.height = PAGE_H;
        const ctx = c.getContext('2d');
        ctx.fillStyle = '#fff'; ctx.fillRect(0, 0, PAGE_W, PAGE_H);
        ctx.textBaseline = 'middle';
        return { c, ctx, y: MARGIN };
    }

    function renderPages() {
        const rows = layout();
        const pages = [newPage()];
        const bottom = PAGE_H - MARGIN - 40;
        rows.forEach((r, i) => {
            let pg = pages[pages.length - 1];
            // 標題不要孤零零留在頁尾：後面至少要放得下 keep 列
            const need = r.lh + (r.keep ? rows.slice(i + 1, i + 1 + r.keep).reduce((s, x) => s + x.lh, 0) : 0);
            if (pg.y + need > bottom && pg.y > MARGIN) { pg = newPage(); pages.push(pg); }
            const { ctx } = pg;
            if (r.rule) { ctx.fillStyle = '#333'; ctx.fillRect(MARGIN, pg.y + 4, PAGE_W - MARGIN * 2, 2); }
            if (r.bar) { ctx.fillStyle = '#cfc8e8'; ctx.fillRect(MARGIN, pg.y, 5, r.lh); }
            if (r.text) {
                ctx.font = `${r.style || ''} ${r.weight} ${r.size}px ${FONT}`;
                ctx.fillStyle = r.color;
                ctx.fillText(r.text, MARGIN + r.indent, pg.y + r.lh / 2);
            }
            pg.y += r.lh;
        });
        pages.forEach((pg, i) => {
            pg.ctx.font = `normal 18px ${FONT}`; pg.ctx.fillStyle = '#999'; pg.ctx.textAlign = 'center';
            pg.ctx.fillText(`${info.student}｜${info.title}｜第 ${i + 1} / ${pages.length} 頁`, PAGE_W / 2, PAGE_H - MARGIN / 2);
            pg.ctx.textAlign = 'left';
        });
        return pages.map(p => p.c);
    }

    function download(blob, name) {
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = name;
        document.body.appendChild(a); a.click(); a.remove();
        setTimeout(() => URL.revokeObjectURL(a.href), 4000);
    }

    function baseName() {
        const d = new Date();
        const stamp = `${d.getFullYear()}${String(d.getMonth() + 1).padStart(2, '0')}${String(d.getDate()).padStart(2, '0')}`;
        return `${info.student}_${info.title.replace(/\s+/g, '')}_Writing_${stamp}`.replace(/[\\/:*?"<>|]/g, '_');
    }

    function dataUrlBytes(url) {
        const bin = atob(url.split(',')[1]);
        const out = new Uint8Array(bin.length);
        for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
        return out;
    }

    // 圖片：所有頁面直向接成一張 PNG
    function exportPng() {
        const pages = renderPages();
        const all = document.createElement('canvas');
        all.width = PAGE_W; all.height = PAGE_H * pages.length;
        const ctx = all.getContext('2d');
        pages.forEach((p, i) => {
            ctx.drawImage(p, 0, i * PAGE_H);
            if (i) { ctx.fillStyle = '#ddd'; ctx.fillRect(0, i * PAGE_H, PAGE_W, 2); }
        });
        download(new Blob([dataUrlBytes(all.toDataURL('image/png'))], { type: 'image/png' }), baseName() + '.png');
    }

    // PDF：每頁放一張 JPEG（自己組最精簡的 PDF 結構）
    function buildPdf(pages) {
        const enc = new TextEncoder();
        const chunks = [], offsets = [];
        let pos = 0;
        const push = (d) => { const b = typeof d === 'string' ? enc.encode(d) : d; chunks.push(b); pos += b.length; };
        const obj = (id, body, stream) => {
            offsets[id] = pos;
            push(`${id} 0 obj\n${body}\n`);
            if (stream) { push('stream\n'); push(stream); push('\nendstream\n'); }
            push('endobj\n');
        };
        const n = pages.length;
        push('%PDF-1.4\n%\xE2\xE3\xCF\xD3\n');
        const kids = pages.map((_, i) => `${3 + i * 3} 0 R`).join(' ');
        obj(1, '<< /Type /Catalog /Pages 2 0 R >>');
        obj(2, `<< /Type /Pages /Kids [${kids}] /Count ${n} >>`);
        pages.forEach((c, i) => {
            const pageId = 3 + i * 3, contId = pageId + 1, imgId = pageId + 2;
            const jpg = dataUrlBytes(c.toDataURL('image/jpeg', 0.92));
            const content = enc.encode('q 595 0 0 842 0 0 cm /Im0 Do Q');
            obj(pageId, `<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /XObject << /Im0 ${imgId} 0 R >> >> /Contents ${contId} 0 R >>`);
            obj(contId, `<< /Length ${content.length} >>`, content);
            obj(imgId, `<< /Type /XObject /Subtype /Image /Width ${c.width} /Height ${c.height} /ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /DCTDecode /Length ${jpg.length} >>`, jpg);
        });
        const total = 3 + n * 3, xref = pos;
        let table = `xref\n0 ${total}\n0000000000 65535 f \n`;
        for (let id = 1; id < total; id++) table += String(offsets[id]).padStart(10, '0') + ' 00000 n \n';
        push(table + `trailer\n<< /Size ${total} /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF\n`);
        return new Blob(chunks, { type: 'application/pdf' });
    }

    function exportPdf() { download(buildPdf(renderPages()), baseName() + '.pdf'); }

    function init(opts) {
        info = Object.assign(info, opts);
        const bind = (id, fn) => {
            const el = document.getElementById(id);
            if (el) el.addEventListener('click', () => { try { fn(); } catch (e) { alert('輸出失敗：' + e.message); } });
        };
        bind('exportPdf', exportPdf);
        bind('exportPng', exportPng);
    }

    return { init, renderPages, buildPdf, exportPdf, exportPng };
})();
