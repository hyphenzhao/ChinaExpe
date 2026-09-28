/* ===== Sessions (grouped by person) ===== */
async function loadSessions() {
    try { AppState.sessions = await API.get('/api/chats'); } catch (_) { AppState.sessions = []; }
    renderSessions();
}

function personName(pid) {
    const p = AppState.people.find(x => x.id === pid);
    return p ? p.display_name : (pid || '');
}

function renderSessions() {
    const el = document.getElementById('session-list');
    if (!AppState.sessions.length) { el.innerHTML = '<div class="text-muted" style="font-size:.75rem;padding:.4rem;">暂无对话</div>'; return; }
    const groups = {};
    for (const s of AppState.sessions) {
        const k = s.person || '__theory__';
        (groups[k] = groups[k] || []).push(s);
    }
    const order = Object.keys(groups).sort((a, b) => {
        if (a === AppState.personId) return -1; if (b === AppState.personId) return 1;
        if (a === '__theory__') return 1; if (b === '__theory__') return -1;
        return personName(a).localeCompare(personName(b));
    });
    el.innerHTML = order.map(k => `
        <div class="session-group">${k === '__theory__' ? '【理论讨论】' : '【' + esc(personName(k)) + '】'}</div>
        ${groups[k].map(s => `
            <div class="session-item ${s.id === AppState.sessionId ? 'active' : ''}" onclick="openSession('${s.id}')" title="${esc(s.title)}">
                <span class="session-item-title">${esc(stripPersonPrefix(s.title))}</span>
                <span class="text-muted" style="font-size:.6rem;">${s.message_count}</span>
                <button class="session-item-del" onclick="event.stopPropagation(); deleteSession('${s.id}')" title="删除">✕</button>
            </div>`).join('')}`).join('');
}

function stripPersonPrefix(t) { return (t || '').replace(/^【[^】]*】/, ''); }

async function openSession(sid, opts = {}) {
    try { AppState.session = await API.get(`/api/chats/${sid}`); } catch (e) { toast(e.message, true); return; }
    AppState.sessionId = sid;
    AppState.pendingPick = null;          // 会话自己的模型选择接管
    renderMessages(AppState.session.messages || []);
    document.getElementById('session-title').textContent = stripPersonPrefix(AppState.session.title) || '对话';
    renderModelBar(); updateModelInfo();
    renderSessions();
    if (!opts.silent && AppState.session.person && AppState.session.person !== AppState.personId) {
        await selectPerson(AppState.session.person, { keepSession: true });
    }
    if (!opts.silent && isMobile()) togglePane('right', false);
    setHash();
}

function clearSession() {
    AppState.sessionId = null; AppState.session = null; AppState.pendingPick = null;
    renderMessages([]);
    renderModelBar(); updateModelInfo();
    document.getElementById('session-title').textContent = AppState.personId ? `与 AI 讨论 ${personName(AppState.personId)} 的命盘` : 'AI 解盘';
    renderSessions();
    setHash();
}

function newSession() {
    clearSession();
    if (isMobile()) togglePane('right', false);
    document.getElementById('message-input').focus();
}

async function deleteSession(sid) {
    if (!confirm('删除这个对话？')) return;
    try { await API.del(`/api/chats/${sid}`); } catch (e) { toast(e.message, true); return; }
    if (AppState.sessionId === sid) clearSession();
    await loadSessions();
}
