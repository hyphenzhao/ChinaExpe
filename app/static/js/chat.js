/* ===== Chat Page Logic ===== */

/* Simple markdown-to-HTML renderer */
function renderMarkdown(text) {
    if (!text) return '';
    let html = text;

    // Escape HTML except what we'll generate
    html = html.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

    // Code blocks (fenced)
    html = html.replace(/```(\w*)\n([\s\S]*?)```/g, '<pre><code>$2</code></pre>');
    // Inline code
    html = html.replace(/`([^`]+)`/g, '<code>$1</code>');

    // Headers
    html = html.replace(/^#### (.+)$/gm, '<h4>$1</h4>');
    html = html.replace(/^### (.+)$/gm, '<h3>$1</h3>');
    html = html.replace(/^## (.+)$/gm, '<h2>$1</h2>');
    html = html.replace(/^# (.+)$/gm, '<h1>$1</h1>');

    // Bold and italic
    html = html.replace(/\*\*\*(.+?)\*\*\*/g, '<strong><em>$1</em></strong>');
    html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    html = html.replace(/\*(.+?)\*/g, '<em>$1</em>');

    // Blockquote
    html = html.replace(/^&gt; (.+)$/gm, '<blockquote>$1</blockquote>');
    // Merge consecutive blockquotes
    html = html.replace(/<\/blockquote>\n<blockquote>/g, '<br>');

    // Horizontal rule
    html = html.replace(/^---$/gm, '<hr>');

    // Unordered lists
    html = html.replace(/^[\-\*] (.+)$/gm, '<li>$1</li>');
    html = html.replace(/(<li>.*<\/li>\n?)+/g, '<ul>$&</ul>');

    // Ordered lists
    html = html.replace(/^\d+\. (.+)$/gm, '<li>$1</li>');

    // Tables
    html = html.replace(/^\|(.+)\|$/gm, (line) => {
        const cells = line.split('|').filter(c => c.trim()).map(c => `<td>${c.trim()}</td>`).join('');
        return `<tr>${cells}</tr>`;
    });
    html = html.replace(/(<tr>.*<\/tr>\n?)+/g, '<table>$&</table>');

    // Paragraphs (double newlines)
    const blocks = html.split(/\n\n+/);
    html = blocks.map(b => {
        b = b.trim();
        if (!b) return '';
        if (b.startsWith('<h') || b.startsWith('<ul') || b.startsWith('<ol') ||
            b.startsWith('<table') || b.startsWith('<pre') || b.startsWith('<blockquote') ||
            b.startsWith('<hr')) {
            return b;
        }
        return '<p>' + b.replace(/\n/g, '<br>') + '</p>';
    }).join('\n');

    return html;
}

async function initChatPage() {
    // Load sessions list
    await loadSessionsList();
    // Load people list for chart reading
    await loadPeopleList();
    // Show current model info
    updateModelInfo();
    // Update UI based on mode
    updateModeUI();
    // Restore session if available
    if (AppState.currentSessionId) {
        await loadSession(AppState.currentSessionId);
    }
}

function updateModelInfo() {
    const el = document.getElementById('sidebar-model-info');
    const cfg = AppState.config;
    if (cfg.default_model) {
        el.textContent = `🤖 ${cfg.default_model} (${cfg.provider})`;
    } else {
        el.textContent = '⚠️ 未配置模型 — 前往设置';
        el.style.color = 'var(--accent-red)';
    }
}

/* ===== Mode Management ===== */

function setMode(mode) {
    AppState.mode = mode;
    updateModeUI();
    clearChartDisplay();

    if (mode === 'theory') {
        AppState.chartType = null;
        AppState.currentPerson = null;
        AppState.selectedContext = {};
        updateContextTags();
    } else {
        AppState.chartType = document.getElementById('chart-type-select').value;
    }
}

function updateModeUI() {
    document.querySelectorAll('.mode-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.mode === AppState.mode);
    });

    const chartOptions = document.getElementById('chart-mode-options');

    const tab = document.getElementById('chart-panel-tab');
    if (AppState.mode === 'chart') {
        chartOptions.classList.remove('hidden');
        if (tab) tab.classList.add('visible');
    } else {
        chartOptions.classList.add('hidden');
        const panel = document.getElementById('chart-panel-right');
        if (panel) { panel.classList.add('hidden'); panel.classList.add('collapsed'); }
        if (tab) { tab.classList.remove('visible'); tab.classList.add('collapsed'); }
        const inline = document.getElementById('chart-inline-wrapper');
        if (inline) inline.remove();
        document.getElementById('chart-display').innerHTML = '';
    }
}

function toggleChartDisplay() {
    const display = document.getElementById('chart-display');
    display.classList.toggle('collapsed');
}

function toggleChartPanel() {
    const panel = document.getElementById('chart-panel-right');
    const tab = document.getElementById('chart-panel-tab');
    const wasCollapsed = panel.classList.contains('collapsed');
    if (wasCollapsed) {
        panel.classList.remove('collapsed');
        if (tab) tab.classList.remove('collapsed');
    } else {
        panel.classList.add('collapsed');
        if (tab) tab.classList.add('collapsed');
    }
}

let _lastWide = null;
function _isWideScreen() { return window.innerWidth >= window.innerHeight; }

window.addEventListener('resize', () => {
    const nowWide = _isWideScreen();
    if (_lastWide !== null && _lastWide !== nowWide && AppState.mode === 'chart' && AppState.currentPerson) {
        loadAndDisplayChart();
    }
    _lastWide = nowWide;
});

function _getChartContainer() {
    if (_isWideScreen()) {
        const panel = document.getElementById('chart-panel-right');
        panel.classList.remove('hidden', 'collapsed');
        const tab = document.getElementById('chart-panel-tab');
        if (tab) { tab.classList.add('visible'); tab.classList.remove('collapsed'); }
        const inline = document.getElementById('chart-inline-wrapper');
        if (inline) inline.remove();
        return document.getElementById('chart-display-wrapper-panel');
    } else {
        const panel = document.getElementById('chart-panel-right');
        panel.classList.add('hidden');
        const tab = document.getElementById('chart-panel-tab');
        if (tab) tab.classList.remove('visible');
        let wrapper = document.getElementById('chart-inline-wrapper');
        if (!wrapper) {
            wrapper = document.createElement('div');
            wrapper.id = 'chart-inline-wrapper';
            // Toggle button
            const toggleBtn = document.createElement('button');
            toggleBtn.className = 'chart-toggle-btn';
            toggleBtn.innerHTML = '<span id="chart-inline-toggle-icon">▼</span> 命盘';
            toggleBtn.onclick = function() {
                const cd = document.getElementById('chart-display');
                const icon = document.getElementById('chart-inline-toggle-icon');
                if (cd.style.display === 'none') {
                    cd.style.display = '';
                    icon.textContent = '▼';
                } else {
                    cd.style.display = 'none';
                    icon.textContent = '▶';
                }
            };
            wrapper.appendChild(toggleBtn);
            const chatMain = document.querySelector('.chat-main');
            const messages = document.getElementById('messages-container');
            chatMain.insertBefore(wrapper, messages);
        }
        return wrapper;
    }
}

async function onChartTypeChange() {
    AppState.chartType = document.getElementById('chart-type-select').value;
    clearChartDisplay();
    AppState.selectedContext = {};
    updateContextTags();
    if (AppState.currentPerson && AppState.mode === 'chart') {
        await loadAndDisplayChart();
    }
}

async function onPersonChange() {
    AppState.currentPerson = document.getElementById('person-select').value;
    clearChartDisplay();
    AppState.selectedContext = {};
    updateContextTags();
    if (AppState.currentPerson && AppState.mode === 'chart') {
        await loadAndDisplayChart();
    }
}

async function loadAndDisplayChart() {
    if (!AppState.currentPerson) return;

    const container = _getChartContainer();
    const chartDisplay = document.getElementById('chart-display');
    if (chartDisplay.parentElement !== container) {
        container.appendChild(chartDisplay);
    }
    chartDisplay.classList.remove('collapsed');

    if (AppState.chartType === 'ziwei') {
        try {
            const resp = await fetch(`/api/charts/${AppState.currentPerson}/ziwei`);
            if (resp.ok) {
                AppState.ziweiData = await resp.json();
                renderZiweiGrid(AppState.ziweiData);
            } else {
                chartDisplay.innerHTML = '<div class="empty-state">未找到紫微斗数命盘</div>';
            }
        } catch (e) {
            chartDisplay.innerHTML = '<div class="error-message">加载命盘失败</div>';
        }
    } else if (AppState.chartType === 'shishen') {
        try {
            const resp = await fetch(`/api/charts/${AppState.currentPerson}/shishen`);
            if (resp.ok) {
                AppState.shishenData = await resp.json();
                renderShiShenDisplay(AppState.shishenData);
            } else {
                chartDisplay.innerHTML = '<div class="empty-state">未找到十神命盘</div>';
            }
        } catch (e) {
            chartDisplay.innerHTML = '<div class="error-message">加载命盘失败</div>';
        }
    }
}

function clearChartDisplay() {
    document.getElementById('chart-display').innerHTML = '';
    const panel = document.getElementById('chart-panel-right');
    if (panel) { panel.classList.add('hidden'); panel.classList.add('collapsed'); }
    const tab = document.getElementById('chart-panel-tab');
    if (tab) { tab.classList.remove('visible'); tab.classList.add('collapsed'); }
    const inline = document.getElementById('chart-inline-wrapper');
    if (inline) inline.remove();
}

/* ===== People List ===== */

async function loadPeopleList() {
    const select = document.getElementById('person-select');
    try {
        const resp = await fetch('/api/charts');
        if (resp.ok) {
            const people = await resp.json();
            select.innerHTML = '<option value="">选择人物...</option>' +
                people.map(p => {
                    const types = [];
                    if (p.has_ziwei) types.push('紫微');
                    if (p.has_shishen) types.push('十神');
                    return `<option value="${p.name}">${p.display_name || p.name} (${types.join('/')})</option>`;
                }).join('');
        }
    } catch (e) {
        // Keep default options
    }
}

/* ===== Chat Sessions ===== */

async function loadSessionsList() {
    const listEl = document.getElementById('chat-list');
    if (!listEl) return;
    try {
        const resp = await fetch('/api/chats');
        if (!resp.ok) throw new Error('API error');
        const sessions = await resp.json();
        if (sessions.length === 0) {
            listEl.innerHTML = '<div class="chat-list-empty">暂无对话</div>';
            return;
        }
        // Remove dupes by id (defensive)
        const seen = new Set();
        const unique = sessions.filter(s => { const ok = !seen.has(s.id); seen.add(s.id); return ok; });
        listEl.innerHTML = unique.map(s => `
            <div class="chat-list-item ${s.id === AppState.currentSessionId ? 'active' : ''}" data-sid="${s.id}" onclick="selectSession('${s.id}')">
                <div class="chat-list-item-info">
                    <div class="chat-list-item-title">${escapeHtml(s.title)}</div>
                    <div class="chat-list-item-meta">${escapeHtml(s.mode === 'theory' ? '📚理论' : s.mode === 'chart_ziwei' ? '🔮紫微' : '🪷十神')} · ${s.message_count}条 · ${formatDate(s.updated_at)}</div>
                </div>
                <button class="chat-list-item-delete" onclick="event.stopPropagation(); deleteSession('${s.id}')">🗑</button>
            </div>
        `).join('');
    } catch (e) {
        console.error('loadSessionsList:', e);
        listEl.innerHTML = '<div class="chat-list-empty">加载失败，请刷新页面</div>';
    }
}

async function selectSession(id) {
    if (AppState.isStreaming) return; // Don't switch while streaming
    AppState.currentSessionId = id;
    try {
        await loadSession(id);
    } catch (e) {
        console.error('selectSession error:', e);
    }
    await loadSessionsList();
}

async function loadSession(id) {
    const container = document.getElementById('messages-container');
    try {
        const resp = await fetch(`/api/chats/${id}`);
        if (resp.ok) {
            const session = await resp.json();
            AppState.currentSession = session;
            AppState.mode = session.mode.includes('chart') ? 'chart' : 'theory';
            if (session.mode === 'chart_ziwei') AppState.chartType = 'ziwei';
            if (session.mode === 'chart_shishen') AppState.chartType = 'shishen';
            AppState.currentPerson = session.person;
            AppState.currentSessionId = session.id;

            // Update person selector
            if (session.person) {
                document.getElementById('person-select').value = session.person;
            }

            updateModeUI();

            // Render messages
            const _w = document.getElementById('welcome-message'); if (_w) _w.classList.add('hidden');
            container.innerHTML = '';

            session.messages.forEach(msg => {
                appendMessage(msg.role, msg.content, msg.context);
            });

            // Load chart if in chart mode
            if (session.mode.startsWith('chart_') && session.person) {
                await loadAndDisplayChart();
            }
            // Scroll after chart renders
            setTimeout(() => scrollToBottom(), 100);
        } else {
            const _w = document.getElementById('welcome-message'); if (_w) _w.classList.add('hidden');
            container.innerHTML = '<div class="empty-state">⚠️ 加载会话失败，请重试或选择其他对话</div>';
        }
    } catch (e) {
        console.error('Failed to load session:', e);
        const _w3 = document.getElementById('welcome-message'); if (_w3) _w3.classList.add('hidden');
        container.innerHTML = '<div class="empty-state">⚠️ 网络错误，无法加载会话</div>';
    }
}

async function newChat() {
    // Cancel any in-flight streaming request
    if (AppState.currentAbortController) {
        AppState.currentAbortController.abort();
        AppState.currentAbortController = null;
    }
    // Force-reset streaming lock (safety)
    AppState.isStreaming = false;
    document.getElementById('btn-send').disabled = false;

    AppState.currentSessionId = null;
    AppState.currentSession = null;
    AppState.mode = 'theory';
    AppState.chartType = 'ziwei';
    AppState.currentPerson = null;
    AppState.selectedContext = {};
    AppState.ziweiData = null;
    AppState.shishenData = null;

    updateModeUI();
    clearChartDisplay();
    updateContextTags();
    const metaEl = document.getElementById('meta-indicator');
    if (metaEl) metaEl.classList.add('hidden');

    const container = document.getElementById('messages-container');
    if (container) {
        container.innerHTML = '';
        container.scrollTop = 0;
    }
    const welcomeEl = document.getElementById('welcome-message');
    if (welcomeEl) welcomeEl.classList.remove('hidden');
    await loadSessionsList();
}

async function deleteSession(id) {
    if (!confirm('确认删除此对话？')) return;
    try {
        await fetch(`/api/chats/${id}`, { method: 'DELETE' });
        if (AppState.currentSessionId === id) {
            await newChat();
        }
        await loadSessionsList();
    } catch (e) {
        console.error('Delete failed:', e);
    }
}

/* ===== Messaging ===== */

async function sendMessage() {
    const input = document.getElementById('message-input');
    console.log('[sendMessage] called, input:', !!input, 'isStreaming:', AppState.isStreaming, 'sessionId:', AppState.currentSessionId);
    const content = input ? input.value.trim() : '';
    if (!content) { console.log('[sendMessage] blocked: empty content'); return; }
    if (AppState.isStreaming) { console.log('[sendMessage] blocked: isStreaming=true'); return; }

    const savedContext = { ...AppState.selectedContext };

    AppState.isStreaming = true;
    document.getElementById('btn-send').disabled = true;
    const abortController = new AbortController();
    AppState.currentAbortController = abortController;
    const safetyTimer = setTimeout(() => {
        if (AppState.isStreaming) {
            console.log('[sendMessage] timeout - aborting');
            abortController.abort('timeout');
        }
    }, 90000);

    let effectiveMode = 'theory';
    if (AppState.mode === 'chart') {
        effectiveMode = AppState.chartType === 'ziwei' ? 'chart_ziwei' : 'chart_shishen';
    }

    if (!AppState.currentSessionId) {
        try {
            const config = AppState.config;
            console.log('[sendMessage] creating session, provider:', config.provider, 'model:', config.default_model);
            let sessionTitle = content.slice(0, 30);
            if (effectiveMode.startsWith('chart_') && AppState.currentPerson) {
                const chartLabel = AppState.chartType === 'ziwei' ? '紫微' : '十神';
                sessionTitle = `【${AppState.currentPerson}·${chartLabel}】` + (content.length > 20 ? content.slice(0, 20) + '…' : content);
            }
            const resp = await fetch('/api/chats', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    title: sessionTitle,
                    mode: effectiveMode,
                    person: AppState.currentPerson,
                    model: config.default_model,
                    provider: config.provider,
                }),
            });
            if (!resp.ok) {
                const err = await resp.json().catch(() => ({}));
                throw new Error(err.detail || `创建会话失败 (${resp.status})`);
            }
            const session = await resp.json();
            console.log('[sendMessage] session created:', session.id);
            AppState.currentSessionId = session.id;
            AppState.currentSession = session;
        } catch (e) {
            console.error('[sendMessage] session creation failed:', e.message);
            alert('发送失败: ' + e.message);
            AppState.isStreaming = false;
            document.getElementById('btn-send').disabled = false;
            clearTimeout(safetyTimer);
            return;
        }
    }

    // Now safe to clear input and append user message
    input.value = '';
    const _w2 = document.getElementById('welcome-message'); if (_w2) _w2.classList.add('hidden');
    appendMessage('user', content, savedContext);
    scrollToBottom();

    // Create streaming placeholder
    const assistantDiv = createStreamingMessage();
    let fullContent = '';
    let receivedDone = false;
    let reader = null;

    try {
        const resp = await fetch(`/api/chats/${AppState.currentSessionId}/messages`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                content,
                mode: effectiveMode,
                person: AppState.currentPerson,
                selected_context: Object.keys(savedContext).length > 0 ? savedContext : null,
            }),
            signal: abortController.signal,
        });

        if (!resp.ok) {
            const errText = await resp.text().catch(() => '');
            throw new Error(errText || `请求失败 (${resp.status})`);
        }

        reader = resp.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop() || '';

            for (const line of lines) {
                if (line.startsWith('data: ')) {
                    try {
                        const data = JSON.parse(line.slice(6));
                        if (data.type === 'token') {
                            fullContent += data.content;
                            assistantDiv.querySelector('.message-bubble').textContent = fullContent;
                            scrollToBottom();
                        } else if (data.type === 'done') {
                            receivedDone = true;
                            assistantDiv.querySelector('.message-bubble').innerHTML = renderMarkdown(fullContent);
                            if (data.session_title) {
                                AppState.currentSession.title = data.session_title;
                            }
                            if (data.meta) {
                                showMetaIndicator(data.meta);
                            }
                        } else if (data.type === 'error') {
                            throw new Error(data.message || '服务器错误');
                        }
                    } catch (e) {
                        if (e.message && !e.message.startsWith('Unexpected')) throw e;
                    }
                }
            }
        }

        if (receivedDone) {
            AppState.selectedContext = {};
            updateContextTags();
        }

    } catch (e) {
        if (e.name === 'AbortError') {
            assistantDiv.querySelector('.message-bubble').innerHTML =
                `<span style="color:var(--accent-orange)">⚠️ 响应超时，正在恢复...</span>`;
        } else {
            assistantDiv.querySelector('.message-bubble').innerHTML =
                `<span style="color:var(--accent-red)">❌ ${escapeHtml(e.message || '请求失败，请检查模型配置')}</span>`;
        }
    } finally {
        if (reader) { try { await reader.cancel(); } catch (_) {} }
        clearTimeout(safetyTimer);
        AppState.currentAbortController = null;
    }

    assistantDiv.classList.remove('streaming');
    AppState.isStreaming = false;
    document.getElementById('btn-send').disabled = false;

    // Stream ended without a done event — reload messages from backend so the display
    // reflects what was actually saved (partial response, error, or nothing).
    if (!receivedDone && AppState.currentSessionId) {
        try {
            const syncResp = await fetch(`/api/chats/${AppState.currentSessionId}`);
            if (syncResp.ok) {
                const synced = await syncResp.json();
                const container = document.getElementById('messages-container');
                container.innerHTML = '';
                synced.messages.forEach(msg => appendMessage(msg.role, msg.content, msg.context));
                scrollToBottom();
            }
        } catch (_) {}
    }

    await loadSessionsList();

    if (AppState.mode === 'chart' && AppState.currentPerson) {
        await loadAndDisplayChart();
    }
    setTimeout(() => scrollToBottom(), 150);
}

function onInputKeydown(event) {
    if (event.key === 'Enter' && !event.shiftKey) {
        event.preventDefault();
        sendMessage();
    }
}

/* ===== Message Rendering ===== */

function appendMessage(role, content, context) {
    const container = document.getElementById('messages-container');
    const div = document.createElement('div');
    div.className = `message ${role}`;

    const avatarIcon = role === 'user' ? '👤' : '🌙';
    const bodyHtml = role === 'assistant' ? renderMarkdown(content) : escapeHtml(content);

    div.innerHTML = `
        <div class="message-avatar">${avatarIcon}</div>
        <div>
            <div class="message-bubble">${bodyHtml}</div>
            ${context && Object.keys(context).length > 0 ? `<div class="message-context">${formatContext(context)}</div>` : ''}
        </div>
    `;

    container.appendChild(div);
}

function createStreamingMessage() {
    const container = document.getElementById('messages-container');
    const div = document.createElement('div');
    div.className = 'message assistant streaming';
    div.innerHTML = `
        <div class="message-avatar">🌙</div>
        <div>
            <div class="message-bubble"></div>
        </div>
    `;
    container.appendChild(div);
    scrollToBottom();
    return div;
}

function scrollToBottom() {
    const container = document.getElementById('messages-container');
    container.scrollTop = container.scrollHeight;
}

function showMetaIndicator(meta) {
    const el = document.getElementById('meta-indicator');
    if (!el) return;
    const parts = [];
    if (meta.skills_loaded && meta.skills_loaded.length > 0) {
        parts.push('📚 ' + meta.skills_loaded.join('+'));
    }
    if (meta.rag_results > 0) {
        parts.push(`🔍 知识库(${meta.rag_results}条)`);
    }
    if (meta.chart_loaded) {
        parts.push('📊 命盘');
    }
    if (parts.length > 0) {
        el.textContent = parts.join(' · ');
        el.classList.remove('hidden');
    } else {
        el.classList.add('hidden');
    }
}

/* ===== Context Tags ===== */

function addContextTag(type, label, data) {
    // Merge into selectedContext
    Object.assign(AppState.selectedContext, data);

    // Remove existing tag of same type
    const existing = document.querySelector(`.context-tag[data-type="${type}"]`);
    if (existing) existing.remove();

    const tags = document.getElementById('context-tags');
    const tag = document.createElement('span');
    tag.className = 'context-tag';
    tag.dataset.type = type;
    tag.innerHTML = `${type}: ${label} <span class="remove-tag" onclick="removeContextTag(this.parentElement, '${type}')">✕</span>`;
    tags.appendChild(tag);
}

function removeContextTag(tagEl, type) {
    tagEl.remove();
    // Remove from selectedContext
    if (type === '宫位') {
        delete AppState.selectedContext.palace;
        delete AppState.selectedContext.stem_branch;
    } else if (type === '星曜') {
        delete AppState.selectedContext.star;
        delete AppState.selectedContext.brightness;
        delete AppState.selectedContext.transform;
    } else if (type.includes('天干') || type.includes('藏干')) {
        delete AppState.selectedContext.stem;
        delete AppState.selectedContext.shishen;
        delete AppState.selectedContext.pillar;
        delete AppState.selectedContext.source;
    }
    updateContextTags();
}

function updateContextTags() {
    const tags = document.getElementById('context-tags');
    tags.innerHTML = '';
    const ctx = AppState.selectedContext;

    if (ctx.palace) {
        const label = ctx.stem_branch ? `${ctx.palace}·${ctx.stem_branch}` : ctx.palace;
        addContextTag('宫位', label, { palace: ctx.palace, stem_branch: ctx.stem_branch });
    }
    if (ctx.star) {
        let label = ctx.star;
        if (ctx.brightness) label += ` (${ctx.brightness})`;
        if (ctx.transform) label += ` [${ctx.transform}]`;
        addContextTag('星曜', label, { star: ctx.star, brightness: ctx.brightness, transform: ctx.transform });
    }
    if (ctx.stem && !ctx.palace) {
        let label = ctx.stem;
        if (ctx.shishen) label += ` (${ctx.shishen})`;
        const sourceLabel = ctx.source === '藏干' ? '藏干' : '天干';
        const fullType = ctx.pillar ? `${ctx.pillar}·${sourceLabel}` : sourceLabel;
        addContextTag(fullType, label, { stem: ctx.stem, shishen: ctx.shishen, pillar: ctx.pillar, source: sourceLabel });
    }
}

function formatContext(ctx) {
    const parts = [];
    if (ctx.palace) parts.push(`宫位: ${ctx.palace}${ctx.stem_branch ? '·' + ctx.stem_branch : ''}`);
    if (ctx.star) {
        let starStr = `星曜: ${ctx.star}`;
        if (ctx.brightness) starStr += `（${ctx.brightness}）`;
        if (ctx.transform) starStr += ` [${ctx.transform}]`;
        parts.push(starStr);
    }
    if (ctx.stem) parts.push(`天干: ${ctx.stem}${ctx.shishen ? '（' + ctx.shishen + '）' : ''}`);
    if (ctx.pillar && !ctx.palace) parts.push(`柱: ${ctx.pillar}`);
    return parts.join(' | ');
}

/* ===== Person Management ===== */

async function showNewPersonModal() {
    document.getElementById('new-person-id').value = '';
    const dnEl = document.getElementById('new-person-display-name');
    if (dnEl) dnEl.value = '';
    openModal('modal-new-person');
}

async function createNewPerson() {
    const personId = document.getElementById('new-person-id').value.trim();
    const displayName = document.getElementById('new-person-display-name')?.value.trim() || personId;
    if (!personId) {
        alert('请输入缩写标识');
        return;
    }
    if (!/^[a-zA-Z0-9_-]+$/.test(personId)) {
        alert('缩写标识只能包含英文字母、数字、下划线和连字符');
        return;
    }
    AppState.currentPerson = personId;
    // Create empty folder with display name if it doesn't exist
    try {
        await fetch(`/api/charts/${personId}/meta`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ display_name: displayName }),
        }).catch(() => {}); // OK if fails (no charts yet)
    } catch (_) {}
    document.getElementById('person-select').value = personId;
    closeModal('modal-new-person');
    await loadPeopleList();
    document.getElementById('person-select').value = personId;
}

function showImportModal() {
    document.getElementById('import-raw-text').value = '';
    document.getElementById('import-display-name').value = '';
    document.getElementById('import-person-id').value = '';
    const _ir = document.getElementById('import-result'); if (_ir) _ir.classList.add('hidden');
    openModal('modal-import-chart');
}

function _genAbbr(name) {
    // Auto-generate pinyin abbreviation from Chinese name
    if (!name) return '';
    // Simple: take first letter of each character's pinyin, fallback to lowercase
    const py = { '宋':'s','赵':'z','李':'l','王':'w','张':'z','刘':'l','陈':'c','杨':'y','黄':'h','周':'z','吴':'w','徐':'x','孙':'s','马':'m','朱':'z','胡':'h','郭':'g','何':'h','高':'g','林':'l','罗':'l','郑':'z','梁':'l','谢':'x','唐':'t','许':'x','韩':'h','冯':'f','邓':'d','曹':'c','彭':'p','曾':'z','肖':'x','田':'t','董':'d','潘':'p','袁':'y','蔡':'c','蒋':'j','余':'y','于':'y','杜':'d','叶':'y','程':'c','苏':'s','魏':'w','吕':'l','丁':'d','任':'r','沈':'s','姚':'y','卢':'l','姜':'j','崔':'c','钟':'z','谭':'t','陆':'l','汪':'w','范':'f','金':'j','石':'s','廖':'l','贾':'j','夏':'x','韦':'w','付':'f','方':'f','白':'b','邹':'z','孟':'m','熊':'x','秦':'q','邱':'q','江':'j','尹':'y','薛':'x','闫':'y','段':'d','雷':'l','侯':'h','龙':'l','史':'s','陶':'t','黎':'l','贺':'h','顾':'g','毛':'m','郝':'h','龚':'g','邵':'s','万':'w','钱':'q','严':'y','覃':'q','武':'w','戴':'d','莫':'m','孔':'k','向':'x','汤':'t','温':'w','康':'k','施':'s','文':'w','牛':'n','樊':'f','葛':'g','邢':'x','安':'a','齐':'q','易':'y','乔':'q','伍':'w','庞':'p','颜':'y','倪':'n','庄':'z','聂':'n','章':'z','鲁':'l','岳':'y','翟':'z','殷':'y','詹':'z','申':'s','欧':'o','耿':'g','关':'g','兰':'l','焦':'j','俞':'y','左':'z','柳':'l','甘':'g','祝':'z','包':'b','宁':'n','尚':'s','符':'f','阮':'r','尤':'y','梅':'m','童':'t','缪':'m','敖':'a','冷':'l','仇':'q','花':'h','费':'f','楼':'l','季':'j','鞠':'j','艾':'a','单':'s','荆':'j','荣':'r','桂':'g','闵':'m','游':'y','阳':'y','裴':'p','匡':'k','查':'z','鲍':'b','华':'h','曲':'q','米':'m','窦':'d','苗':'m','尉':'w','冼':'x' };
    let abbr = '';
    for (const ch of name) {
        if (py[ch]) { abbr += py[ch]; }
        else { abbr += ch.toLowerCase(); }
    }
    return abbr.slice(0, 6) || name.toLowerCase().slice(0, 6);
}

async function importChartAI() {
    const displayName = document.getElementById('import-display-name').value.trim();
    let personId = document.getElementById('import-person-id').value.trim();
    const rawText = document.getElementById('import-raw-text').value.trim();
    const resultDiv = document.getElementById('import-result');
    const btnImport = document.getElementById('btn-import');

    if (!displayName) {
        resultDiv.classList.remove('hidden');
        resultDiv.className = 'test-result error';
        resultDiv.textContent = '请填写名字';
        return;
    }

    // Auto-generate abbreviation if empty
    if (!personId) {
        personId = _genAbbr(displayName);
        document.getElementById('import-person-id').value = personId;
    }

    if (!/^[a-zA-Z0-9_-]+$/.test(personId)) {
        resultDiv.classList.remove('hidden');
        resultDiv.className = 'test-result error';
        resultDiv.textContent = '缩写只能包含英文字母、数字、下划线和连字符';
        return;
    }

    if (!rawText) {
        resultDiv.classList.remove('hidden');
        resultDiv.className = 'test-result error';
        resultDiv.textContent = '请粘贴命盘内容';
        return;
    }

    btnImport.disabled = true;
    btnImport.textContent = '⏳ AI 解析中...';
    resultDiv.classList.remove('hidden');
    resultDiv.className = 'test-result';
    resultDiv.textContent = '⏳ AI 正在识别命盘类型并提取数据...';

    try {
        const resp = await fetch('/api/charts/import', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                person: personId,
                display_name: displayName,
                chart_type: 'auto',
                raw_text: rawText,
            }),
        });

        const data = await resp.json();

        if (resp.ok && data.success) {
            const chartTypeName = data.chart_type === 'ziwei' ? '紫微斗数' : '十神·子平命理';
            resultDiv.className = 'test-result success';
            resultDiv.textContent = `✅ 已识别为「${chartTypeName}」并保存` +
                (data.extracted_summary ? ` — ${data.extracted_summary}` : '');

            // Set as current person and reload
            AppState.currentPerson = personId;
            AppState.chartType = data.chart_type;
            document.getElementById('chart-type-select').value = data.chart_type;
            await loadPeopleList();
            document.getElementById('person-select').value = personId;
            await loadAndDisplayChart();
            setTimeout(() => closeModal('modal-import-chart'), 2000);
        } else {
            resultDiv.className = 'test-result error';
            resultDiv.textContent = `❌ ${data.detail || data.message || '导入失败'}`;
        }
    } catch (e) {
        resultDiv.classList.remove('hidden');
        resultDiv.className = 'test-result error';
        resultDiv.textContent = `导入失败: ${e.message}`;
    } finally {
        btnImport.disabled = false;
        btnImport.textContent = '🤖 AI 识别导入';
    }
}

/* ===== Utilities ===== */

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function formatDate(isoString) {
    if (!isoString) return '';
    try {
        const d = new Date(isoString);
        const now = new Date();
        const diff = now - d;
        if (diff < 60000) return '刚刚';
        if (diff < 3600000) return `${Math.floor(diff / 60000)} 分钟前`;
        if (diff < 86400000) return `${Math.floor(diff / 3600000)} 小时前`;
        return `${d.getMonth()+1}/${d.getDate()} ${d.getHours()}:${String(d.getMinutes()).padStart(2,'0')}`;
    } catch (e) {
        return '';
    }
}
