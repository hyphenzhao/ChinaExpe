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
    const A = c.analysis;
    const stLabel = A ? `${A.strength.label} ${A.strength.same_pct}%${A.strength.border ? '（临界）' : ''}` : c.strength.label;
    root.innerHTML = `<div class="bz-wrap">
        <div class="bz-pv">${previewBar()}</div>
        <div class="bz-head"><span>${esc(c.birth.jieqi_note)}</span><span>日主 <b>${c.day_master}</b></span><span>身强弱 <b>${stLabel}</b>（月令${c.strength.month_status}）</span><span>胎元 <b>${c.taiyuan}</b> 命宫 <b>${c.minggong}</b> 身宫 <b>${c.shengong}</b></span></div>
        ${table}
        <div class="bz-rel">${rel}</div>
        <div class="bz-wx">${wxs}</div>
        ${renderBaziAnalysis(A)}
        <div id="bz-chain" class="bz-chain"></div>
    </div>`;
}

/* ---------- 命局分析：身强弱 / 五行 / 十神占比 / 格局候选 / 喜忌用神（纯代码结果） ---------- */
const WX_OF_GROUP_ROLE = { '用神': 'yong', '喜神': 'xi', '闲神': 'xian', '仇神': 'chou', '忌神': 'ji' };

function _bzaBar(pct, cls) {
    const w = Math.max(0, Math.min(100, pct || 0));
    return `<span class="bza-bar"><i class="${cls || ''}" style="width:${w}%"></i></span><span class="bza-num">${(pct || 0).toFixed(1)}%</span>`;
}

function renderBaziAnalysis(A) {
    if (!A) return '';
    const st = A.strength, sh = A.shishen, gj = A.geju, ys = A.yongshen;
    const flag = (on, t) => `<span class="bza-flag ${on ? 'on' : ''}">${on ? '✓' : '·'} ${t}</span>`;
    const strength = `<div class="bza-block"><h4>身强身弱</h4>
        <div class="bza-row"><b>${st.label}</b>${st.special ? `<span class="bza-tag warn">${st.special}</span>` : ''}${st.border ? '<span class="bza-tag">临界</span>' : ''}</div>
        <div class="bza-row"><span class="bza-k">同类占比</span>${_bzaBar(st.same_pct, 'same')}</div>
        <div class="bza-row">${flag(st.de_ling, '得令')}${flag(st.de_di, '得地')}${flag(st.de_shi, '得势')}</div>
        ${Object.entries(st.element_pct).map(([e, p]) => `<div class="bza-row"><span class="bza-k">${wx(e, e)}</span>${_bzaBar(p, 'wxbar-' + e)}</div>`).join('')}
    </div>`;
    const shishen = `<div class="bza-block"><h4>十神占比</h4>
        ${sh.groups.map(g => `<div class="bza-row"><span class="bza-k">${g.group}</span>${_bzaBar(g.pct)}</div>`).join('')}
        <div class="bza-sub">${sh.items.map(r => `<span>${r.shishen} ${r.pct}%</span>`).join('')}</div>
    </div>`;
    const cand = gj.candidates.map(x => `<div class="bza-row" title="${esc(x.basis.join('；') + '；' + x.flags.join('、'))}"><span class="bza-k wide">${x.name}</span>${_bzaBar(x.pct, 'geju')}</div>`).join('');
    const special = gj.special.length ? `<div class="bza-sub">特殊格候选：${gj.special.map(s => `<span class="bza-tag warn" title="${esc(Object.keys(s.gates).join('、'))}">${s.name} ${s.pct}%</span>`).join('')}</div>` : '';
    const geju = `<div class="bza-block"><h4>格局候选</h4>
        ${gj.primary ? `<div class="bza-row"><span class="bza-k">取格</span><b>${gj.primary.name}</b><small class="text-muted">${esc(gj.primary.basis)}${gj.primary.note ? '；' + esc(gj.primary.note) : ''}</small></div>` : ''}
        ${cand}${special}
        ${gj.observations.length ? `<div class="bza-sub">相关合冲：${gj.observations.map(esc).join('、')}</div>` : ''}
    </div>`;
    const yong = `<div class="bza-block"><h4>喜忌用神</h4>
        <div class="bza-roles">${ys.ranking.map(r => `<details class="bza-role ${WX_OF_GROUP_ROLE[r.role]}"><summary>${r.role} ${wx(r.element, r.element)}<small>${r.score > 0 ? '+' : ''}${r.score}</small></summary>
            <div>${r.reasons.map(x => `<div>${x.layer} ${x.delta > 0 ? '+' : ''}${x.delta}：${esc(x.text)}</div>`).join('') || '无加减分'}</div></details>`).join('')}</div>
        <div class="bza-sub">方法：${esc(ys.method)}</div>
    </div>`;
    const open = isMobile() ? '' : 'open';
    return `<details class="bz-analysis" ${open}><summary>命局分析 <small class="text-muted">（代码计算 · ${A.version}）</small></summary>
        <div class="bza-grid">${strength}${shishen}${geju}${yong}</div>
        <div class="bza-foot">口径说明：天干各 100，藏干按本中余气 60/30/10 分配，乘月令系数（本月：${esc(st.coef_source)}）。
            测测等 App 算法未公开，数值不会逐位一致；格局只列成格方向，不判破格；喜忌排序为本系统口径，仅供参考。</div>
    </details>`;
}

async function loadBaziTimeline(dateStr) {
    if (AppState.preview) { renderBaziStrips(); return; }
    try {
        AppState.baziTimeline = await API.get(`/api/people/${AppState.personId}/bazi/timeline?date=${dateStr}`);
    } catch (e) { toast('运限加载失败: ' + e.message, true); return; }
    renderBaziStrips();
    renderBaziChain();
}

function renderBaziStrips() {
    const t = AppState.baziTimeline; const area = document.getElementById('strip-area');
    if (AppState.preview && AppState.chart === 'bazi') { area.innerHTML = previewStripNote(); return; }
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
