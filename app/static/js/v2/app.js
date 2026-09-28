/* ===== Boot + hash router ===== */
// #/p/<pid>/<ziwei|bazi>[/s/<sid>]

function setHash() {
    const parts = [];
    if (AppState.personId) parts.push('p', AppState.personId, AppState.chart);
    if (AppState.sessionId) parts.push('s', AppState.sessionId);
    const h = '#/' + parts.join('/');
    if (window.location.hash !== h) history.replaceState(null, '', h);
}

function parseHash() {
    const parts = (window.location.hash || '').replace(/^#\/?/, '').split('/').filter(Boolean);
    const out = {};
    for (let i = 0; i < parts.length; i++) {
        if (parts[i] === 'p') { out.pid = parts[i + 1]; out.chart = parts[i + 2] === 'bazi' ? 'bazi' : 'ziwei'; i += 2; }
        else if (parts[i] === 's') { out.sid = parts[i + 1]; i += 1; }
    }
    return out;
}

async function boot() {
    AppState.stripsOpen = false;
    restorePanes();
    await loadConfig();
    await loadCatalog();
    updateModelInfo();
    await loadPeople();
    await loadSessions();
    const h = parseHash();
    if (h.sid) {
        await openSession(h.sid, { silent: true });
    }
    if (h.pid && AppState.people.some(p => p.id === h.pid)) {
        AppState.chart = h.chart || 'ziwei';
        await selectPerson(h.pid, { keepSession: true });
    } else if (!AppState.personId && AppState.people.length) {
        await selectPerson(AppState.people[0].id, { keepSession: true });
    }
    switchChart(AppState.chart, true);
    applyZoom();
    initChatPane();
    let wasDrawer = isDrawerMode(), wasMobile = isMobile();
    window.addEventListener('resize', () => {
        const d = isDrawerMode(), m = isMobile();
        if (d !== wasDrawer) { wasDrawer = d; restorePanes(); }
        if (m !== wasMobile) {
            wasMobile = m;
            document.getElementById('app').classList.toggle('mobile', m);
            if (AppState.chart === 'ziwei' && AppState.ziwei) { renderStrips(); }
            if (AppState.chart === 'bazi' && AppState.baziTimeline) { renderBaziStrips(); }
        }
        if (AppState.chart === 'ziwei' && AppState.ziwei) drawFeixing();
    });
}

function updateModelInfo() {
    const el = document.getElementById('model-info');
    const pick = typeof currentPick === 'function' ? currentPick() : {};
    if (pick && pick.model) {
        const entry = typeof catalogEntry === 'function' ? catalogEntry(pick.provider, pick.model) : null;
        const label = entry ? (entry.label || entry.model) : pick.model;
        const scope = AppState.sessionId ? '本对话' : '默认';
        el.textContent = `${scope}：${pick.provider} · ${label}`;
        return;
    }
    el.textContent = '未配置模型（点 ⚙️ 设置）';
}

window.addEventListener('DOMContentLoaded', boot);
