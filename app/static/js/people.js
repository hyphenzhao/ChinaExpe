/* ===== People Management Page ===== */

async function initPeoplePage() {
    console.log('[people] initPeoplePage called');
    await loadPeoplePage();
}

async function loadPeoplePage() {
    const grid = document.getElementById('people-grid');
    console.log('[people] grid found:', !!grid);
    if (!grid) return;
    try {
        const resp = await fetch('/api/charts');
        console.log('[people] fetch status:', resp.status);
        if (!resp.ok) throw new Error('API error ' + resp.status);
        const people = await resp.json();
        console.log('[people] people count:', people.length);
        if (people.length === 0) {
            grid.innerHTML = '<div class="people-empty"><div class="people-empty-icon">📭</div><p>暂无人物，去聊天页导入命盘或点击下方按钮新建</p></div>';
            return;
        }
        grid.innerHTML = people.map(p => {
            const safeName = (p.display_name || p.name).replace(/'/g, "\\'");
            return '<div class="person-card" id="card-' + p.name + '">' +
                '<div class="person-card-header"><div>' +
                '<div class="person-card-name">' + escapeHtml(p.display_name || p.name) + '</div>' +
                '<div class="person-card-id">' + escapeHtml(p.name) + '</div>' +
                '</div></div>' +
                '<div class="person-chart-badges">' +
                '<span class="chart-badge ' + (p.has_ziwei ? 'has' : 'missing') + '">🔮 紫微 ' + (p.has_ziwei ? '✓' : '—') + '</span>' +
                '<span class="chart-badge ' + (p.has_shishen ? 'has' : 'missing') + '">🪷 十神 ' + (p.has_shishen ? '✓' : '—') + '</span>' +
                '</div>' +
                '<div class="person-card-actions">' +
                '<button class="btn btn-sm" onclick="editPersonName(\'' + p.name + '\', \'' + safeName + '\')">✏️ 改名</button>' +
                (p.has_ziwei ? '<button class="btn btn-sm" style="color:var(--accent-red)" onclick="deletePersonChart(\'' + p.name + '\', \'ziwei\')">🗑 紫微</button>' : '<button class="btn btn-sm" style="color:var(--accent-green)" onclick="importChartForPerson(\'' + p.name + '\', \'' + safeName + '\', \'ziwei\')">＋ 紫微</button>') +
                (p.has_shishen ? '<button class="btn btn-sm" style="color:var(--accent-red)" onclick="deletePersonChart(\'' + p.name + '\', \'shishen\')">🗑 十神</button>' : '<button class="btn btn-sm" style="color:var(--accent-green)" onclick="importChartForPerson(\'' + p.name + '\', \'' + safeName + '\', \'shishen\')">＋ 十神</button>') +
                '<button class="btn btn-sm" style="color:var(--accent-red)" onclick="deletePerson(\'' + p.name + '\')">🗑 人物</button>' +
                '</div>' +
                '<div id="edit-' + p.name + '"></div>' +
                '</div>';
        }).join('');
        console.log('[people] rendered:', grid.innerHTML.length, 'chars');
    } catch (e) {
        grid.innerHTML = '<div class="people-empty"><div class="people-empty-icon">⚠️</div><p>加载失败</p></div>';
    }
}

function editPersonName(person, currentName) {
    const el = document.getElementById(`edit-${person}`);
    if (!el) return;
    el.innerHTML = `
        <div class="edit-name-row">
            <input type="text" id="edit-name-input-${person}" class="input" value="${escapeHtml(currentName)}" placeholder="新显示名称">
            <button class="btn btn-primary btn-sm" onclick="savePersonName('${person}')">保存</button>
            <button class="btn btn-ghost btn-sm" onclick="this.parentElement.parentElement.innerHTML=''">取消</button>
        </div>`;
    document.getElementById(`edit-name-input-${person}`).focus();
}

async function savePersonName(person) {
    const input = document.getElementById(`edit-name-input-${person}`);
    if (!input) return;
    const name = input.value.trim();
    if (!name) return;
    try {
        const resp = await fetch(`/api/charts/${person}/meta`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ display_name: name }),
        });
        if (resp.ok) {
            document.getElementById(`edit-${person}`).innerHTML = '';
            await loadPeoplePage();
        } else {
            const err = await resp.json();
            alert('保存失败: ' + (err.detail || ''));
        }
    } catch (e) {
        alert('保存失败: ' + e.message);
    }
}

async function deletePersonChart(person, chartType) {
    const label = chartType === 'ziwei' ? '紫微斗数' : '十神';
    if (!confirm(`确认删除 ${person} 的 ${label} 命盘？此操作不可恢复。`)) return;
    const resp = await fetch(`/api/charts/${person}/${chartType}`, { method: 'DELETE' });
    const data = await resp.json();
    if (resp.ok) {
        await loadPeoplePage();
        // Also refresh the chat page's person selector
        if (typeof loadPeopleList === 'function') await loadPeopleList();
    } else {
        alert('删除失败: ' + (data.detail || ''));
    }
}

function importChartForPerson(person, displayName, chartType) {
    document.getElementById('import-display-name').value = displayName;
    document.getElementById('import-person-id').value = person;
    document.getElementById('import-raw-text').value = '';
    const resultDiv = document.getElementById('import-result');
    if (resultDiv) resultDiv.classList.add('hidden');
    // Override chart type detection: force the requested type
    window._forceChartType = chartType;
    openModal('modal-import-chart');
    window._importFromPeople = true;
}

// Patch importChartAI to respect forced chart type
const _origImportChartAI2 = importChartAI;
importChartAI = async function() {
    if (window._forceChartType) {
        // Temporarily override the chart_type sent to backend
        const origFetch = window.fetch;
        window.fetch = function(url, opts) {
            if (url === '/api/charts/import' && opts.body) {
                const body = JSON.parse(opts.body);
                if (window._forceChartType) {
                    body.chart_type = window._forceChartType;
                    opts.body = JSON.stringify(body);
                }
            }
            return origFetch.call(window, url, opts);
        };
        try {
            await _origImportChartAI2();
        } finally {
            window.fetch = origFetch;
            window._forceChartType = null;
        }
    } else {
        await _origImportChartAI2();
    }
    if (window._importFromPeople) {
        window._importFromPeople = false;
        await loadPeoplePage();
    }
};

function showImportModalFromPeople() {
    document.getElementById('import-raw-text').value = '';
    document.getElementById('import-display-name').value = '';
    document.getElementById('import-person-id').value = '';
    const resultDiv = document.getElementById('import-result');
    if (resultDiv) resultDiv.classList.add('hidden');
    openModal('modal-import-chart');
    // Override the success behavior to also refresh people page
    const origImport = importChartAI;
    // Just reuse the existing import function; it refreshes people list via loadPeopleList
    // We'll also refresh this page after
    window._importFromPeople = true;
}

// Patch the import success path to also refresh people page
const _origImportChartAI = importChartAI;
importChartAI = async function() {
    await _origImportChartAI();
    if (window._importFromPeople) {
        window._importFromPeople = false;
        await loadPeoplePage();
    }
};

async function deletePerson(person) {
    if (!confirm(`确认删除人物「${person}」及其所有命盘？此操作不可恢复！`)) return;
    const resp = await fetch(`/api/charts/${person}`, { method: 'DELETE' });
    const data = await resp.json();
    if (resp.ok) {
        await loadPeoplePage();
        if (typeof loadPeopleList === 'function') await loadPeopleList();
    } else {
        alert('删除失败: ' + (data.detail || ''));
    }
}
