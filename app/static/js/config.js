/* ===== Configuration Page Logic ===== */

let _configProvider = 'ollama';

async function loadConfig() {
    try {
        const resp = await fetch('/api/config');
        if (resp.ok) {
            AppState.config = await resp.json();
        }
    } catch (e) {
        // Use defaults
    }
}

async function loadConfigPage() {
    const config = AppState.config;

    // Set provider toggle
    _configProvider = config.provider || 'ollama';
    updateProviderUI();

    // Set values
    document.getElementById('ollama-host').value = config.ollama_host || 'http://127.0.0.1';
    document.getElementById('ollama-port').value = config.ollama_port || 11434;
    document.getElementById('deepseek-key').value = config.deepseek_api_key || '';
    document.getElementById('deepseek-url').value = config.deepseek_base_url || 'https://api.deepseek.com';

    // Bind provider toggle (use onclick assignment so repeated visits don't stack listeners)
    document.querySelectorAll('.toggle-btn').forEach(btn => {
        btn.onclick = () => {
            _configProvider = btn.dataset.provider;
            updateProviderUI();
        };
    });

    // Refresh models on load
    await refreshModels();
}

function updateProviderUI() {
    document.querySelectorAll('.toggle-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.provider === _configProvider);
    });

    document.getElementById('ollama-settings').classList.toggle('hidden', _configProvider !== 'ollama');
    document.getElementById('deepseek-settings').classList.toggle('hidden', _configProvider !== 'deepseek');
}

async function refreshModels() {
    const select = document.getElementById('model-select');
    const savedModel = AppState.config.default_model || '';
    select.innerHTML = '<option value="">加载中...</option>';

    try {
        const resp = await fetch(`/api/config/models?provider=${_configProvider}`);
        if (resp.ok) {
            const models = await resp.json();
            AppState.models = models;

            if (models.length === 0) {
                // No models from API, keep saved model as option
                if (savedModel) {
                    select.innerHTML = `<option value="${savedModel}">${savedModel}</option>`;
                } else {
                    select.innerHTML = '<option value="">无可用模型 — 请检查服务是否运行</option>';
                }
            } else {
                select.innerHTML = models.map(m =>
                    `<option value="${m.name}">${m.name} ${m.size ? '(' + m.size + ')' : ''} [${m.provider}]</option>`
                ).join('');
                if (savedModel) {
                    select.value = savedModel;
                }
            }
        } else {
            if (savedModel) {
                select.innerHTML = `<option value="${savedModel}">${savedModel}</option>`;
            } else {
                select.innerHTML = '<option value="">获取失败</option>';
            }
        }
    } catch (e) {
        if (savedModel) {
            select.innerHTML = `<option value="${savedModel}">${savedModel} (离线)</option>`;
        } else {
            select.innerHTML = '<option value="">连接失败</option>';
        }
    }
}

async function testConnection() {
    const resultDiv = document.getElementById('test-result');
    resultDiv.classList.remove('hidden', 'success', 'error');
    resultDiv.textContent = '测试中...';
    resultDiv.className = 'test-result';

    const body = {
        provider: _configProvider,
    };

    if (_configProvider === 'ollama') {
        body.host = document.getElementById('ollama-host').value;
        body.port = parseInt(document.getElementById('ollama-port').value) || 11434;
    } else {
        body.api_key = document.getElementById('deepseek-key').value;
        body.base_url = document.getElementById('deepseek-url').value;
    }

    try {
        const resp = await fetch('/api/config/test', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        });
        const data = await resp.json();

        if (data.success) {
            resultDiv.classList.add('success');
            resultDiv.textContent = `✅ ${data.message}`;
            if (data.models && data.models.length > 0) {
                const select = document.getElementById('model-select');
                select.innerHTML = data.models.map(m =>
                    `<option value="${m}">${m}</option>`
                ).join('');
            }
        } else {
            resultDiv.classList.add('error');
            resultDiv.textContent = `❌ ${data.message}`;
        }
    } catch (e) {
        resultDiv.classList.add('error');
        resultDiv.textContent = `❌ 请求失败: ${e.message}`;
    }
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
        const resp = await fetch('/api/config', {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(config),
        });

        if (resp.ok) {
            AppState.config = config;
            alert('配置已保存！');
        } else {
            alert('保存失败');
        }
    } catch (e) {
        alert(`保存失败: ${e.message}`);
    }
}
