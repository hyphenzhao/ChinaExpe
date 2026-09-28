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
    document.querySelectorAll('.toggle-btn').forEach(btn => btn.onclick = () => { _configProvider = btn.dataset.provider; updateProviderUI(); refreshModels(false); });
    updateProviderUI();
    await loadLibrary();
    refreshModels(false);
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

/* ---------- 模型库 ---------- */
let _library = [];          // [{provider, model, label, supports_tools, thinking, ...}]
let _defaultKey = '';       // "provider:model"

function _libKey(p, m) { return `${p}:${m}`; }
function _inLibrary(p, m) { return _library.some(x => x.provider === p && x.model === m); }

async function loadLibrary() {
    try {
        const r = await API.get('/api/config/library');
        _library = r.models || [];
        _defaultKey = r.default && r.default.model ? _libKey(r.default.provider, r.default.model) : '';
    } catch (_) { _library = []; _defaultKey = ''; }
}

async function refreshModels(force) {
    const box = document.getElementById('model-catalog');
    box.innerHTML = '<div class="text-muted" style="font-size:.75rem;">加载中…</div>';
    let rows = [];
    try {
        rows = await API.get(`/api/config/models?provider=${_configProvider}&refresh=${force ? 1 : 0}`);
    } catch (e) {
        box.innerHTML = `<div class="text-red" style="font-size:.75rem;">拉取模型列表失败：${esc(e.message)}</div>`;
        return;
    }
    // 库里已有但这次没列出来的（手工添加的、离线的）也要显示
    const extra = _library.filter(m => m.provider === _configProvider && !rows.some(r => r.name === m.model))
        .map(m => ({ name: m.model, provider: m.provider, manual: true, thinking: m.thinking }));
    renderCatalog([...rows, ...extra]);
}

function renderCatalog(rows) {
    const box = document.getElementById('model-catalog');
    if (!rows.length) { box.innerHTML = '<div class="text-muted" style="font-size:.75rem;">没有可用模型，填好 API Key 后点「刷新模型」，或手工添加 ID。</div>'; return; }
    const needsProxy = ['openai', 'anthropic'].includes(_configProvider);
    box.innerHTML = rows.map(r => {
        const key = _libKey(r.provider, r.name);
        const on = _inLibrary(r.provider, r.name);
        const tags = [
            r.thinking === 'optional' ? '<span class="mc-tag">可调思考</span>' : '',
            r.thinking === 'always' ? '<span class="mc-tag">自带思考</span>' : '',
            r.supports_tools === false ? '<span class="mc-tag warn">不支持工具</span>' : '',
            needsProxy ? '<span class="mc-tag">需跳板</span>' : '',
            r.stale ? '<span class="mc-tag warn">离线兜底</span>' : '',
            r.manual ? '<span class="mc-tag">手工添加</span>' : '',
        ].join('');
        return `<label class="mc-row">
            <input type="checkbox" class="mc-check" data-key="${esc(key)}" data-provider="${esc(r.provider)}" data-model="${esc(r.name)}" ${on ? 'checked' : ''} onchange="toggleLibraryModel(this)">
            <span class="mc-name">${esc(r.name)}</span>${tags}
            <input type="radio" name="mc-default" class="mc-default" title="设为默认" ${_defaultKey === key ? 'checked' : ''} onchange="setDefaultModel('${esc(r.provider)}','${esc(r.name)}')">
        </label>`;
    }).join('');
}

function toggleLibraryModel(cb) {
    const p = cb.dataset.provider, m = cb.dataset.model;
    if (cb.checked) { if (!_inLibrary(p, m)) _library.push({ provider: p, model: m, label: m }); }
    else _library = _library.filter(x => !(x.provider === p && x.model === m));
    if (!_library.length) _defaultKey = '';
    else if (!_library.some(x => _libKey(x.provider, x.model) === _defaultKey)) _defaultKey = _libKey(_library[0].provider, _library[0].model);
}

function setDefaultModel(provider, model) {
    if (!_inLibrary(provider, model)) _library.push({ provider, model, label: model });
    _defaultKey = _libKey(provider, model);
    const cb = document.querySelector(`.mc-check[data-key="${CSS.escape(_libKey(provider, model))}"]`);
    if (cb) cb.checked = true;
}

function addManualModel() {
    const el = document.getElementById('model-manual');
    const id = el.value.trim();
    if (!id) return;
    if (!_inLibrary(_configProvider, id)) _library.push({ provider: _configProvider, model: id, label: id });
    if (!_defaultKey) _defaultKey = _libKey(_configProvider, id);
    el.value = '';
    refreshModels(false);
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
        if (d.success) refreshModels(true);
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
    };
    // 注意：跳板字段不在这里提交，后端也会忽略；改跳板用「应用跳板设置」
    const pick = _defaultKey ? { provider: _defaultKey.split(':')[0], model: _defaultKey.slice(_defaultKey.indexOf(':') + 1) } : null;
    if (pick) config.default_model = pick.model;
    try {
        await API.put('/api/config', config);
        const lib = await API.put('/api/config/library', { models: _library, default: pick });
        _library = lib.models || _library;
        _defaultKey = lib.default && lib.default.model ? _libKey(lib.default.provider, lib.default.model) : '';
        AppState.config = { ...AppState.config, ...config, default_model: (lib.default || {}).model || '', provider: (lib.default || {}).provider || config.provider };
        await loadCatalog();
        updateModelInfo();
        toast('配置已保存；' + (lib.message || ''));
    } catch (e) { toast('保存失败: ' + e.message, true); }
}

async function applyProxySettings() {
    const body = {
        proxy_enabled: document.getElementById('proxy-enabled').checked,
        proxy_autostart: document.getElementById('proxy-autostart').checked,
        proxy_url: document.getElementById('proxy-url').value || 'socks5h://127.0.0.1:1080',
        proxy_ssh_user: document.getElementById('proxy-ssh-user').value || 'root',
        proxy_ssh_host: document.getElementById('proxy-ssh-host').value || '45.77.19.55',
        proxy_ssh_port: parseInt(document.getElementById('proxy-ssh-port').value) || 22,
        proxy_providers: [...document.querySelectorAll('.proxy-provider')].filter(c => c.checked).map(c => c.value),
    };
    _proxyOut(true, '正在应用…');
    try {
        const r = await API.put('/api/config/proxy', body);
        AppState.config = { ...AppState.config, ...body };
        _proxyOut(r.proxy ? r.proxy.success !== false : true, (r.message || '') + (r.proxy && r.proxy.message ? '；' + r.proxy.message : ''));
        await loadCatalog();
    } catch (e) { _proxyOut(false, e.message); }
    refreshProxyStatus();
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
    loadCatalog();        // 隧道状态变了，对话页那颗跳板提示要跟着变
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
