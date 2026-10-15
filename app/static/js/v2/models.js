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
    const raw = pending.thinking != null ? pending.thinking : (s.thinking || '');
    const thinking = validThinking(catalogEntry(provider, model), raw);
    return { provider, model, thinking };
}

function validThinking(entry, value) {
    const levels = entry && entry.thinking === 'optional' ? (entry.thinking_levels || []) : [];
    if (!levels.length) return '';
    if (value === 'off' && levels.includes('none')) value = 'none';
    return levels.includes(value) ? value : levels.includes(entry.default_thinking) ? entry.default_thinking : levels[0];
}

function thinkingLabel(value) {
    const match = ((AppState.catalog || {}).thinking_levels || []).find(l => l.value === value);
    return `${match ? match.label : value} · ${value}`;
}

function previewThinking() {
    const input = document.getElementById('chat-thinking');
    const levels = JSON.parse(input.dataset.levels || '[]');
    const level = levels[Number(input.value)];
    if (!level) return;
    document.getElementById('chat-thinking-value').textContent = thinkingLabel(level);
    input.setAttribute('aria-valuetext', thinkingLabel(level));
    input.style.setProperty('--thinking-progress', `${levels.length > 1 ? Number(input.value) / (levels.length - 1) * 100 : 0}%`);
    document.querySelectorAll('#chat-thinking-ticks span').forEach((tick, i) => tick.classList.toggle('active', i === Number(input.value)));
}

function renderThinking(entry, value) {
    const wrap = document.getElementById('chat-thinking-wrap');
    const input = document.getElementById('chat-thinking');
    const levels = entry && entry.thinking === 'optional' ? (entry.thinking_levels || []) : [];
    wrap.classList.toggle('hidden', !levels.length);
    input.dataset.levels = JSON.stringify(levels);
    if (!levels.length) { input.value = 0; return; }
    input.max = levels.length - 1;
    input.value = levels.indexOf(validThinking(entry, value));
    input.disabled = levels.length < 2;
    document.getElementById('chat-thinking-ticks').innerHTML = levels.map(l => `<span>${esc(l)}</span>`).join('');
    const names = { remote: '来源：远程模型接口', docs: '来源：官方文档规则', manual: '来源：自定义能力', unknown: '能力待确认' };
    const source = document.getElementById('chat-thinking-source');
    source.textContent = names[entry.thinking_source] || names.unknown;
    source.title = (entry.thinking_checked_at ? `上次读取：${new Date(entry.thinking_checked_at).toLocaleString()}。` : '')
        + (entry.thinking_protocol === 'anthropic_budget' ? '该模型提供思考开关，没有原生深度档位。' : '刻度是模型支持的离散档位，不代表等比例算力。')
        + (entry.thinking_source === 'docs' ? '远程接口未提供档位，使用已核对的文档配置。' : '');
    previewThinking();
}

function renderModelBar() {
    const bar = document.getElementById('chat-model-bar');
    const sel = document.getElementById('chat-model');
    const warn = document.getElementById('chat-proxy-warn');
    if (!bar || !sel) return;
    const c = AppState.catalog || { models: [], thinking_levels: [] };
    const pick = currentPick();

    if (!c.models || !c.models.length) {
        sel.innerHTML = '<option value="">未配置模型</option>';
        renderThinking(null, '');
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
    renderThinking(entry, pick.thinking);

    const msg = entry ? (entry.warning || '') : '';
    warn.textContent = msg ? '⚠ ' + msg.split('（')[0] : '';
    warn.title = msg;
    warn.classList.toggle('hidden', !msg);
}

async function persistPick(patch) {
    const sid = AppState.sessionId;
    const modelSelect = document.getElementById('chat-model');
    const slider = document.getElementById('chat-thinking');
    modelSelect.disabled = slider.disabled = true;
    let saved = true;
    try {
    if (AppState.sessionId) {
        try {
            const session = await API.put(`/api/chats/${sid}`, patch);
            if (AppState.sessionId === sid) AppState.session = session;
        } catch (e) { toast('保存模型选择失败: ' + e.message, true); saved = false; }
    } else {
        AppState.pendingPick = { ...(AppState.pendingPick || {}), ...patch };
    }
    updateModelInfo();
    return saved;
    } finally {
        modelSelect.disabled = false;
        renderModelBar();
    }
}

async function onChatModelChange() {
    const v = document.getElementById('chat-model').value || '';
    const provider = v.split(':')[0];
    const model = v.slice(v.indexOf(':') + 1);
    const entry = catalogEntry(provider, model);
    const thinking = entry && entry.thinking === 'optional' ? (entry.default_thinking || 'off') : '';
    await persistPick({ provider, model, thinking });
}

async function onChatThinkingChange() {
    const input = document.getElementById('chat-thinking');
    const levels = JSON.parse(input.dataset.levels || '[]');
    const thinking = levels[Number(input.value)];
    if (!thinking) return;
    await persistPick({ thinking });
}
