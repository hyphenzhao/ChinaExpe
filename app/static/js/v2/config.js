/* ===== Config modal ===== */
let _configProvider = 'ollama';

async function loadConfig() {
    try { AppState.config = await API.get('/api/config'); } catch (_) { AppState.config = {}; }
}

const PROVIDERS = ['ollama', 'deepseek', 'openai', 'anthropic'];

async function loadConfigPage() {
    const c = AppState.config || {};
    _configProvider = c.provider || 'ollama';
    document.getElementById('ollama-host').value = c.ollama_host || 'http://127.0.0.1';
    document.getElementById('ollama-port').value = c.ollama_port || 11434;
    document.getElementById('deepseek-key').value = c.deepseek_api_key || '';
    document.getElementById('deepseek-url').value = c.deepseek_base_url || 'https://api.deepseek.com';
    document.getElementById('openai-key').value = c.openai_api_key || '';
    document.getElementById('openai-url').value = c.openai_base_url || 'https://api.openai.com';
    document.getElementById('anthropic-key').value = c.anthropic_api_key || '';
    document.getElementById('anthropic-url').value = c.anthropic_base_url || 'https://api.anthropic.com';
    document.getElementById('proxy-enabled').checked = !!c.proxy_enabled;
    document.getElementById('proxy-autostart').checked = c.proxy_autostart !== false;
    document.getElementById('proxy-url').value = c.proxy_url || 'socks5h://127.0.0.1:1080';
    document.getElementById('proxy-ssh-user').value = c.proxy_ssh_user || 'root';
    document.getElementById('proxy-ssh-host').value = c.proxy_ssh_host || '45.77.19.55';
    document.getElementById('proxy-ssh-port').value = c.proxy_ssh_port || 22;
    const on = c.proxy_providers || ['openai', 'anthropic'];
    document.querySelectorAll('.proxy-provider').forEach(cb => cb.checked = on.includes(cb.value));
    document.querySelectorAll('.toggle-btn').forEach(btn => btn.onclick = () => { _configProvider = btn.dataset.provider; updateProviderUI(); refreshModels(); });
    updateProviderUI();
    refreshModels();
    refreshIndexInfo();
    refreshProxyStatus();
}

function updateProviderUI() {
    document.querySelectorAll('.toggle-btn').forEach(btn => btn.classList.toggle('active', btn.dataset.provider === _configProvider));
    PROVIDERS.forEach(p => {
        const el = document.getElementById(p + '-settings');
        if (el) el.classList.toggle('hidden', p !== _configProvider);
    });
}

async function refreshModels() {
    const select = document.getElementById('model-select');
    const saved = AppState.config.default_model || '';
    select.innerHTML = '<option value="">加载中...</option>';
    try {
        const models = await API.get(`/api/config/models?provider=${_configProvider}`);
        if (!models.length) {
            select.innerHTML = saved ? `<option value="${esc(saved)}">${esc(saved)}</option>` : '<option value="">无可用模型</option>';
        } else {
            select.innerHTML = models.map(m => `<option value="${esc(m.name)}">${esc(m.name)}${m.size ? ' (' + m.size + ')' : ''}</option>`).join('');
            if (saved && models.some(m => m.name === saved)) select.value = saved;
            else if (saved) { select.insertAdjacentHTML('afterbegin', `<option value="${esc(saved)}">${esc(saved)}</option>`); select.value = saved; }
        }
    } catch (_) {
        select.innerHTML = saved ? `<option value="${esc(saved)}">${esc(saved)} (离线)</option>` : '<option value="">连接失败</option>';
    }
}

async function testConnection() {
    const out = document.getElementById('test-result');
    out.className = 'test-result'; out.textContent = '测试中...';
    const body = { provider: _configProvider };
    if (_configProvider === 'ollama') { body.host = document.getElementById('ollama-host').value; body.port = parseInt(document.getElementById('ollama-port').value) || 11434; }
    else { body.api_key = document.getElementById(_configProvider + '-key').value; body.base_url = document.getElementById(_configProvider + '-url').value; }
    try {
        const d = await API.post('/api/config/test', body);
        out.classList.add(d.success ? 'success' : 'error');
        out.textContent = (d.success ? '✅ ' : '❌ ') + d.message;
        if (d.success && d.models && d.models.length) {
            const select = document.getElementById('model-select');
            select.innerHTML = d.models.map(m => `<option value="${esc(m)}">${esc(m)}</option>`).join('');
        }
    } catch (e) { out.classList.add('error'); out.textContent = '❌ ' + e.message; }
}

async function saveConfig() {
    const config = {
        provider: _configProvider,
        ollama_host: document.getElementById('ollama-host').value,
        ollama_port: parseInt(document.getElementById('ollama-port').value) || 11434,
        deepseek_api_key: document.getElementById('deepseek-key').value,
        deepseek_base_url: document.getElementById('deepseek-url').value,
        openai_api_key: document.getElementById('openai-key').value,
        openai_base_url: document.getElementById('openai-url').value,
        anthropic_api_key: document.getElementById('anthropic-key').value,
        anthropic_base_url: document.getElementById('anthropic-url').value,
        default_model: document.getElementById('model-select').value,
        proxy_enabled: document.getElementById('proxy-enabled').checked,
        proxy_autostart: document.getElementById('proxy-autostart').checked,
        proxy_url: document.getElementById('proxy-url').value || 'socks5h://127.0.0.1:1080',
        proxy_ssh_user: document.getElementById('proxy-ssh-user').value || 'root',
        proxy_ssh_host: document.getElementById('proxy-ssh-host').value || '45.77.19.55',
        proxy_ssh_port: parseInt(document.getElementById('proxy-ssh-port').value) || 22,
        proxy_providers: [...document.querySelectorAll('.proxy-provider')].filter(c => c.checked).map(c => c.value),
    };
    try {
        const r = await API.put('/api/config', config);
        AppState.config = { ...AppState.config, ...config };
        updateModelInfo();
        toast('配置已保存' + (r && r.proxy && r.proxy.message ? '；' + r.proxy.message : ''));
        refreshProxyStatus();
    } catch (e) { toast('保存失败: ' + e.message, true); }
}

/* ---------- 跳板 ---------- */
function _proxyOut(ok, msg) {
    const out = document.getElementById('proxy-result');
    out.className = 'test-result ' + (ok ? 'success' : 'error');
    out.textContent = (ok ? '✅ ' : '❌ ') + msg;
}

async function refreshProxyStatus() {
    const el = document.getElementById('proxy-status');
    try {
        const s = await API.get('/api/config/proxy');
        el.innerHTML = `隧道：${s.listening ? '<span class="text-green">已监听</span>' : '<span class="text-red">未监听</span>'}`
            + ` ${esc(s.proxy_url || '')} · 跳板机 ${esc(s.ssh || '')}`
            + ` · 走跳板：${(s.providers || []).map(esc).join('、') || '无'}`
            + (s.managed_by_app ? ` · 由本服务启动 pid ${s.pid}` : '');
    } catch (e) { el.textContent = '无法获取跳板状态'; }
}

async function proxyAction(what) {
    _proxyOut(true, what === 'start' ? '正在启动隧道…' : '正在停止隧道…');
    try {
        const r = await API.post(`/api/config/proxy/${what}`, {});
        _proxyOut(r.success, r.message);
    } catch (e) { _proxyOut(false, e.message); }
    refreshProxyStatus();
}

async function proxyTest() {
    _proxyOut(true, '正在测试 OpenAI / Anthropic 可达性…');
    try {
        const r = await API.post('/api/config/proxy/test', {});
        const detail = Object.entries(r.results || {}).map(([k, v]) => `${k}: ${v.ok ? 'HTTP ' + v.status : (v.error || '失败')}`).join(' · ');
        _proxyOut(r.success, `${r.message}${detail ? '（' + detail + '）' : ''}`);
    } catch (e) { _proxyOut(false, e.message); }
    refreshProxyStatus();
}

async function _kbAction(url, startMsg) {
    const out = document.getElementById('index-result');
    out.className = 'test-result'; out.textContent = startMsg;
    try {
        const d = await API.post(url);
        out.classList.add(d.success === false ? 'error' : 'success');
        out.textContent = (d.success === false ? '❌ ' : '✅ ') + (d.message || JSON.stringify(d));
    } catch (e) { out.classList.add('error'); out.textContent = '❌ ' + e.message; }
    refreshIndexInfo();
}
function buildKnowledgeIndex() { return _kbAction('/api/knowledge/build-index', '⏳ 正在扫描文件并生成索引…'); }
function importLiterature() { return _kbAction('/api/knowledge/import-literature', '⏳ 正在导入典籍与技能（可能需要一两分钟）…'); }
function buildVectors() { return _kbAction('/api/knowledge/build-vectors', '⏳ 正在向量化（需要 Ollama bge-m3，可能较慢）…'); }

async function refreshIndexInfo() {
    const el = document.getElementById('index-info');
    try {
        const s = await API.get('/api/knowledge/status');
        const i = s.index_info || {};
        el.innerHTML = `本地索引：${i.exists ? `<span class="text-green">已建立</span> ${i.file_count} 文件 / ${i.term_count} 词 / ${esc(i.built_at || '')}` : '<span class="text-red">未建立</span>'}
            &nbsp;|&nbsp; 向量库：${s.lancedb_available ? '<span class="text-green">可用</span>' : '<span class="text-red">不可用</span>'}
            ${s.literature ? `&nbsp;|&nbsp; 典籍：${s.literature.files} 篇` : ''}`;
    } catch (_) { el.textContent = '无法获取知识库状态'; }
}
