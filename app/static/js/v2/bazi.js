/* ===== 子平八字 view (测测 layout) + 大运→流年→流月→流日 strips ===== */
const REL_CLS = { '合': 'he', '六合': 'he', '三合': 'he', '半合': 'he', '拱合': 'he', '暗合': 'he', '三会': 'he', '冲': 'chong', '刑': 'xing', '害': 'hai', '破': 'po', '克': 'chong' };
const SHA_JI = new Set(['羊刃', '劫煞', '亡神', '灾煞', '元辰', '六厄', '勾绞', '孤辰', '寡宿', '空亡', '血刃', '十恶大败', '阴差阳错', '童子', '大耗']);

function wx(ch, w) { return `<span class="wx-${w}">${ch}</span>`; }

function renderBazi() {
    const c = AppState.bazi; const root = document.getElementById('bazi-root');
    if (!c) { root.innerHTML = ''; return; }
    const P = c.pillars;
    const row = (label, cells, cls) => `<tr><th>${label}</th>${cells.map(x => `<td class="${cls || ''}">${x}</td>`).join('')}</tr>`;
    const hidden = p => `<div class="bz-hidden">${p.hidden.map(h => `<span>${wx(h.stem, h.wuxing)}<small>${h.shishen}</small></span>`).join('')}</div>`;
    const ss = p => {
        const lim = isMobile() ? 3 : 99;
        const shown = p.shensha.slice(0, lim).map(s => `<span class="${SHA_JI.has(s) ? 'ji' : ''}">${s}</span>`).join('');
        const more = p.shensha.length > lim ? `<span class="more" onclick="showShensha('${p.pos}')">+${p.shensha.length - lim}</span>` : '';
        return `<div class="bz-ss">${shown}${more}${p.shensha.length ? '' : '<span style="background:none;color:var(--text-muted)">—</span>'}</div>`;
    };
    const table = `<table class="bz-table">
        <thead><tr><th></th>${P.map(p => `<td>${p.pos}</td>`).join('')}</tr></thead>
        <tbody>
        ${row('干神', P.map(p => `<b>${p.stem_shishen}</b>`))}
        ${row('天干', P.map(p => `<span onclick="addContextTag({pillar:'${p.pos}',stem:'${p.stem}',shishen:'${p.stem_shishen}'})">${wx(p.stem, p.stem_wuxing)}</span>`), 'gan')}
        ${row('地支', P.map(p => `<span onclick="addContextTag({pillar:'${p.pos}',stem:'${p.branch}',shishen:'${p.branch_shishen.join('/')}'})">${wx(p.branch, p.branch_wuxing)}</span>`), 'zhi')}
        ${row('藏干', P.map(hidden))}
        ${row('支神', P.map(p => p.branch_shishen.join('、')))}
        ${row('纳音', P.map(p => p.nayin))}
        ${row('空亡', P.map(p => p.xunkong))}
        ${row('地势', P.map(p => p.dishi))}
        ${row('自坐', P.map(p => p.zizuo))}
        ${row('神煞', P.map(ss))}
        </tbody></table>`;
    const rel = [...c.relations.stems, ...c.relations.branches].map(r => `<span class="${REL_CLS[r.type] || ''}" title="${r.pillars.join('·')}">${esc(r.text)}</span>`).join('') || '<span>无</span>';
    const wxs = Object.entries(c.wuxing_status).map(([k, v]) => `<span>${wx(k, k)} ${v}</span>`).join('');
    root.innerHTML = `<div class="bz-wrap">
        <div class="bz-head"><span>${esc(c.birth.jieqi_note)}</span><span>日主 <b>${c.day_master}</b></span><span>强弱初判 <b>${c.strength.label}</b>（月令${c.strength.month_status}）</span><span>胎元 <b>${c.taiyuan}</b> 命宫 <b>${c.minggong}</b> 身宫 <b>${c.shengong}</b></span></div>
        ${table}
        <div class="bz-rel">${rel}</div>
        <div class="bz-wx">${wxs}</div>
        <div id="bz-chain" class="bz-chain"></div>
    </div>`;
}

async function loadBaziTimeline(dateStr) {
    try {
        AppState.baziTimeline = await API.get(`/api/people/${AppState.personId}/bazi/timeline?date=${dateStr}`);
    } catch (e) { toast('运限加载失败: ' + e.message, true); return; }
    renderBaziStrips();
    renderBaziChain();
}

function renderBaziStrips() {
    const t = AppState.baziTimeline; const area = document.getElementById('strip-area');
    if (!t || AppState.chart !== 'bazi') { area.innerHTML = ''; return; }
    const cur = t.date.slice(0, 10);
    const nowY = new Date().getFullYear();
    let html = `<div class="strip"><span class="strip-label">大运</span>${t.dayun_all.filter(d => d.index >= 1).map(d => `<span class="chip ${t.dayun && t.dayun.ganzhi === d.ganzhi ? 'active' : ''} ${nowY >= d.start_year && nowY <= d.end_year ? 'now' : ''}" onclick="loadBaziTimeline('${d.start_year}-07-01')">${d.ganzhi} ${d.stem_shishen}<small>${d.start_age}岁 ${d.start_year}</small></span>`).join('')}
        <span class="strip-actions"><span class="text-muted" style="font-size:.68rem;">${t.forward ? '顺' : '逆'}排 · ${esc(t.start.text)} · 起运 ${t.start.date}</span><button class="btn btn-ghost btn-sm" onclick="loadBaziTimeline('${fmtDate(new Date())}')">今天</button><button class="btn btn-accent btn-sm" onclick="askBaziLevel()">💬 问此运限</button></span></div>`;
    html += `<div class="strip"><span class="strip-label">流年</span>${t.liunian_all.map(y => `<span class="chip ${t.liunian.year === y.year ? 'active' : ''} ${y.year === nowY ? 'now' : ''}" onclick="loadBaziTimeline('${y.year}-07-01')">${y.year} ${y.ganzhi}<small>${y.age}岁 ${y.stem_shishen}</small></span>`).join('')}</div>`;
    html += `<div class="strip"><span class="strip-label">流月</span>${t.liuyue_all.map(m => `<span class="chip ${t.liuyue.ganzhi === m.ganzhi ? 'active' : ''}" onclick="loadBaziTimeline('${m.start ? nextDay(m.start) : cur}')">${m.jie} ${m.ganzhi}<small>${m.start ? m.start.slice(5) : ''} ${m.stem_shishen}</small></span>`).join('')}</div>`;
    html += `<div class="strip"><span class="strip-label">流日</span><span class="bz-day"><button class="btn btn-ghost btn-sm" onclick="shiftBaziDay(-1)">◀</button><input type="date" class="input" value="${cur}" onchange="loadBaziTimeline(this.value)"><button class="btn btn-ghost btn-sm" onclick="shiftBaziDay(1)">▶</button></span>
        <span class="chip active">${t.liuri.ganzhi}<small>${esc(t.liuri.lunar || '')} ${t.liuri.stem_shishen}</small></span></div>`;
    const sum = `${t.dayun ? '大运' + t.dayun.ganzhi : ''} · ${t.liunian.year}${t.liunian.ganzhi} · ${t.liuyue.ganzhi} · ${cur.slice(5)} ${t.liuri.ganzhi}`;
    area.innerHTML = wrapStrips(html, sum);
    if (!isMobile() || AppState.stripsOpen) scrollActiveChips();
}

function showShensha(pos) {
    const p = (AppState.bazi.pillars || []).find(x => x.pos === pos); if (!p) return;
    showInfoSheet(`${pos} ${p.ganzhi} 神煞`, `<div class="bz-ss" style="justify-content:flex-start;gap:.4rem;">${p.shensha.map(s => `<span class="${SHA_JI.has(s) ? 'ji' : ''}" style="font-size:.8rem;padding:.2rem .6rem;">${s}</span>`).join('') || '—'}</div>`);
}

function nextDay(s) { const d = new Date(s + 'T12:00:00'); d.setDate(d.getDate() + 1); return fmtDate(d); }
function shiftBaziDay(n) { const d = new Date(AppState.baziTimeline.date.slice(0, 10) + 'T12:00:00'); d.setDate(d.getDate() + n); loadBaziTimeline(fmtDate(d)); }

function renderBaziChain() {
    const t = AppState.baziTimeline; const el = document.getElementById('bz-chain'); if (!t || !el) return;
    const card = (lv, p, extra) => !p || !p.ganzhi ? '' : `<div class="bz-card cur">
        <div class="lv"><span>${lv}</span><span>${extra || ''}</span></div>
        <div class="gz">${wx(p.stem, p.stem_wuxing)}${p.branch}</div>
        <div class="ss">干 <b>${p.stem_shishen}</b> · 支 ${p.hidden.map(h => `${h.stem}${h.shishen}`).join(' ')}</div>
        <div class="ss">地势 ${p.dishi} · 自坐 ${p.zizuo} · 空亡 ${p.xunkong}</div>
        <div class="bz-ss">${p.shensha.map(s => `<span class="${SHA_JI.has(s) ? 'ji' : ''}">${s}</span>`).join('')}</div>
        <button class="btn btn-ghost btn-sm" onclick="addContextTag({level:'${lv} ${p.ganzhi}'}, {open:true})">💬 问 AI</button></div>`;
    el.innerHTML = card('大运', t.dayun, t.dayun ? `${t.dayun.start_age}-${t.dayun.end_age}岁 ${t.dayun.start_year}-${t.dayun.end_year}` : '')
        + card('流年', t.liunian, `${t.liunian.year} ${t.liunian.age}岁`)
        + card('流月', t.liuyue, t.liuyue.jie ? `${t.liuyue.jie}起` : '')
        + card('流日', t.liuri, t.liuri.date)
        + card('流时', t.liushi, (t.liushi.hour_branch || '') + '时');
}

function askBaziLevel() { const vc = viewContext(); if (vc.level) addContextTag({ level: vc.level }, { open: true }); }
