/* ===== Panes, drawers, modals, mobile helpers ===== */
function isMobile() { return window.matchMedia('(max-width: 700px)').matches; }          // phone: compact board etc.
function isDrawerMode() { return window.matchMedia('(max-width: 960px)').matches; }     // panes are drawers

function togglePane(side, force) {
    const pane = document.getElementById(side === 'left' ? 'pane-left' : 'pane-right');
    const shell = document.getElementById('app');
    const collapsed = force === undefined ? !pane.classList.contains('collapsed') : !!force;
    if (isDrawerMode() && !collapsed) {
        // only one drawer at a time on small screens
        const other = document.getElementById(side === 'left' ? 'pane-right' : 'pane-left');
        other.classList.add('collapsed');
        shell.classList.add((side === 'left' ? 'right' : 'left') + '-collapsed');
    }
    pane.classList.toggle('collapsed', collapsed);
    shell.classList.toggle(side + '-collapsed', collapsed);
    const anyOpen = isDrawerMode() && (!document.getElementById('pane-left').classList.contains('collapsed') || !document.getElementById('pane-right').classList.contains('collapsed'));
    shell.classList.toggle('drawer-open', anyOpen);
    if (!isDrawerMode()) { try { localStorage.setItem('pane-' + side, collapsed ? '1' : '0'); } catch (_) {} }
    if (side === 'right' && !collapsed) setTimeout(scrollToBottom, 50);
}

function closeDrawers() { togglePane('left', true); togglePane('right', true); }

function restorePanes() {
    const shell = document.getElementById('app');
    shell.classList.toggle('mobile', isMobile());
    if (isDrawerMode()) { if (document.getElementById('pane-right').classList.contains('floating')) applyChatFloat(false); closeDrawers(); return; }
    let l = '0', r = '0';
    try { l = localStorage.getItem('pane-left') || '0'; r = localStorage.getItem('pane-right') || '0'; } catch (_) {}
    togglePane('left', l === '1');
    togglePane('right', r === '1');
}

/* ---------- chat pane: drag-to-resize (docked) and floating window ---------- */
const _chatGeo = { w: 400, fx: null, fy: null, fw: 420, fh: 600, floating: false };
function _loadChatGeo() { try { Object.assign(_chatGeo, JSON.parse(localStorage.getItem('chat-geo') || '{}')); } catch (_) {} }
function _saveChatGeo() { try { localStorage.setItem('chat-geo', JSON.stringify(_chatGeo)); } catch (_) {} }

function initChatPane() {
    _loadChatGeo();
    const pane = document.getElementById('pane-right');
    if (!isDrawerMode() && _chatGeo.w) { pane.style.width = _chatGeo.w + 'px'; pane.style.minWidth = _chatGeo.w + 'px'; }
    // docked width resizer
    const rz = document.getElementById('pane-resizer');
    let startX = 0, startW = 0;
    const px = e => (e.touches ? e.touches[0].clientX : e.clientX);
    const py = e => (e.touches ? e.touches[0].clientY : e.clientY);
    const onMove = e => {
        const w = Math.max(320, Math.min(window.innerWidth * 0.7, startW + (startX - px(e))));
        pane.style.width = w + 'px'; pane.style.minWidth = w + 'px'; _chatGeo.w = w;
    };
    const onUp = () => {
        document.removeEventListener('mousemove', onMove); document.removeEventListener('mouseup', onUp);
        document.removeEventListener('touchmove', onMove); document.removeEventListener('touchend', onUp);
        document.body.classList.remove('resizing'); rz.classList.remove('active'); _saveChatGeo();
        if (typeof drawFeixing === 'function') setTimeout(drawFeixing, 50);
    };
    const onDown = e => {
        if (pane.classList.contains('floating')) return;
        startX = px(e); startW = pane.getBoundingClientRect().width;
        document.body.classList.add('resizing'); rz.classList.add('active');
        document.addEventListener('mousemove', onMove); document.addEventListener('mouseup', onUp);
        document.addEventListener('touchmove', onMove, { passive: true }); document.addEventListener('touchend', onUp);
        e.preventDefault();
    };
    rz.addEventListener('mousedown', onDown); rz.addEventListener('touchstart', onDown, { passive: false });
    // floating window: drag by the header
    const head = document.getElementById('chat-header');
    let dx = 0, dy = 0;
    const dragMove = e => {
        const r = pane.getBoundingClientRect();
        const cx = Math.max(0, Math.min(window.innerWidth - r.width, px(e) - dx));
        const cy = Math.max(0, Math.min(window.innerHeight - 40, py(e) - dy));
        pane.style.left = cx + 'px'; pane.style.top = cy + 'px'; _chatGeo.fx = cx; _chatGeo.fy = cy;
    };
    const dragUp = () => {
        document.removeEventListener('mousemove', dragMove); document.removeEventListener('mouseup', dragUp);
        document.removeEventListener('touchmove', dragMove); document.removeEventListener('touchend', dragUp);
        document.body.classList.remove('dragging'); _saveChatGeo();
    };
    const dragDown = e => {
        if (!pane.classList.contains('floating') || e.target.closest('button')) return;
        const r = pane.getBoundingClientRect(); dx = px(e) - r.left; dy = py(e) - r.top;
        document.body.classList.add('dragging');
        document.addEventListener('mousemove', dragMove); document.addEventListener('mouseup', dragUp);
        document.addEventListener('touchmove', dragMove, { passive: true }); document.addEventListener('touchend', dragUp);
        if (e.cancelable) e.preventDefault();
    };
    head.addEventListener('mousedown', dragDown); head.addEventListener('touchstart', dragDown, { passive: false });
    // remember the size chosen with the CSS resize grip
    if (window.ResizeObserver) new ResizeObserver(() => {
        if (!pane.classList.contains('floating')) return;
        const r = pane.getBoundingClientRect();
        if (r.width > 0) { _chatGeo.fw = r.width; _chatGeo.fh = r.height; _saveChatGeo(); }
    }).observe(pane);
    if (_chatGeo.floating && !isDrawerMode()) applyChatFloat(true);
}

function applyChatFloat(on) {
    const pane = document.getElementById('pane-right'), shell = document.getElementById('app'), btn = document.getElementById('btn-float');
    _chatGeo.floating = !!on;
    pane.classList.toggle('floating', !!on);
    shell.classList.toggle('chat-floating', !!on);
    if (on) {
        pane.classList.remove('collapsed'); shell.classList.remove('right-collapsed');
        const w = Math.min(_chatGeo.fw || 420, window.innerWidth - 20), h = Math.min(_chatGeo.fh || 600, window.innerHeight - 20);
        const x = _chatGeo.fx == null ? window.innerWidth - w - 16 : Math.max(0, Math.min(window.innerWidth - w, _chatGeo.fx));
        const y = _chatGeo.fy == null ? Math.max(8, window.innerHeight - h - 16) : Math.max(0, Math.min(window.innerHeight - 40, _chatGeo.fy));
        Object.assign(pane.style, { left: x + 'px', top: y + 'px', width: w + 'px', height: h + 'px', minWidth: '' });
        if (btn) btn.textContent = '⧈ 停靠';
    } else {
        Object.assign(pane.style, { left: '', top: '', height: '', width: _chatGeo.w ? _chatGeo.w + 'px' : '', minWidth: _chatGeo.w ? _chatGeo.w + 'px' : '' });
        if (btn) btn.textContent = '⧉ 弹出';
    }
    _saveChatGeo();
    if (typeof drawFeixing === 'function') setTimeout(drawFeixing, 60);
}
function toggleChatFloat() {
    applyChatFloat(!document.getElementById('pane-right').classList.contains('floating'));
    setTimeout(scrollToBottom, 50);
}

/* compact / zoomed board on phones */
function applyZoom() {
    let z = '0';
    try { z = localStorage.getItem('zw-zoom') || '0'; } catch (_) {}
    document.getElementById('app').classList.toggle('zoomed', z === '1');
    const b = document.getElementById('btn-zoom');
    if (b) b.textContent = z === '1' ? '▣ 紧凑' : '🔍 放大';
}
function toggleZoom() {
    let z = '0';
    try { z = localStorage.getItem('zw-zoom') || '0'; localStorage.setItem('zw-zoom', z === '1' ? '0' : '1'); } catch (_) {}
    applyZoom();
    if (typeof drawFeixing === 'function') setTimeout(drawFeixing, 60);
}

/* collapsible strips on phones */
function toggleStrips() {
    AppState.stripsOpen = !AppState.stripsOpen;
    const w = document.querySelector('.strip-wrap');
    if (w) w.classList.toggle('collapsed', !AppState.stripsOpen);
    if (AppState.stripsOpen) scrollActiveChips();
}
function scrollActiveChips() {
    document.querySelectorAll('.strip .chip.active').forEach(c => { try { c.scrollIntoView({ block: 'nearest', inline: 'center' }); } catch (_) {} });
}
function wrapStrips(html, summary) {
    if (!isMobile()) return html;
    return `<div class="strip-wrap ${AppState.stripsOpen ? '' : 'collapsed'}">
        <div class="strip-handle" onclick="toggleStrips()"><b>运限</b><span class="sum">${summary}</span><span>${AppState.stripsOpen ? '▴' : '▾'}</span></div>
        <div class="strip-rows">${html}</div></div>`;
}

function openModal(id) {
    document.getElementById('modal-overlay').classList.remove('hidden');
    document.querySelectorAll('.modal').forEach(m => m.classList.add('hidden'));
    document.getElementById(id).classList.remove('hidden');
}
function closeModal(id) {
    const m = document.getElementById(id);
    if (m) m.classList.add('hidden');
    const anyOpen = [...document.querySelectorAll('.modal')].some(x => !x.classList.contains('hidden'));
    if (!anyOpen) document.getElementById('modal-overlay').classList.add('hidden');
}
function closeAllModals() {
    document.querySelectorAll('.modal').forEach(m => m.classList.add('hidden'));
    document.getElementById('modal-overlay').classList.add('hidden');
}
function showInfoSheet(title, html) {
    document.getElementById('modal-info-title').textContent = title;
    document.getElementById('modal-info-body').innerHTML = html;
    openModal('modal-info');
}
document.addEventListener('keydown', e => { if (e.key === 'Escape') closeAllModals(); });

function openConfig() { openModal('modal-config'); loadConfigPage(); }
function openCompare() { openModal('modal-compare'); document.getElementById('compare-result').innerHTML = ''; }

async function runCompare() {
    const text = document.getElementById('compare-text').value.trim();
    const out = document.getElementById('compare-result');
    if (!AppState.personId) { out.textContent = '请先选择人物'; return; }
    if (!text) { out.textContent = '请粘贴导出文本'; return; }
    out.textContent = '比对中…';
    try {
        const r = await API.post(`/api/people/${AppState.personId}/wenmo-compare`, { text });
        let html = `<div class="${r.diff_count ? 'text-red' : 'text-green'}" style="margin-bottom:.4rem;">${esc(r.message)}</div>`;
        if (r.parsed_basic && r.parsed_basic.clock_time) html += `<div class="text-muted">导出：${esc(r.parsed_basic.gender || '')} ${esc(r.parsed_basic.clock_time)} 经度 ${esc(r.parsed_basic.longitude)}</div>`;
        if (r.diffs.length) {
            html += '<table><tr><th>位置</th><th>字段</th><th>引擎</th><th>文墨</th></tr>' +
                r.diffs.map(d => `<tr><td>${esc(d.where)}</td><td>${esc(d.field)}</td><td>${esc(d.engine)}</td><td>${esc(d.wenmo)}</td></tr>`).join('') + '</table>';
        }
        out.innerHTML = html;
    } catch (e) { out.innerHTML = `<span class="text-red">${esc(e.message)}</span>`; }
}
