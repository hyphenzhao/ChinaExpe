/* ===== Layers (四化 / 三合 / 飞星 / 小星 / 虚线) + horoscope strips (大限→流年→流月→流日→流时) ===== */
const LEVELS = ['decadal', 'yearly', 'monthly', 'daily', 'hourly'];
const LEVEL_CN = { decadal: '大限', yearly: '流年', monthly: '流月', daily: '流日', hourly: '流时' };
const LEVEL_PREFIX = { decadal: '限', yearly: '年', monthly: '月', daily: '日', hourly: '时' };

function toggleLayer(name) {
    AppState.layers[name] = !AppState.layers[name];
    document.querySelectorAll('.layer-btn').forEach(b => b.classList.toggle('active', !!AppState.layers[b.dataset.layer]));
    if (name === 'sihua' || name === 'minor') renderZiwei(); else { applyLayers(); renderCenter(); }
}

function applyLayers() {
    const z = AppState.ziwei; if (!z) return;
    document.querySelectorAll('.layer-btn').forEach(b => b.classList.toggle('active', !!AppState.layers[b.dataset.layer]));
    const sel = AppState.selectedPalace;
    z.palaces.forEach(p => {
        const el = document.getElementById('palace-' + p.index); if (!el) return;
        el.classList.toggle('selected', sel === p.index);
        el.classList.remove('sanhe-opp', 'sanhe-tri', 'dim');
        if (AppState.layers.sanhe && sel != null) {
            if (p.index === (sel + 6) % 12) el.classList.add('sanhe-opp');
            else if (p.index === (sel + 4) % 12 || p.index === (sel + 8) % 12) el.classList.add('sanhe-tri');
            else if (p.index !== sel) el.classList.add('dim');
        }
    });
    applyLevelOverlays();
    drawFeixing();
}

/* ---------- 飞星 SVG ---------- */
const HUA_COLOR = { '禄': '#34d399', '权': '#fbbf24', '科': '#60a5fa', '忌': '#f87171' };
function drawFeixing() {
    const svg = document.getElementById('zw-svg'); if (!svg) return;
    svg.innerHTML = '';
    const z = AppState.ziwei; const sel = AppState.selectedPalace;
    if (!z || sel == null) return;
    const grid = document.getElementById('zw-grid');
    const gr = grid.getBoundingClientRect();
    svg.setAttribute('viewBox', `0 0 ${gr.width} ${gr.height}`);
    const rect = i => { const r = document.getElementById('palace-' + i).getBoundingClientRect(); return { l: r.left - gr.left, t: r.top - gr.top, r: r.right - gr.left, b: r.bottom - gr.top }; };
    const center = i => { const q = rect(i); return [(q.l + q.r) / 2, (q.t + q.b) / 2]; };
    // point where the segment centre(a)->centre(b) leaves palace a's rectangle (2px outside the border)
    const edge = (a, b) => {
        const q = rect(a); const [x0, y0] = center(a); const [x1, y1] = center(b);
        const dx = x1 - x0, dy = y1 - y0; let t = 1;
        if (dx > 0) t = Math.min(t, (q.r - x0) / dx); else if (dx < 0) t = Math.min(t, (q.l - x0) / dx);
        if (dy > 0) t = Math.min(t, (q.b - y0) / dy); else if (dy < 0) t = Math.min(t, (q.t - y0) / dy);
        const len = Math.hypot(dx, dy) || 1;
        return [x0 + dx * t + dx / len * 2, y0 + dy * t + dy / len * 2];
    };
    // anchor on the palace edge that faces the central block, so links run through the
    // centre area only and never cross another palace (cf. 文墨天机)
    const anchor = i => {
        const q = rect(i); const [c, r] = GRID_POS[z.palaces[i].branch];
        const top = r === 1, bottom = r === 4, left = c === 1, right = c === 4;
        if (top && left) return [q.r, q.b];
        if (top && right) return [q.l, q.b];
        if (bottom && left) return [q.r, q.t];
        if (bottom && right) return [q.l, q.t];
        if (top) return [(q.l + q.r) / 2, q.b];
        if (bottom) return [(q.l + q.r) / 2, q.t];
        if (left) return [q.r, (q.t + q.b) / 2];
        return [q.l, (q.t + q.b) / 2];
    };
    const dashed = (a, b, cls) => { const [x1, y1] = anchor(a), [x2, y2] = anchor(b); return `<line class="${cls}" x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}"/><circle class="link-dot" cx="${x1}" cy="${y1}" r="2.5"/><circle class="link-dot" cx="${x2}" cy="${y2}" r="2.5"/>`; };
    let defs = '';
    for (const [h, c] of Object.entries(HUA_COLOR)) defs += `<marker id="arr-${HUA_CLS[h]}" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8 z" fill="${c}"/></marker>`;
    let body = `<defs>${defs}</defs>`;
    const [x0, y0] = center(sel);
    // 三方四正: dashed links — 本宫↔对宫, and the 三合 triangle (本宫, +4, +8)
    const opp = (sel + 6) % 12, t1 = (sel + 4) % 12, t2 = (sel + 8) % 12;
    if (AppState.layers.links) body += dashed(sel, opp, 'link-opp') + dashed(sel, t1, 'link-tri') + dashed(sel, t2, 'link-tri') + dashed(t1, t2, 'link-tri');
    if (!AppState.layers.feixing) { svg.innerHTML = body; return; }
    const f = z.fly[sel];
    f.targets.forEach((t, k) => {
        if (t.to_index == null) return;
        const c = HUA_COLOR[t.hua];
        if (t.self) {
            body += `<circle cx="${x0 + 30 + k * 6}" cy="${y0 - 30}" r="10" fill="none" stroke="${c}" stroke-width="2" stroke-dasharray="3 2"/><text x="${x0 + 30 + k * 6}" y="${y0 - 26}" font-size="10" fill="${c}" text-anchor="middle">${t.hua}</text>`;
            return;
        }
        const [x1, y1] = center(t.to_index);
        const dx = x1 - x0, dy = y1 - y0, len = Math.hypot(dx, dy) || 1;
        const nx = -dy / len, ny = dx / len;               // normal for curvature
        const off = (k - 1.5) * 22;                        // spread the 4 arrows
        const cx = (x0 + x1) / 2 + nx * (40 + off), cy = (y0 + y1) / 2 + ny * (40 + off);
        const ex = x1 - dx / len * 34, ey = y1 - dy / len * 34;
        body += `<path d="M${x0},${y0} Q${cx},${cy} ${ex},${ey}" fill="none" stroke="${c}" stroke-width="2.2" opacity=".9" marker-end="url(#arr-${HUA_CLS[t.hua]})"/>
                 <text x="${cx}" y="${cy}" font-size="11" font-weight="700" fill="${c}" text-anchor="middle" style="paint-order:stroke;stroke:#0a0e1a;stroke-width:3px;">${t.hua}·${t.star}</text>`;
    });
    svg.innerHTML = body;
}

/* ---------- level overlays on the board ---------- */
function applyLevelOverlays() {
    const z = AppState.ziwei; if (!z) return;
    document.querySelectorAll('.hua.lv').forEach(e => e.remove());
    document.querySelectorAll('.p-flow').forEach(e => e.innerHTML = '');
    document.querySelectorAll('.p-lvtag').forEach(e => e.innerHTML = '');
    for (const lv of LEVELS) {
        const d = AppState.levelData[lv]; if (!d) continue;
        // level 命宫 tag
        const tag = document.getElementById('lvtag-' + d.index);
        if (tag) tag.insertAdjacentHTML('beforeend', `<span class="lvc-${lv}" title="${LEVEL_CN[lv]}命宫">${LEVEL_PREFIX[lv]}命</span>`);
        if (lv === 'yearly' && d.age_palace) {
            const t2 = document.getElementById('lvtag-' + d.age_palace.index);
            if (t2) t2.insertAdjacentHTML('beforeend', `<span class="lvc-age" title="小限">小限</span>`);
        }
        // 四化 badges on target stars
        for (const h of d.hua) {
            if (h.palace_index == null) continue;
            const el = document.querySelector(`#palace-${h.palace_index} .star[data-star="${h.star}"]`);
            if (el) el.insertAdjacentHTML('beforeend', `<i class="hua ${HUA_CLS[h.hua]} lv lv-${lv}" title="${LEVEL_CN[lv]}${d.ganzhi} ${h.star}化${h.hua}">${LEVEL_PREFIX[lv]}${h.hua}</i>`);
        }
        // 流曜
        if (lv === 'decadal' || lv === 'yearly') {
            for (const s of d.stars || []) {
                const fl = document.getElementById('flow-' + s.palace_index);
                if (fl) fl.insertAdjacentHTML('beforeend', `<span class="fs">${s.name}</span>`);
            }
        }
    }
}

/* ---------- strips ---------- */
async function initHoroscopeStrip() {
    const z = AppState.ziwei; if (!z) return;
    // default: today's chain
    if (!AppState.levelData.decadal) await selectToday();
    else renderStrips();
}

async function selectToday() {
    const pid = AppState.personId;
    try {
        const d = await API.get(`/api/people/${pid}/ziwei/horoscope?date=${fmtDate(new Date())}`);
        AppState.levelData = { decadal: d.decadal, yearly: d.yearly, monthly: d.monthly, daily: d.daily, hourly: null };
        AppState.level = { decadal: decadalIndexOf(d.decadal), yearly: d.yearly.year, monthly: { year: d.monthly.year, month: d.monthly.lunar_month, leap: d.monthly.is_leap }, daily: d.daily.solar_date, hourly: null };
        AppState.lists.yearly = await API.get(`/api/people/${pid}/ziwei/yearly-list?decadal=${AppState.level.decadal}`);
        AppState.lists.monthly = await API.get(`/api/people/${pid}/ziwei/monthly-list?year=${d.yearly.year}`);
        AppState.lists.daily = await API.get(`/api/people/${pid}/ziwei/daily-list?year=${d.monthly.year}&month=${d.monthly.lunar_month}&leap=${d.monthly.is_leap}`);
        AppState.lists.hourly = [];
    } catch (e) { toast('运限加载失败: ' + e.message, true); }
    renderStrips(); applyLevelOverlays(); renderCenter();
}

function decadalIndexOf(d) {
    const list = AppState.ziwei.decadals;
    const k = list.findIndex(x => x.ganzhi === d.ganzhi && x.start_age === d.start_age);
    return k >= 0 ? k : null;
}

function clearLevels(from) {
    const idx = LEVELS.indexOf(from);
    for (const lv of LEVELS.slice(idx)) { AppState.level[lv] = null; AppState.levelData[lv] = null; }
    for (const lv of LEVELS.slice(idx + 1)) AppState.lists[lv] = [];
}

async function pickDecadal(k) {
    if (AppState.level.decadal === k) { clearLevels('decadal'); renderStrips(); applyLevelOverlays(); renderCenter(); return; }
    clearLevels('decadal');
    AppState.level.decadal = k; AppState.levelData.decadal = AppState.ziwei.decadals[k];
    try { AppState.lists.yearly = await API.get(`/api/people/${AppState.personId}/ziwei/yearly-list?decadal=${k}`); } catch (e) { toast(e.message, true); }
    renderStrips(); applyLevelOverlays(); renderCenter();
}

async function pickYearly(year) {
    if (AppState.level.yearly === year) { clearLevels('yearly'); renderStrips(); applyLevelOverlays(); renderCenter(); return; }
    clearLevels('yearly');
    const y = AppState.lists.yearly.find(x => x.year === year);
    AppState.level.yearly = year; AppState.levelData.yearly = y;
    try { AppState.lists.monthly = await API.get(`/api/people/${AppState.personId}/ziwei/monthly-list?year=${year}`); } catch (e) { toast(e.message, true); }
    renderStrips(); applyLevelOverlays(); renderCenter();
}

async function pickMonthly(i) {
    const m = AppState.lists.monthly[i];
    const same = AppState.level.monthly && AppState.level.monthly.month === m.lunar_month && AppState.level.monthly.leap === m.is_leap;
    if (same) { clearLevels('monthly'); renderStrips(); applyLevelOverlays(); renderCenter(); return; }
    clearLevels('monthly');
    AppState.level.monthly = { year: m.year, month: m.lunar_month, leap: m.is_leap }; AppState.levelData.monthly = m;
    try { AppState.lists.daily = await API.get(`/api/people/${AppState.personId}/ziwei/daily-list?year=${m.year}&month=${m.lunar_month}&leap=${m.is_leap}`); } catch (e) { toast(e.message, true); }
    renderStrips(); applyLevelOverlays(); renderCenter();
}

async function pickDaily(i) {
    const d = AppState.lists.daily[i];
    if (AppState.level.daily === d.solar_date) { clearLevels('daily'); renderStrips(); applyLevelOverlays(); renderCenter(); return; }
    clearLevels('daily');
    AppState.level.daily = d.solar_date; AppState.levelData.daily = d;
    try { AppState.lists.hourly = await API.get(`/api/people/${AppState.personId}/ziwei/hourly-list?date=${d.solar_date}`); } catch (e) { toast(e.message, true); }
    renderStrips(); applyLevelOverlays(); renderCenter();
}

function pickHourly(i) {
    const h = AppState.lists.hourly[i];
    if (AppState.level.hourly === i) { clearLevels('hourly'); } else { AppState.level.hourly = i; AppState.levelData.hourly = h; }
    renderStrips(); applyLevelOverlays(); renderCenter();
}

function askLevel() {
    const vc = viewContext();
    if (vc.level) addContextTag({ level: vc.level }, { open: true });
}

function renderStrips() {
    const z = AppState.ziwei; const area = document.getElementById('strip-area');
    if (!z || AppState.chart !== 'ziwei') { area.innerHTML = ''; return; }
    const nowYear = new Date().getFullYear();
    const L = AppState.level;
    let html = `<div class="strip"><span class="strip-label">大限</span>${z.decadals.map((d, k) => `<span class="chip ${L.decadal === k ? 'active' : ''} ${nowYear >= d.start_year && nowYear <= d.end_year ? 'now' : ''}" onclick="pickDecadal(${k})">${d.ganzhi} ${d.palace_name.replace('宫', '')}<small>${d.start_age}-${d.end_age}岁 ${d.start_year}</small></span>`).join('')}
        <span class="strip-actions"><button class="btn btn-ghost btn-sm" onclick="selectToday()">今天</button><button class="btn btn-ghost btn-sm" onclick="clearLevels('decadal'); renderStrips(); applyLevelOverlays(); renderCenter();">清除</button><button class="btn btn-accent btn-sm" onclick="askLevel()">💬 问此运限</button></span></div>`;
    if (L.decadal != null && AppState.lists.yearly.length) {
        html += `<div class="strip"><span class="strip-label">流年</span>${AppState.lists.yearly.map(y => `<span class="chip ${L.yearly === y.year ? 'active' : ''} ${y.year === nowYear ? 'now' : ''}" onclick="pickYearly(${y.year})">${y.year} ${y.ganzhi}<small>${y.age}岁 ${y.palace_name.replace('宫', '')}</small></span>`).join('')}</div>`;
    }
    if (L.yearly != null && AppState.lists.monthly.length) {
        html += `<div class="strip"><span class="strip-label">流月</span>${AppState.lists.monthly.map((m, i) => `<span class="chip ${L.monthly && L.monthly.month === m.lunar_month && L.monthly.leap === m.is_leap ? 'active' : ''}" onclick="pickMonthly(${i})">${m.month_name} ${m.ganzhi}<small>${m.palace_name.replace('宫', '')}</small></span>`).join('')}</div>`;
    }
    if (L.monthly && AppState.lists.daily.length) {
        html += `<div class="strip"><span class="strip-label">流日</span>${AppState.lists.daily.map((d, i) => `<span class="chip ${L.daily === d.solar_date ? 'active' : ''} ${d.solar_date === fmtDate(new Date()) ? 'now' : ''}" onclick="pickDaily(${i})">${d.lunar_text.slice(-2)} ${d.ganzhi}<small>${d.solar_date.slice(5)} ${d.palace_name.replace('宫', '')}</small></span>`).join('')}</div>`;
    }
    if (L.daily && AppState.lists.hourly.length) {
        html += `<div class="strip"><span class="strip-label">流时</span>${AppState.lists.hourly.map((h, i) => `<span class="chip ${L.hourly === i ? 'active' : ''}" onclick="pickHourly(${i})">${h.hour_branch}时 ${h.ganzhi}<small>${h.palace_name.replace('宫', '')}</small></span>`).join('')}</div>`;
    }
    const Ld = AppState.levelData;
    const sum = [Ld.decadal && `大限${Ld.decadal.ganzhi}`, Ld.yearly && `${Ld.yearly.year}${Ld.yearly.ganzhi}`, Ld.monthly && (Ld.monthly.month_name || ''), Ld.daily && Ld.daily.solar_date.slice(5)].filter(Boolean).join(' · ') || '点此选择大限/流年/流月/流日';
    area.innerHTML = wrapStrips(html, sum);
    if (!isMobile() || AppState.stripsOpen) scrollActiveChips();
}
