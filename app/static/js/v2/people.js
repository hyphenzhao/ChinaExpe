/* ===== People list + person form ===== */
const CITIES = [
    ['北京', 116.40], ['上海', 121.47], ['广州', 113.26], ['深圳', 114.06], ['杭州', 120.15], ['南京', 118.80], ['苏州', 120.62],
    ['武汉', 114.31], ['成都', 104.07], ['重庆', 106.55], ['西安', 108.94], ['郑州', 113.63], ['济南', 117.00], ['青岛', 120.38],
    ['天津', 117.20], ['沈阳', 123.43], ['哈尔滨', 126.64], ['长沙', 112.94], ['合肥', 117.23], ['福州', 119.30], ['厦门', 118.09],
    ['昆明', 102.71], ['贵阳', 106.63], ['南宁', 108.37], ['兰州', 103.83], ['乌鲁木齐', 87.62], ['拉萨', 91.11], ['台北', 121.56], ['香港', 114.17],
];
const HOURS = ['早子(00-01)', '丑(01-03)', '寅(03-05)', '卯(05-07)', '辰(07-09)', '巳(09-11)', '午(11-13)', '未(13-15)', '申(15-17)', '酉(17-19)', '戌(19-21)', '亥(21-23)', '晚子(23-24)'];
let _schools = null;
let _editingId = null;

async function loadPeople() {
    try { AppState.people = await API.get('/api/people'); } catch (e) { AppState.people = []; toast(e.message, true); }
    renderPeople();
}

function renderPeople() {
    const el = document.getElementById('people-list');
    if (!AppState.people.length) { el.innerHTML = '<div class="text-muted" style="font-size:.75rem;padding:.5rem;">还没有人物，点「新建」录入出生信息</div>'; return; }
    el.innerHTML = AppState.people.map(p => `
        <div class="person-item ${p.gender === '女' ? 'female' : ''} ${p.id === AppState.personId ? 'active' : ''}" onclick="selectPerson('${p.id}')">
            <div class="person-avatar">${esc(p.display_name.slice(0, 1))}</div>
            <div class="person-meta">
                <div class="person-name">${esc(p.display_name)} <span class="text-muted" style="font-weight:400;font-size:.65rem;">${esc(p.id)}</span></div>
                <div class="person-sub">${esc(p.yinyang_gender || p.gender)} · ${esc(p.birth_solar)} · ${esc(p.bureau || '')}</div>
            </div>
        </div>`).join('');
}

async function selectPerson(pid, opts = {}) {
    if (!pid) return;
    AppState.personId = pid;
    AppState.selectedPalace = null;
    AppState.level = { decadal: null, yearly: null, monthly: null, daily: null, hourly: null };
    AppState.levelData = { decadal: null, yearly: null, monthly: null, daily: null, hourly: null };
    AppState.ziwei = null; AppState.bazi = null; AppState.baziTimeline = null;
    renderPeople();
    try { AppState.person = await API.get(`/api/people/${pid}`); } catch (e) { toast(e.message, true); return; }
    const t = document.getElementById('person-title');
    t.textContent = `${AppState.person.display_name}`;
    if (!opts.keepSession) {
        // switch to this person's latest session (or none)
        const s = AppState.sessions.find(x => x.person === pid);
        if (s) await openSession(s.id, { silent: true }); else clearSession();
    }
    renderSessions();
    await switchChart(AppState.chart, true);
    if (isMobile()) togglePane('left', true);
    setHash();
}

async function switchChart(which, force) {
    if (!force && which === AppState.chart && (which === 'ziwei' ? AppState.ziwei : AppState.bazi)) return;
    AppState.chart = which;
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.toggle('active', b.dataset.chart === which));
    document.getElementById('layer-toggles').style.display = which === 'ziwei' ? '' : 'none';
    const empty = document.getElementById('chart-empty');
    const zr = document.getElementById('ziwei-root'), br = document.getElementById('bazi-root');
    if (!AppState.personId) { empty.classList.remove('hidden'); zr.classList.add('hidden'); br.classList.add('hidden'); document.getElementById('strip-area').innerHTML = ''; return; }
    empty.classList.add('hidden');
    zr.classList.toggle('hidden', which !== 'ziwei');
    br.classList.toggle('hidden', which !== 'bazi');
    try {
        if (which === 'ziwei') {
            if (!AppState.ziwei) AppState.ziwei = await API.get(`/api/people/${AppState.personId}/ziwei`);
            renderZiwei();
            await initHoroscopeStrip();
        } else {
            if (!AppState.bazi) AppState.bazi = await API.get(`/api/people/${AppState.personId}/bazi`);
            renderBazi();
            await loadBaziTimeline(AppState.baziTimeline ? AppState.baziTimeline.date.slice(0, 10) : fmtDate(new Date()));
        }
    } catch (e) { toast('加载命盘失败: ' + e.message, true); }
    setHash();
}

/* ---------- form ---------- */
async function openPersonForm(pid) {
    _editingId = pid || null;
    if (!_schools) { try { _schools = await API.get('/api/people/meta/schools'); } catch (_) { _schools = { ziwei: {}, bazi: {} }; } }
    const citySel = document.getElementById('pf-city');
    if (citySel.options.length <= 1) CITIES.forEach(([n, lon]) => citySel.insertAdjacentHTML('beforeend', `<option value="${lon}">${n} ${lon}</option>`));
    const hourSel = document.getElementById('pf-hour');
    if (hourSel.options.length <= 1) HOURS.forEach((h, i) => hourSel.insertAdjacentHTML('beforeend', `<option value="${i}">${h}</option>`));
    // settings selects
    const sc = document.getElementById('pf-settings');
    sc.innerHTML = '';
    for (const sys of ['ziwei', 'bazi']) {
        for (const [key, def] of Object.entries(_schools[sys] || {})) {
            const opts = Object.entries(def.options).map(([v, l]) => `<option value="${esc(v)}">${esc(l)}</option>`).join('');
            sc.insertAdjacentHTML('beforeend', `<div class="form-group"><label>${sys === 'ziwei' ? '紫微' : '八字'} · ${esc(def.label)}</label><select class="input pf-setting" data-sys="${sys}" data-key="${key}">${opts}</select></div>`);
        }
    }
    document.getElementById('pf-result').className = 'test-result hidden';
    document.getElementById('pf-delete').style.display = pid ? '' : 'none';
    document.getElementById('person-form-title').textContent = pid ? '编辑人物' : '新建人物';
    if (pid) {
        const p = AppState.person && AppState.person.id === pid ? AppState.person : await API.get(`/api/people/${pid}`);
        document.getElementById('pf-name').value = p.display_name;
        document.getElementById('pf-id').value = p.id; document.getElementById('pf-id').disabled = true;
        document.getElementById('pf-gender').value = p.gender;
        document.getElementById('pf-date').value = p.birth.solar.slice(0, 10);
        document.getElementById('pf-time').value = p.birth.solar.slice(11, 16);
        document.getElementById('pf-lon').value = p.birth.longitude;
        document.getElementById('pf-tst').value = p.birth.use_true_solar_time ? '1' : '0';
        document.getElementById('pf-hour').value = p.birth.hour_override == null ? '' : String(p.birth.hour_override);
        document.getElementById('pf-place').value = p.birth.place || '';
        document.querySelectorAll('.pf-setting').forEach(s => { const v = (p.settings[s.dataset.sys] || {})[s.dataset.key]; if (v != null) s.value = String(v); });
    } else {
        ['pf-name', 'pf-id', 'pf-place'].forEach(id => document.getElementById(id).value = '');
        document.getElementById('pf-id').disabled = false;
        document.getElementById('pf-gender').value = '男';
        document.getElementById('pf-date').value = '1990-01-01'; document.getElementById('pf-time').value = '12:00';
        document.getElementById('pf-lon').value = 120; document.getElementById('pf-tst').value = '1'; document.getElementById('pf-hour').value = '';
    }
    openModal('modal-person');
}

function pickCity() {
    const v = document.getElementById('pf-city').value;
    if (v) document.getElementById('pf-lon').value = v;
}

/* Re-export the AI-readable bundle for the current person (运限按今天重算) */
async function exportPersonJson(pid) {
    const id = pid || AppState.personId;
    if (!id) { toast('请先选择人物', true); return; }
    try {
        const r = await API.post(`/api/people/${id}/export`, {});
        toast(`已导出 ${r.json.split(/[\\/]/).pop()} · ${(r.bytes / 1024).toFixed(0)} KB · 运限 ${r.as_of}`);
    } catch (e) { toast('导出失败: ' + e.message, true); }
}

async function exportAllJson() {
    try {
        const r = await API.post('/api/people/export-all', {});
        toast(`已导出 ${r.count} 人到 data/exports`);
    } catch (e) { toast('导出失败: ' + e.message, true); }
}

async function savePersonForm() {
    const out = document.getElementById('pf-result');
    const settings = { ziwei: {}, bazi: {} };
    document.querySelectorAll('.pf-setting').forEach(s => { settings[s.dataset.sys][s.dataset.key] = s.dataset.key === 'yun_sect' ? parseInt(s.value) : s.value; });
    const hour = document.getElementById('pf-hour').value;
    const body = {
        display_name: document.getElementById('pf-name').value.trim(),
        gender: document.getElementById('pf-gender').value,
        birth: {
            solar: `${document.getElementById('pf-date').value} ${document.getElementById('pf-time').value || '12:00'}`,
            longitude: parseFloat(document.getElementById('pf-lon').value) || 120,
            place: document.getElementById('pf-place').value.trim(),
            use_true_solar_time: document.getElementById('pf-tst').value === '1',
            hour_override: hour === '' ? null : parseInt(hour),
        },
        settings,
    };
    if (!body.display_name) { out.className = 'test-result error'; out.textContent = '请填写姓名'; return; }
    try {
        let p;
        if (_editingId) p = await API.put(`/api/people/${_editingId}`, body);
        else { const id = document.getElementById('pf-id').value.trim(); if (id) body.id = id; p = await API.post('/api/people', body); }
        closeModal('modal-person');
        await loadPeople();
        AppState.ziwei = null; AppState.bazi = null; AppState.baziTimeline = null;
        await selectPerson(p.id, { keepSession: true });
        toast(`已保存并重新排盘，命盘已导出 data/exports/${p.id}.json`);
    } catch (e) { out.className = 'test-result error'; out.textContent = e.message; }
}

async function deletePersonConfirm() {
    if (!_editingId) return;
    if (!confirm(`确定删除人物 ${_editingId} ？对话记录会保留。`)) return;
    try {
        await API.del(`/api/people/${_editingId}`);
        closeModal('modal-person');
        AppState.personId = null; AppState.person = null; AppState.ziwei = null; AppState.bazi = null;
        document.getElementById('person-title').textContent = '未选择人物';
        await loadPeople();
        if (AppState.people.length) await selectPerson(AppState.people[0].id); else switchChart('ziwei', true);
    } catch (e) { toast(e.message, true); }
}
