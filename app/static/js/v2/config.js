/* ===== Config modal ===== */
let _configProvider = 'ollama';

async function loadConfig() {
    try { AppState.config = await API.get('/api/config'); } catch (_) { AppState.config = {}; }
}

async function loadConfigPage() {
    const c = AppState.config || {};
    _configProvider = c.provider || 'ollama';
    document.getElementById('ollama-host').value = c.ollama_host || 'http://127.0.0.1';
    document.getElementById('ollama-port').value = c.ollama_port || 11434;
    document.getElementById('deepseek-key').value = c.deepseek_api_key || '';
    document.getElementById('deepseek-url').value = c.deepseek_base_url || 'https://api.deepseek.com';
    document.querySelectorAll('.toggle-btn').forEach(btn => btn.onclick = () => { _configProvider = btn.dataset.provider; updateProviderUI(); });
    updateProviderUI();
    refreshModels();
    refreshIndexInfo();
}

function updateProviderUI() {
    document.querySelectorAll('.toggle-btn').forEach(btn => btn.classList.toggle('active', btn.dataset.provider === _configProvider));
    document.getElementById('ollama-settings').classList.toggle('hidden', _configProvider !== 'ollama');
    document.getElementById('deepseek-settings').classList.toggle('hidden', _configProvider !== 'deepseek');
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
    else { body.api_key = document.getElementById('deepseek-key').value; body.base_url = document.getElementById('deepseek-url').value; }
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
        default_model: document.getElementById('model-select').value,
    };
    try {
        await API.put('/api/config', config);
        AppState.config = { ...AppState.config, ...config };
        updateModelInfo();
        toast('配置已保存');
    } catch (e) { toast('保存失败: ' + e.message, true); }
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
