/* ===== 紫微斗数 board rendering ===== */
const GRID_POS = { '巳': [1, 1], '午': [2, 1], '未': [3, 1], '申': [4, 1], '辰': [1, 2], '酉': [4, 2], '卯': [1, 3], '戌': [4, 3], '寅': [1, 4], '丑': [2, 4], '子': [3, 4], '亥': [4, 4] };
const SHA_MINOR = new Set(['擎羊', '陀罗', '火星', '铃星', '地空', '地劫']);
const HUA_CLS = { '禄': 'lu', '权': 'quan', '科': 'ke', '忌': 'ji' };

function huaBadge(h, kind, label) {
    return `<i class="hua ${HUA_CLS[h]} ${kind}" title="${kind === 'birth' ? '生年' : kind === 'self out' ? '离心自化' : '向心自化'}化${h}">${label}</i>`;
}

function starHtml(s, pi) {
    const cls = ['star', s.category, SHA_MINOR.has(s.name) ? 'sha' : ''].join(' ');
    let h = `<span class="${cls}" data-star="${esc(s.name)}" data-palace="${pi}" onclick="onStarClick(event, ${pi}, '${esc(s.name)}')"><span class="sn">${esc(s.name)}</span>`;
    if (s.brightness) h += `<sup class="b b-${s.brightness}">${s.brightness}</sup>`;
    if (AppState.layers.sihua) {
        if (s.birth_hua) h += huaBadge(s.birth_hua, 'birth', s.birth_hua);
        if (s.self_hua_out) h += huaBadge(s.self_hua_out, 'self out', '↓' + s.self_hua_out);
        if (s.self_hua_in) h += huaBadge(s.self_hua_in, 'self in', '↑' + s.self_hua_in);
    }
    return h + '</span>';
}

function renderZiwei() {
    const z = AppState.ziwei;
    const root = document.getElementById('ziwei-root');
    if (!z) { root.innerHTML = ''; return; }
    const cells = z.palaces.map(p => {
        const [c, r] = GRID_POS[p.branch];
        const major = p.stars.filter(s => s.category === 'major');
        const minor = p.stars.filter(s => s.category === 'minor');
        const adj = p.stars.filter(s => s.category === 'adjective');
        const badges = (p.is_laiyin ? '<span class="p-badge laiyin" title="来因宫">来因</span>' : '') + (p.is_body ? '<span class="p-badge body" title="身宫">身宫</span>' : '');
        const nb = (p.is_laiyin ? 1 : 0) + (p.is_body ? 1 : 0);
        return `<div class="palace ${p.is_body ? 'body' : ''} ${p.is_laiyin ? 'laiyin' : ''} ${nb ? 'has-badge-' + nb : ''}" id="palace-${p.index}" data-index="${p.index}" style="grid-column:${c};grid-row:${r};" onclick="onPalaceClick(${p.index})">
            ${nb ? `<div class="p-badges">${badges}</div>` : ''}
            <div class="p-stars">
                <div class="p-major">${major.map(s => starHtml(s, p.index)).join('') || '<span class="star major" style="color:var(--text-muted);font-weight:400;font-size:.75rem;">空宫</span>'}</div>
                <div class="p-minor">${minor.map(s => starHtml(s, p.index)).join('')}</div>
                <div class="p-adj" style="${AppState.layers.minor ? '' : 'display:none'}">${adj.map(s => starHtml(s, p.index)).join('')}</div>
                <div class="p-flow" id="flow-${p.index}"></div>
            </div>
            <div class="p-foot">
                <div class="p-shensha"><span>${esc(p.changsheng)}</span><span>${esc(p.suiqian)}</span><span>${esc(p.jiangqian)}</span><span>${esc(p.boshi)}</span></div>
                <div class="p-name-row">
                    <span class="p-name" onclick="event.stopPropagation(); openPalaceDetail(${p.index})" title="查看宫位详情">${esc(p.name)}</span>
                    <span class="p-gz">${esc(p.ganzhi)}</span>
                    <span class="p-dec" title="大限 ${p.decadal.start_year}-${p.decadal.end_year}">${p.decadal.start}-${p.decadal.end}</span>
                </div>
                <div class="p-ages">小限 ${p.ages.slice(0, 3).join(',')}… · 流年 ${p.yearly_ages.slice(0, 3).join(',')}…</div>
            </div>
            <div class="p-lvtag" id="lvtag-${p.index}"></div>
        </div>`;
    }).join('');
    root.innerHTML = `<div class="zw-wrap"><div class="zw-head" id="zw-head"></div><div class="zw-grid" id="zw-grid">${cells}<div class="zw-center" id="zw-center"></div><div class="zw-mid" id="zw-mid"></div><svg class="zw-svg" id="zw-svg"></svg></div></div>`;
    renderCenter();
    applyLayers();
}

function _levelRows() {
    const L = AppState.levelData;
    const rows = [];
    for (const k of ['decadal', 'yearly', 'monthly', 'daily', 'hourly']) {
        const d = L[k]; if (!d) continue;
        const name = { decadal: '大限', yearly: '流年', monthly: '流月', daily: '流日', hourly: '流时' }[k];
        const extra = k === 'decadal' ? ` ${d.start_age}-${d.end_age}岁` : k === 'yearly' ? ` ${d.year}年 ${d.age}岁` : k === 'monthly' ? ` ${d.month_name || ''}` : k === 'daily' ? ` ${d.solar_date}` : ` ${d.hour_branch || ''}时`;
        rows.push(`<div><span class="hua lv lvc-${k}" style="color:#000">${name}</span> <b>${d.ganzhi}</b>${extra} · 命宫在<b>${d.palace_name}</b> · ${d.hua.map(h => `${h.star}<i class="hua ${HUA_CLS[h.hua]}">${h.hua}</i>→${h.palace_name || '—'}`).join(' ')}${k === 'yearly' && d.age_palace ? ` · 小限在<b>${d.age_palace.name}</b>` : ''}</div>`);
    }
    return rows;
}

function renderCenter() {
    const z = AppState.ziwei; if (!z) return;
    const b = z.birth;
    const p = AppState.person || {};
    const el = document.getElementById('zw-center');
    const pil = z.pillars.jieqi.map((gz, i) => `<span>${gz}<small>${['年', '月', '日', '时'][i]}</small></span>`).join('');
    const hua = Object.entries(z.birth_hua).map(([h, s]) => `<span>${esc(s)}<i class="hua ${HUA_CLS[h]} birth">${h}</i></span>`).join(' ');
    const rows = _levelRows();
    const level = rows.length ? `<div class="zw-level-summary">${rows.join('')}</div>` : '';
    let fly = '';
    if (AppState.layers.feixing && AppState.selectedPalace != null) {
        const f = z.fly[AppState.selectedPalace];
        fly = `<div class="fly-list"><b>${f.from_name}[${f.stem}]</b> 飞：${f.targets.map(t => `<i class="hua ${HUA_CLS[t.hua]}">${t.hua}</i>${t.star}→${t.to_name || '不在盘中'}${t.self ? '(自化)' : t.opposite ? '(对宫)' : ''}`).join(' ')}</div>`;
    }
    const legend = `<div class="zw-legend"><span><i class="hua lu birth">禄</i> 生年</span><span><i class="hua ji self">↓忌</i> 离心自化</span><span><i class="hua quan self">↑权</i> 向心自化</span><span><i class="hua lu lv">限禄</i> 运限四化</span><span>点宫位=三方四正引用入对话 · 点宫名=详情</span></div>`;
    const info = `${previewBar()}<div class="row"><span>公历 <b>${b.solar}</b></span>${b.use_true_solar_time ? `<span>真太阳时 <b>${b.true_solar.slice(11)}</b>（经度 ${b.longitude}）</span>` : ''}</div>
        <div class="row"><span>农历 <b>${b.lunar}</b></span></div>
        <div class="pillars">${pil}</div>
        <div class="row"><span><b>${z.bureau}</b></span><span>命主 <b>${z.ming_zhu}</b></span><span>身主 <b>${z.shen_zhu}</b></span><span>子年斗君 <b>${z.zi_dou}</b></span></div>
        <div class="row"><span>身宫 <b>${z.palaces[z.body_index].name}</b></span><span>来因 <b>${z.palaces[z.laiyin_index].name}</b></span><span>大限${z.forward ? '顺' : '逆'}行</span></div>
        <div class="row"><span>生年四化 ${hua}</span></div>
        ${patternsRow(z.patterns)}`;
    el.innerHTML = `<h3>${esc(p.display_name || '')} <span style="font-size:.75rem;color:var(--text-secondary);font-weight:400;">${b.yinyang_gender}</span></h3>${info}${fly}${level}${legend}`;

    // phone: collapsible header bar + small centre cell
    const head = document.getElementById('zw-head');
    if (head) {
        const soul = z.palaces[z.soul_index];
        const open = head.classList.contains('open');
        head.innerHTML = `<div class="zh-sum" onclick="document.getElementById('zw-head').classList.toggle('open')">
                <b>${esc(p.display_name || '')}</b><span>${b.yinyang_gender}</span><span>${z.bureau}</span><span>命宫${soul.ganzhi}</span><span>${hua}</span><span class="caret">${open ? '▴' : '▾'}</span></div>
            <div class="zh-detail">${info}${fly}${level}${legend}</div>`;
    }
    const mid = document.getElementById('zw-mid');
    if (mid) {
        const L = AppState.levelData;
        const parts = [];
        if (L.decadal) parts.push(`<span class="hua lv lvc-decadal" style="color:#000">限</span>${L.decadal.ganzhi}`);
        if (L.yearly) parts.push(`<span class="hua lv lvc-yearly" style="color:#000">年</span>${L.yearly.ganzhi}`);
        if (L.monthly) parts.push(`<span class="hua lv lvc-monthly" style="color:#000">月</span>${L.monthly.ganzhi}`);
        if (L.daily) parts.push(`<span class="hua lv lvc-daily" style="color:#000">日</span>${L.daily.ganzhi}`);
        mid.innerHTML = `<div class="mid-name">${esc(p.display_name || '')}</div><div>${b.yinyang_gender} · ${z.bureau}</div><div>${b.lunar}</div><div class="mid-lv">${parts.join(' ') || '<span class="text-muted">点下方运限条选择大限/流年</span>'}</div>`;
    }
}

/* 格局（代码判定成格方向，不判破格） */
function patternsRow(r) {
    if (!r) return '';
    const chips = r.patterns.length
        ? r.patterns.map((p, i) => `<span class="zw-geju ${p.kind === '凶' ? 'xiong' : 'ji'}" onclick="event.stopPropagation(); showPattern(${i})" title="${esc(p.evidence.join('；'))}">${esc(p.name)}</span>`).join('')
        : '<span class="text-muted">未见常见格局</span>';
    return `<div class="row zw-geju-row"><span>格局</span>${chips}</div>`;
}

function showPattern(i) {
    const r = AppState.ziwei && AppState.ziwei.patterns; if (!r) return;
    const p = r.patterns[i]; const c = r.context;
    const facts = [['煞', c.sha], ['空亡', c.kong], ['生年忌', c.ji], ['离心自化忌', c.self_ji], ['主星落陷', c.xian]]
        .filter(([, v]) => v.length).map(([k, v]) => `<div><b>${k}</b>：${v.map(esc).join('、')}</div>`).join('') || '<div>未见煞忌空陷</div>';
    showInfoSheet(`${p.name}（${p.kind}格 · ${p.level}宫）`, `
        <div class="pd-section"><h4>成格依据</h4>${p.evidence.map(e => `<div>· ${esc(e)}</div>`).join('')}${p.note ? `<div class="text-muted" style="margin-top:.3rem;">注：${esc(p.note)}</div>` : ''}</div>
        <div class="pd-section"><h4>命宫三方四正与夹宫的事实</h4>${facts}
            <div class="text-muted" style="font-size:.72rem;margin-top:.3rem;">代码只判成格方向，破格程度请用「紫微斗数格局分析」交给 AI 评估。</div></div>
        <div class="pd-actions"><button class="btn btn-primary btn-sm" onclick="closeModal('modal-info'); askPatterns('ziwei')">💬 让 AI 评估破格</button></div>`);
}

function palaceRef(i, role) {
    const p = AppState.ziwei.palaces[i];
    const fmt = s => s.name + (s.brightness ? `[${s.brightness}]` : '') + (s.birth_hua ? `[生年${s.birth_hua}]` : '') + (s.self_hua_out ? `[↓${s.self_hua_out}]` : '') + (s.self_hua_in ? `[↑${s.self_hua_in}]` : '');
    return {
        kind: 'palace', role, index: i, palace: p.name, ganzhi: p.ganzhi,
        major: p.stars.filter(s => s.category === 'major').map(fmt),
        minor: p.stars.filter(s => s.category === 'minor').map(fmt),
        adjective: p.stars.filter(s => s.category === 'adjective').map(s => s.name),
        changsheng: p.changsheng, decadal: `${p.decadal.start}-${p.decadal.end}岁`,
    };
}

function onPalaceClick(i) {
    const was = AppState.selectedPalace;
    AppState.selectedPalace = was === i ? null : i;
    if (AppState.selectedPalace != null) {
        // 本宫 + 对宫 + 两个三合宫，全部星曜作为引用气泡加入对话
        const refs = [palaceRef(i, '本宫'), palaceRef((i + 6) % 12, '对宫'), palaceRef((i + 4) % 12, '三合'), palaceRef((i + 8) % 12, '三合')];
        setPalaceRefs(refs);
    } else {
        setPalaceRefs([]);
    }
    applyLayers();
    renderCenter();
}

function onStarClick(ev, pi, name) {
    // 单星不再单独引用：点星 = 点宫
    ev.stopPropagation();
    onPalaceClick(pi);
}

function openPalaceDetail(i) {
    const z = AppState.ziwei; const p = z.palaces[i];
    document.getElementById('modal-palace-title').textContent = `${p.name} · ${p.ganzhi}${p.is_body ? ' · 身宫' : ''}${p.is_laiyin ? ' · 来因宫' : ''}`;
    const f = z.fly[i];
    const sf = [i, (i + 4) % 12, (i + 6) % 12, (i + 8) % 12].map(k => z.palaces[k]);
    const starRow = s => `<div class="pd-star">
        <span>${starHtml(s, i)}</span><span class="text-muted" style="font-size:.7rem;">${s.category === 'major' ? '主星' : s.category === 'minor' ? '辅星' : '小星'}</span></div>`;
    const lvBadges = [];
    for (const lv of ['decadal', 'yearly', 'monthly', 'daily', 'hourly']) {
        const d = AppState.levelData[lv]; if (!d) continue;
        for (const h of d.hua) if (h.palace_index === i) lvBadges.push(`<span>${{ decadal: '限', yearly: '年', monthly: '月', daily: '日', hourly: '时' }[lv]}${h.star}<i class="hua ${HUA_CLS[h.hua]} lv">${h.hua}</i></span>`);
        if (d.index === i) lvBadges.push(`<span class="hua lv lvc-${lv}" style="color:#000">${{ decadal: '大限', yearly: '流年', monthly: '流月', daily: '流日', hourly: '流时' }[lv]}命宫</span>`);
    }
    document.getElementById('modal-palace-body').innerHTML = `
        <div class="pd-actions" style="margin-bottom:.6rem;">
            <button class="btn btn-accent btn-sm" onclick="if(AppState.selectedPalace!==${i}) onPalaceClick(${i}); closeModal('modal-palace'); if(isMobile()) togglePane('right', false);">💬 引用三方四正提问</button>
            <button class="btn btn-secondary btn-sm" onclick="AppState.selectedPalace=${i}; if(!AppState.layers.feixing) toggleLayer('feixing'); else { applyLayers(); renderCenter(); } closeModal('modal-palace')">✈ 飞星</button>
            <button class="btn btn-secondary btn-sm" onclick="AppState.selectedPalace=${i}; if(!AppState.layers.sanhe) toggleLayer('sanhe'); else { applyLayers(); renderCenter(); } closeModal('modal-palace')">三合</button>
        </div>
        ${lvBadges.length ? `<div class="pd-section"><h4>当前运限落此宫</h4><div class="row" style="display:flex;flex-wrap:wrap;gap:.3rem .6rem;font-size:.78rem;">${lvBadges.join('')}</div></div>` : ''}
        <div class="pd-section"><h4>星曜</h4>${p.stars.map(starRow).join('') || '<div class="text-muted">空宫，借对宫星曜</div>'}</div>
        <div class="pd-section"><h4>神煞 / 运限</h4><div class="row" style="font-size:.8rem;color:var(--text-secondary);">十二长生 <b>${p.changsheng}</b> · 岁前 <b>${p.suiqian}</b> · 将前 <b>${p.jiangqian}</b> · 博士 <b>${p.boshi}</b><br>大限 <b>${p.decadal.start}-${p.decadal.end}岁</b>（${p.decadal.start_year}-${p.decadal.end_year}）<br>小限 ${p.ages.join(', ')} 岁<br>流年 ${p.yearly_ages.join(', ')} 岁</div></div>
        <div class="pd-section"><h4>宫干 ${p.stem} 飞四化</h4><div class="fly-list">${f.targets.map(t => `<div><i class="hua ${HUA_CLS[t.hua]}">${t.hua}</i>${t.star} → ${t.to_name || '不在盘中'}${t.self ? '（本宫自化）' : t.opposite ? '（对宫）' : ''}</div>`).join('')}</div></div>
        <div class="pd-section"><h4>三方四正</h4><div class="text-muted" style="font-size:.8rem;">${sf.map(x => `${x.name}(${x.ganzhi})`).join(' · ')}</div></div>`;
    openModal('modal-palace');
}
