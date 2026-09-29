/* ===== Chat pane: SSE streaming, tool events, pending updates ===== */

function renderMarkdown(text) {
    if (!text) return '';
    let html = esc(text);
    html = html.replace(/```(\w*)\n([\s\S]*?)```/g, '<pre><code>$2</code></pre>');
    html = html.replace(/`([^`]+)`/g, '<code>$1</code>');
    html = html.replace(/^#### (.+)$/gm, '<h4>$1</h4>').replace(/^### (.+)$/gm, '<h3>$1</h3>').replace(/^## (.+)$/gm, '<h2>$1</h2>').replace(/^# (.+)$/gm, '<h1>$1</h1>');
    html = html.replace(/\*\*\*(.+?)\*\*\*/g, '<strong><em>$1</em></strong>').replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>').replace(/(^|[^*])\*([^*\n]+)\*/g, '$1<em>$2</em>');
    html = html.replace(/^&gt; (.+)$/gm, '<blockquote>$1</blockquote>').replace(/<\/blockquote>\n<blockquote>/g, '<br>');
    html = html.replace(/^---$/gm, '<hr>');
    html = html.replace(/^[\-\*] (.+)$/gm, '<li>$1</li>').replace(/^\d+\. (.+)$/gm, '<li>$1</li>');
    html = html.replace(/(<li>.*<\/li>\n?)+/g, '<ul>$&</ul>');
    html = html.replace(/^\|(.+)\|$/gm, line => {
        const cells = line.split('|').filter(c => c.trim()).map(c => `<td>${c.trim()}</td>`).join('');
        return /^\|\s*:?-+/.test(line) ? '' : `<tr>${cells}</tr>`;
    });
    html = html.replace(/(<tr>.*<\/tr>\n?)+/g, '<table>$&</table>');
    return html.split(/\n\n+/).map(b => {
        b = b.trim(); if (!b) return '';
        if (/^<(h\d|ul|ol|table|pre|blockquote|hr)/.test(b)) return b;
        return '<p>' + b.replace(/\n/g, '<br>') + '</p>';
    }).join('\n');
}

function renderMessages(messages) {
    const c = document.getElementById('messages-container');
    c.innerHTML = '';
    if (!messages.length) {
        c.innerHTML = `<div class="welcome-message" id="welcome-message"><div class="welcome-icon">🔮</div><p>${AppState.personId ? '点选命盘中的宫位/星曜/柱后提问，AI 会自动读取命盘与运限，并检索典籍。' : '先在左侧选择人物。'}</p><div id="welcome-extra"></div></div>`;
        if (AppState.personId) renderWelcomeExtra();
        return;
    }
    for (const m of messages) {
        if (m.role === 'tool') { appendToolEvent({ tool: m.name, summary: m.content }, true); continue; }
        if (m.role === 'assistant' && !m.content) continue;
        appendMessage(m.role, m.content, m.context);
    }
    scrollToBottom();
}

function appendMessage(role, content, context) {
    const c = document.getElementById('messages-container');
    const w = document.getElementById('welcome-message'); if (w) w.remove();
    const div = document.createElement('div');
    div.className = `message ${role}`;
    div.innerHTML = `<div class="message-avatar">${role === 'user' ? '👤' : '🌙'}</div>
        <div style="min-width:0;"><div class="message-bubble">${role === 'assistant' ? renderMarkdown(content) : esc(content)}</div>
        ${context && Object.keys(context).length ? `<div class="message-context">${esc(formatContext(context))}</div>` : ''}</div>`;
    c.appendChild(div);
    return div;
}

function appendToolEvent(data, done) {
    const c = document.getElementById('messages-container');
    const w = document.getElementById('welcome-message'); if (w) w.remove();
    const names = { get_ziwei_patterns: '🏯 紫微格局', get_bazi_analysis: '⚖ 子平分析', get_life_events: '🎉 人生喜事', get_chart_variant: '🕰 候选时辰盘', get_rectify_candidates: '🧭 时辰评分', save_life_facts: '📝 记录经历', search_knowledge: '🔍 检索知识库', get_chart: '📊 读取命盘', get_horoscope: '🕰 读取运限', get_fly: '✈ 宫干飞化', get_bazi: '🀄 读取八字', get_bazi_timeline: '📅 八字运限', propose_person_update: '✎ 修改建议', add_note: '📝 添加备注', list_classics: '📚 典籍清单', search_classics: '📖 检索典籍原文', read_classic: '📄 读典籍原文' };
    const div = document.createElement('div');
    div.className = 'tool-event' + (done ? ' done' : '');
    const q = data.query || (data.args && (data.args.date || data.args.palace || data.args.text)) || '';
    div.innerHTML = `<details><summary>${names[data.tool] || esc(data.tool)}${q ? ' · ' + esc(String(q)).slice(0, 60) : ''}${done ? '' : ' …'}</summary><div style="white-space:pre-wrap;margin-top:.25rem;">${esc(data.summary || '')}</div></details>`;
    c.appendChild(div);
    return div;
}

/* 思考过程：折叠显示，正文照旧单独渲染 */
function appendThinking() {
    const div = document.createElement('div');
    div.className = 'tool-event thinking-event';
    div.innerHTML = '<details><summary>💭 思考中…</summary><div class="think-body" style="white-space:pre-wrap;margin-top:.25rem;"></div></details>';
    return div;
}

function showPendingUpdate(pu) {
    AppState.pendingUpdate = pu;
    const c = document.getElementById('messages-container');
    const div = document.createElement('div');
    div.className = 'pending-card';
    div.innerHTML = `<strong>AI 建议修改 ${esc(personName(pu.person))}（${esc(pu.person)}）</strong>${pu.reason ? '：' + esc(pu.reason) : ''}
        <pre>${esc(JSON.stringify(pu.patch, null, 1))}</pre>
        <div style="display:flex;gap:.5rem;"><button class="btn btn-primary btn-sm" onclick="applyPendingUpdate(this)">确认修改并重新排盘</button><button class="btn btn-ghost btn-sm" onclick="this.closest('.pending-card').remove()">忽略</button></div>`;
    c.appendChild(div);
    scrollToBottom();
}

async function applyPendingUpdate(btn) {
    const pu = AppState.pendingUpdate; if (!pu) return;
    btn.disabled = true;
    try {
        const body = {};
        if (pu.patch.birth) body.birth = { ...(AppState.person && AppState.person.id === pu.person ? AppState.person.birth : {}), ...pu.patch.birth };
        if (pu.patch.settings) body.settings = pu.patch.settings;
        for (const k of ['display_name', 'gender', 'tags']) if (pu.patch[k] !== undefined) body[k] = pu.patch[k];
        await API.put(`/api/people/${pu.person}`, body);
        btn.closest('.pending-card').innerHTML = '<span class="text-green">✅ 已修改并重新排盘</span>';
        await loadPeople();
        AppState.ziwei = null; AppState.bazi = null; AppState.baziTimeline = null;
        await selectPerson(pu.person, { keepSession: true });
    } catch (e) { btn.disabled = false; toast(e.message, true); }
    AppState.pendingUpdate = null;
}

function scrollToBottom() { const c = document.getElementById('messages-container'); c.scrollTop = c.scrollHeight; }
function autoGrow(ta) { ta.style.height = 'auto'; ta.style.height = Math.min(ta.scrollHeight, 5 * 24 + 16) + 'px'; }
if (window.visualViewport) {
    window.visualViewport.addEventListener('resize', () => {
        // keyboard opened/closed on phones: keep the input visible and the thread scrolled
        if (isDrawerMode() && !document.getElementById('pane-right').classList.contains('collapsed')) {
            document.getElementById('pane-right').style.height = window.visualViewport.height + 'px';
            setTimeout(scrollToBottom, 50);
        } else {
            document.getElementById('pane-right').style.height = '';
        }
    });
}

/* ---------- context tags / reference bubbles ---------- */
function addContextTag(ctx, opts = {}) {
    AppState.selectedContext = { ...AppState.selectedContext, ...ctx };
    updateContextTags();
    if (opts.open) {
        if (isDrawerMode()) togglePane('right', false);
        document.getElementById('message-input').focus();
    } else {
        toast('已加入对话引用');
    }
}
/* replace the palace reference set (本宫 / 对宫 / 三合 ×2) built from a palace click */
function setPalaceRefs(refs) {
    AppState.selectedContext = { ...AppState.selectedContext, refs: refs.slice() };
    delete AppState.selectedContext.palace; delete AppState.selectedContext.stem_branch;
    delete AppState.selectedContext.star; delete AppState.selectedContext.brightness;
    updateContextTags();
    if (refs.length) toast(`已引用 ${refs[0].palace} 及其三方四正（${refs.length} 宫）`);
}
function clearContext() { AppState.selectedContext = {}; updateContextTags(); }
function roleCls(r) { return r === '本宫' ? 'ref-self' : r === '对宫' ? 'ref-opp' : 'ref-tri'; }
function updateContextTags() {
    const el = document.getElementById('context-tags');
    const ctx = AppState.selectedContext;
    const tags = [];
    (ctx.refs || []).forEach((r, i) => {
        const stars = [...r.major, ...r.minor].join(' ') || '空宫';
        tags.push(`<span class="context-tag ${roleCls(r.role)}" title="${esc(stars)}${r.adjective && r.adjective.length ? ' / ' + esc(r.adjective.join(' ')) : ''}"><b>${esc(r.palace)}</b>·${esc(r.ganzhi)}（${esc(r.role)}）<span class="ref-stars">${esc(stars)}</span><span class="remove-tag" onclick="removeRef(${i})">✕</span></span>`);
    });
    if (ctx.palace) tags.push(`<span class="context-tag">宫位 ${esc(ctx.palace)}${ctx.stem_branch ? '·' + esc(ctx.stem_branch) : ''}<span class="remove-tag" onclick="removeContext('palace')">✕</span></span>`);
    if (ctx.star) tags.push(`<span class="context-tag">星曜 ${esc(ctx.star)}${ctx.brightness ? '(' + esc(ctx.brightness) + ')' : ''}<span class="remove-tag" onclick="removeContext('star')">✕</span></span>`);
    if (ctx.pillar) tags.push(`<span class="context-tag">柱 ${esc(ctx.pillar)}<span class="remove-tag" onclick="removeContext('pillar')">✕</span></span>`);
    if (ctx.stem) tags.push(`<span class="context-tag">天干 ${esc(ctx.stem)}${ctx.shishen ? '(' + esc(ctx.shishen) + ')' : ''}<span class="remove-tag" onclick="removeContext('stem')">✕</span></span>`);
    if (ctx.level) tags.push(`<span class="context-tag">运限 ${esc(ctx.level)}<span class="remove-tag" onclick="removeContext('level')">✕</span></span>`);
    el.innerHTML = tags.join('');
    const badge = document.getElementById('ctx-badge');
    if (badge) { badge.textContent = tags.length || ''; badge.classList.toggle('hidden', !tags.length); }
}
function removeRef(i) {
    const refs = (AppState.selectedContext.refs || []).slice();
    const removed = refs.splice(i, 1)[0];
    AppState.selectedContext.refs = refs;
    if (removed && removed.role === '本宫' && AppState.selectedPalace === removed.index) { AppState.selectedPalace = null; if (typeof applyLayers === 'function') { applyLayers(); renderCenter(); } }
    if (!refs.length) delete AppState.selectedContext.refs;
    updateContextTags();
}
function removeContext(k) {
    const ctx = AppState.selectedContext;
    if (k === 'palace') { delete ctx.palace; delete ctx.stem_branch; }
    else if (k === 'star') { delete ctx.star; delete ctx.brightness; }
    else if (k === 'stem') { delete ctx.stem; delete ctx.shishen; }
    else delete ctx[k];
    updateContextTags();
}
function formatContext(ctx) {
    const p = [];
    (ctx.refs || []).forEach(r => p.push(`${r.palace}·${r.ganzhi}(${r.role})`));
    if (ctx.palace) p.push(`宫位:${ctx.palace}`);
    if (ctx.star) p.push(`星曜:${ctx.star}`);
    if (ctx.pillar) p.push(`柱:${ctx.pillar}`);
    if (ctx.stem) p.push(`天干:${ctx.stem}`);
    if (ctx.level) p.push(`运限:${ctx.level}`);
    if (ctx.action) p.push(`附代码分析:${{ ziwei_geju: '紫微格局', bazi_geju: '子平格局', life_event: '人生喜事', life_events: '人生喜事', rectify: '反推时辰' }[ctx.action.type] || ctx.action.type}`);
    return p.join(' · ');
}

/* ---------- send ---------- */
function onInputKeydown(e) { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); } }

/* opts.content：预置问题（不读输入框）；opts.action：让服务端附上代码分析结果 */
async function sendMessage(opts = {}) {
    const input = document.getElementById('message-input');
    const preset = typeof opts.content === 'string';
    const content = preset ? opts.content : input.value.trim();
    const action = opts.action || null;
    if (!content || AppState.isStreaming) return;
    const pick = currentPick();
    if (!pick.model) { toast('请先在设置 → 模型库里勾选模型', true); openConfig(); return; }
    const savedCtx = { ...AppState.selectedContext };
    const mode = AppState.personId ? 'chart' : 'theory';
    AppState.isStreaming = true;
    document.getElementById('btn-send').disabled = true;
    const abort = new AbortController(); AppState.abort = abort;

    if (!AppState.sessionId) {
        try {
            const title = (AppState.personId ? `【${personName(AppState.personId)}】` : '') + content.slice(0, 24) + (content.length > 24 ? '…' : '');
            const s = await API.post('/api/chats', { title, mode, person: AppState.personId, model: pick.model, provider: pick.provider, thinking: pick.thinking || '' });
            AppState.sessionId = s.id; AppState.session = s; AppState.pendingPick = null;
            updateModelInfo();
            document.getElementById('session-title').textContent = stripPersonPrefix(title);
        } catch (e) { toast('创建会话失败: ' + e.message, true); AppState.isStreaming = false; document.getElementById('btn-send').disabled = false; return; }
    }
    if (!preset) { input.value = ''; autoGrow(input); }
    appendMessage('user', content, action ? { ...savedCtx, action } : savedCtx);
    clearContext();
    const div = document.createElement('div'); div.className = 'message assistant streaming';
    div.innerHTML = '<div class="message-avatar">🌙</div><div style="min-width:0;"><div class="message-bubble"></div></div>';
    document.getElementById('messages-container').appendChild(div);
    const bubble = div.querySelector('.message-bubble');
    scrollToBottom();
    let full = '', gotDone = false, reader = null;
    try {
        const resp = await fetch(`/api/chats/${AppState.sessionId}/messages`, {
            method: 'POST', headers: { 'Content-Type': 'application/json' }, signal: abort.signal,
            body: JSON.stringify({ content, mode, person: AppState.personId, selected_context: Object.keys(savedCtx).length ? savedCtx : null, view_context: viewContext(), model: pick.model, provider: pick.provider, thinking: pick.thinking || '', action }),
        });
        if (!resp.ok) throw new Error(await resp.text());
        reader = resp.body.getReader();
        const dec = new TextDecoder(); let buf = '';
        let toolDiv = null, thinkDiv = null;
        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            buf += dec.decode(value, { stream: true });
            const lines = buf.split('\n'); buf = lines.pop() || '';
            for (const line of lines) {
                if (!line.startsWith('data: ')) continue;
                let d; try { d = JSON.parse(line.slice(6)); } catch (_) { continue; }
                if (d.type === 'thinking') {
                    if (!thinkDiv) { thinkDiv = appendThinking(); div.before(thinkDiv); }
                    const body = thinkDiv.querySelector('.think-body');
                    body.textContent += d.content;
                    scrollToBottom();
                }
                else if (d.type === 'warning') { toast(d.message, true); }
                else if (d.type === 'token') { full += d.content; bubble.textContent = full; scrollToBottom(); }
                else if (d.type === 'tool_start') { div.before(toolDiv = appendToolEvent(d, false)); scrollToBottom(); }
                else if (d.type === 'tool_result') {
                    if (toolDiv) { toolDiv.classList.add('done'); toolDiv.querySelector('summary').textContent = toolDiv.querySelector('summary').textContent.replace(' …', ''); toolDiv.querySelector('div').textContent = d.summary || ''; }
                    if (d.meta && d.meta.pending_update) showPendingUpdate(d.meta.pending_update);
                    if (d.meta && d.meta.note_added) { AppState.person = null; API.get(`/api/people/${AppState.personId}`).then(p => AppState.person = p).catch(() => {}); }
                    div.remove(); document.getElementById('messages-container').appendChild(div);
                }
                else if (d.type === 'done') {
                    gotDone = true; bubble.innerHTML = renderMarkdown(full);
                    if (d.session_title && AppState.session) AppState.session.title = d.session_title;
                    if (thinkDiv) thinkDiv.querySelector('summary').textContent = '💭 思考过程';
                }
                else if (d.type === 'error') throw new Error(d.message || '服务器错误');
            }
        }
    } catch (e) {
        bubble.innerHTML = `<span class="text-red">❌ ${esc(e.name === 'AbortError' ? '已中断' : e.message)}</span>`;
        // 失败像是网络/跳板问题时刷新一下状态，让输入框上方的提示与现实一致
        if (/proxy|socks|timeout|连接|超时|403/i.test(e.message || '')) loadCatalog();
    } finally {
        if (reader) { try { await reader.cancel(); } catch (_) {} }
        AppState.abort = null; AppState.isStreaming = false;
        div.classList.remove('streaming');
        document.getElementById('btn-send').disabled = false;
    }
    if (!gotDone && AppState.sessionId) { try { const s = await API.get(`/api/chats/${AppState.sessionId}`); renderMessages(s.messages); } catch (_) {} }
    await loadSessions();
    scrollToBottom();
}
