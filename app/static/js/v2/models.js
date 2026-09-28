/* ===== 聊天页的模型 / 思考档位选择器 =====
   数据来自 GET /api/config/catalog：模型库、各自能力、跳板状态。
   选择按会话记忆：已有会话走 PUT /api/chats/{id}，新会话先存在 AppState，首次发送时带上。 */

async function loadCatalog() {
    try { AppState.catalog = await API.get('/api/config/catalog'); }
    catch (_) { AppState.catalog = { models: [], default: {}, proxy: {}, thinking_levels: [] }; }
    renderModelBar();
    return AppState.catalog;
}

function catalogEntry(provider, model) {
    const c = AppState.catalog || { models: [] };
    return (c.models || []).find(m => m.provider === provider && m.model === model) || null;
}

/* 当前会话该用哪个模型：会话里存的 → 模型库默认 */
function currentPick() {
    const c = AppState.catalog || { models: [], default: {} };
    const s = AppState.session || {};
    const pending = AppState.pendingPick || {};
    const provider = pending.provider || s.provider || (c.default || {}).provider || '';
    const model = pending.model || s.model || (c.default || {}).model || '';
    const thinking = pending.thinking != null ? pending.thinking : (s.thinking || '');
    return { provider, model, thinking };
}

function renderModelBar() {
    const bar = document.getElementById('chat-model-bar');
    const sel = document.getElementById('chat-model');
    const think = document.getElementById('chat-thinking');
    const warn = document.getElementById('chat-proxy-warn');
    if (!bar || !sel) return;
    const c = AppState.catalog || { models: [], thinking_levels: [] };
    const pick = currentPick();

    if (!c.models || !c.models.length) {
        sel.innerHTML = '<option value="">未配置模型</option>';
        think.classList.add('hidden');
        warn.textContent = '去设置里勾选模型';
        warn.classList.remove('hidden');
        return;
    }

    const key = `${pick.provider}:${pick.model}`;
    let opts = c.models.map(m => `<option value="${esc(m.provider + ':' + m.model)}">${esc(m.label || m.model)}</option>`).join('');
    if (pick.model && !c.models.some(m => `${m.provider}:${m.model}` === key)) {
        // 会话固定的模型已被移出模型库：保留显示，标注出来
        opts = `<option value="${esc(key)}">${esc(pick.model)}（已移出模型库）</option>` + opts;
    }
    sel.innerHTML = opts;
    sel.value = key;

    const entry = catalogEntry(pick.provider, pick.model);
    const levels = (entry && entry.thinking === 'optional') ? (entry.thinking_levels || []) : [];
    if (levels.length) {
        const cur = pick.thinking || (entry.default_thinking || 'off');
        const labels = {};
        (c.thinking_levels || []).forEach(l => labels[l.value] = l.label);
        think.innerHTML = levels.map(l => `<option value="${esc(l)}">${esc(labels[l] || l)}</option>`).join('');
        think.value = levels.includes(cur) ? cur : levels[0];
        think.classList.remove('hidden');
    } else {
        think.classList.add('hidden');
        think.innerHTML = '';
    }

    const msg = entry ? (entry.warning || '') : '';
    warn.textContent = msg ? '⚠ ' + msg.split('（')[0] : '';
    warn.title = msg;
    warn.classList.toggle('hidden', !msg);
}

async function persistPick(patch) {
    if (AppState.sessionId) {
        try {
            AppState.session = await API.put(`/api/chats/${AppState.sessionId}`, patch);
        } catch (e) { toast('保存模型选择失败: ' + e.message, true); }
    } else {
        AppState.pendingPick = { ...(AppState.pendingPick || {}), ...patch };
    }
    updateModelInfo();
}

async function onChatModelChange() {
    const v = document.getElementById('chat-model').value || '';
    const provider = v.split(':')[0];
    const model = v.slice(v.indexOf(':') + 1);
    const entry = catalogEntry(provider, model);
    const thinking = entry && entry.thinking === 'optional' ? (entry.default_thinking || 'off') : '';
    await persistPick({ provider, model, thinking });
    if (AppState.session) { AppState.session.provider = provider; AppState.session.model = model; AppState.session.thinking = thinking; }
    renderModelBar();
}

async function onChatThinkingChange() {
    const thinking = document.getElementById('chat-thinking').value || '';
    await persistPick({ thinking });
    if (AppState.session) AppState.session.thinking = thinking;
}
