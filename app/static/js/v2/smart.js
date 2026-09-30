/* ===== 【智能分析】弹窗：紫微格局、子平格局、人生喜事、引导式反推 =====
   数据来自 /api/people/{id}/analysis（全部代码计算，不经 AI）。
   只有点卡片里的「问 AI」按钮才跳到对话，服务端会把对应的代码结果附在消息后面。 */

const XISHI = ['结婚', '发财', '高升', '搬迁', '添丁', '高中'];
const XISHI_ICON = { 结婚: '💍', 发财: '💰', 高升: '📈', 搬迁: '🏠', 添丁: '👶', 高中: '🎓' };
const SMART_TABS = [['ziwei', '🏯 紫微格局'], ['bazi', '⚖ 子平格局'], ['xishi', '🎉 人生喜事'], ['rectify', '🧭 反推时辰']];
let _smartTab = 'ziwei';
let _smartPattern = null;     // 选中的紫微格局序号
let _xishiOpen = null;        // 展开的喜事

async function loadAnalysis() {
    if (!AppState.personId) return null;
    if (AppState.analysis && AppState.analysis._pid === AppState.personId) return AppState.analysis;
    try {
        const a = await API.get(`/api/people/${AppState.personId}/analysis`);
        a._pid = AppState.personId;
        AppState.analysis = a;
        return a;
    } catch (e) { toast('分析载入失败: ' + e.message, true); return null; }
}

async function openSmart(tab) {
    if (!AppState.personId) { toast('请先选择人物', true); return; }
    if (tab) _smartTab = tab;
    if (AppState.analysis && AppState.analysis._pid !== AppState.personId) { _smartPattern = null; _xishiOpen = null; }
    openModal('modal-smart');
    const body = document.getElementById('smart-body');
    document.getElementById('smart-title').textContent = `✨ 智能分析 · ${AppState.person ? AppState.person.display_name : ''}`;
    body.innerHTML = '<div class="text-muted" style="font-size:.8rem;">正在计算格局与喜事年份…</div>';
    const a = await loadAnalysis();
    if (!a) { body.innerHTML = '<div class="text-red">分析载入失败</div>'; return; }
    renderSmart();
}

function switchSmartTab(tab) { _smartTab = tab; renderSmart(); }

function renderSmart() {
    const a = AppState.analysis; const body = document.getElementById('smart-body');
    if (!a || !body) return;
    const tabs = SMART_TABS.map(([k, t]) => `<button class="sm-tab ${_smartTab === k ? 'on' : ''}" onclick="switchSmartTab('${k}')">${t}</button>`).join('');
    const panel = { ziwei: _smartZiwei, bazi: _smartBazi, xishi: _smartXishi, rectify: _smartRectify }[_smartTab](a);
    const pv = AppState.preview ? '<div class="sm-warn">当前是预览盘，这里的分析仍按已保存的出生时间计算。</div>' : '';
    body.innerHTML = `<div class="sm-tabs">${tabs}</div>${pv}${panel}`;
}

/* ---------- 紫微格局：每个格一个标签，点标签看依据，问 AI 走专门按钮 ---------- */
function _smartZiwei(a) {
    const r = a.patterns || { patterns: [], counts: {}, context: {} };
    const tag = (p, i) => `<button class="sm-geju ${p.kind === '凶' ? 'xiong' : 'ji'} ${_smartPattern === i ? 'on' : ''}" onclick="pickSmartPattern(${i})">
        ${esc(p.name)}${p.level !== '命' ? `<small>${esc(p.level)}</small>` : ''}</button>`;
    const group = kind => {
        const items = r.patterns.map((p, i) => [p, i]).filter(([p]) => p.kind === kind);
        return `<div class="sm-group"><div class="sm-glabel ${kind === '凶' ? 'xiong' : 'ji'}">${kind}格 ${items.length}</div>
            <div class="sm-tags">${items.map(([p, i]) => tag(p, i)).join('') || '<span class="text-muted">无</span>'}</div></div>`;
    };
    const p = _smartPattern != null ? r.patterns[_smartPattern] : null;
    const detail = p ? `<div class="sm-detail">
            <div class="sm-dh">${esc(p.name)} <small>${p.kind}格 · ${esc(p.level)}宫${p.aliases && p.aliases.length ? ' · 又名' + p.aliases.map(esc).join('、') : ''}</small></div>
            ${p.evidence.map(e => `<div>· ${esc(e)}</div>`).join('')}
            ${p.note ? `<div class="text-muted" style="margin-top:.25rem;">注：${esc(p.note)}</div>` : ''}</div>`
        : '<div class="sm-hint">点上面的格局标签查看成格依据。</div>';
    const c = r.context || {};
    const facts = [['煞', c.sha], ['空亡', c.kong], ['生年忌', c.ji], ['离心自化忌', c.self_ji], ['主星落陷', c.xian]]
        .filter(([, v]) => v && v.length).map(([k, v]) => `<div><b>${k}</b>：${v.map(esc).join('、')}</div>`).join('') || '<div>未见煞忌空陷</div>';
    return `<div class="sm-card">
        <div class="sm-head"><div><b>紫微斗数格局</b><small>命宫${esc((r.ming || {}).branch || '')} · 代码只判成格方向，不判破格</small></div>
            <button class="btn btn-primary btn-sm" onclick="askPatterns('ziwei')">💬 问 AI 评估破格</button></div>
        ${r.patterns.length ? group('吉') + group('凶') : '<div class="text-muted">未见常见格局</div>'}
        ${detail}
        <details class="sm-facts"><summary>命宫三方四正与夹宫的煞忌事实（交给 AI 判断破格）</summary>${facts}</details>
    </div>`;
}

function pickSmartPattern(i) { _smartPattern = _smartPattern === i ? null : i; renderSmart(); }

/* ---------- 子平格局：取格、候选、强弱、用神 ---------- */
function _smartBazi(a) {
    const A = a.bazi;
    if (!A) return '<div class="sm-card text-muted">暂无八字分析</div>';
    const st = A.strength, gj = A.geju, ys = A.yongshen;
    const cand = gj.candidates.map(x => `<span class="sm-geju ji ${gj.primary && gj.primary.name === x.name ? 'on' : ''}" title="${esc(x.basis.join('；'))}">${esc(x.name)}<small>${x.pct}%</small></span>`).join('');
    const special = gj.special.map(s => `<span class="sm-geju warn">${esc(s.name)}<small>${s.pct}%</small></span>`).join('');
    const roles = ys.ranking.map(r => `<span class="sm-role">${r.role} <b>${wx(r.element, r.element)}</b></span>`).join('');
    const groups = A.shishen.groups.map(g => `<span class="sm-role">${g.group} <b>${g.pct}%</b></span>`).join('');
    return `<div class="sm-card">
        <div class="sm-head"><div><b>子平格局</b><small>${gj.primary ? '取格 ' + esc(gj.primary.name) + ' · ' + esc(gj.primary.basis) : ''}</small></div>
            <button class="btn btn-primary btn-sm" onclick="askPatterns('bazi')">💬 问 AI 评估破格</button></div>
        <div class="sm-group"><div class="sm-glabel">格局候选</div><div class="sm-tags">${cand}${special}</div></div>
        <div class="sm-group"><div class="sm-glabel">身强弱</div><div class="sm-tags"><span class="sm-role"><b>${esc(st.label)}</b> 同类 ${st.same_pct}%</span>
            ${st.special ? `<span class="sm-geju warn">${esc(st.special)}</span>` : ''}${st.border ? '<span class="sm-role">临界</span>' : ''}</div></div>
        <div class="sm-group"><div class="sm-glabel">喜忌</div><div class="sm-tags">${roles}</div></div>
        <div class="sm-group"><div class="sm-glabel">十神</div><div class="sm-tags">${groups}</div></div>
        ${gj.observations.length ? `<div class="sm-hint">相关合冲：${gj.observations.map(esc).join('、')}</div>` : ''}
        <div class="sm-hint">完整的五行条形图、十神明细与用神加减分在「子平八字」页的命局分析里。</div>
    </div>`;
}

/* ---------- 人生喜事：每件事一行，按能量从大到小列一生最强 3 年 ---------- */
function _smartXishi(a) {
    const ev = a.life_events;
    if (!ev || !ev.events) return '<div class="sm-card text-muted">暂无数据</div>';
    const rows = XISHI.filter(n => ev.events[n]).map(n => {
        const e = ev.events[n];
        const tags = e.life_top.map(r => `<span class="sm-year ${r.past ? 'past' : ''}" title="${r.age}岁 · 分 ${r.score}">${r.year}<small>${r.past ? '已过' : r.age + '岁'}</small></span>`).join('');
        return `<div class="sm-xrow ${_xishiOpen === n ? 'on' : ''}">
            <button class="sm-xhead" onclick="toggleXishi('${n}')"><span class="sm-xname">${XISHI_ICON[n]} ${n}</span>
                <span class="sm-years">${tags || '<small class="text-muted">不在常见年龄段</small>'}</span><span class="sm-caret">${_xishiOpen === n ? '▴' : '▾'}</span></button>
            ${_xishiOpen === n ? _xishiDetail(e, n) : ''}</div>`;
    }).join('');
    return `<div class="sm-card">
        <div class="sm-head"><div><b>人生喜事</b><small>一生中能量最强的 3 年，按强弱排序；灰色为已过的年份</small></div>
            <button class="btn btn-primary btn-sm" onclick="askLifeEvent()">💬 问 AI 总览</button></div>
        ${rows}
        <div class="sm-hint">代码按大限与流年的四化、流曜、叠宫打分，八字流年十神辅助；只比较同一人不同年份的相对强弱，不是断语。</div>
    </div>`;
}

function _xishiDetail(e, name) {
    const sig = r => r.signals.filter(s => s.delta).sort((x, y) => Math.abs(y.delta) - Math.abs(x.delta)).slice(0, 4)
        .map(s => `<span class="${s.delta < 0 ? 'text-red' : ''}">${esc(s.text)}</span>`).join('；');
    const row = r => `<div class="sm-xline"><b>${r.year}</b><span>${r.age}岁</span><span class="xs-bar"><i style="width:${Math.max(4, Math.min(100, r.pct))}%"></i></span>
        <span>${r.months.map(m => '农历' + m.name).join('、')}</span></div><div class="sm-xsig">${sig(r)}</div>`;
    const fut = e.future_top.filter(r => !e.life_top.some(t => t.year === r.year)).slice(0, 3);
    return `<div class="sm-xdetail">
        <div class="sm-xsub">看${e.palace} · 一生最强</div>${e.life_top.map(row).join('')}
        ${fut.length ? `<div class="sm-xsub">未来 20 年里另外较强的年份：${fut.map(r => `${r.year}（${r.age}岁）`).join('、')}</div>` : ''}
        <div class="pd-actions"><button class="btn btn-primary btn-sm" onclick="askLifeEvent('${name}')">💬 问 AI 解读${name}</button></div>
    </div>`;
}

function toggleXishi(name) { _xishiOpen = _xishiOpen === name ? null : name; renderSmart(); }

/* ---------- 反推时辰入口 ---------- */
function _smartRectify() {
    return `<div class="sm-card">
        <div class="sm-head"><div><b>引导式反推时辰</b><small>不确定出生时辰时用</small></div></div>
        <div class="sm-hint" style="margin-top:0;">回答几道关于兄弟姐妹、婚育、父母变故、搬迁等经历的问题（带年份最有用），
            代码把候选时辰逐个排盘打分；有大致时段就比前后各两个时辰，没有就比全天，子时同时算当天早子与前一天晚子。
            排名来自代码，AI 只在你点「交给 AI」后帮忙比对并补问。</div>
        <div class="pd-actions"><button class="btn btn-primary btn-sm" onclick="openRectify()">开始问卷</button></div>
    </div>`;
}

/* ---------- 跳到 AI ---------- */
function _ensureChatOpen() {
    closeAllModals();
    const pane = document.getElementById('pane-right');
    if (pane && pane.classList.contains('collapsed')) togglePane('right', false);
}

function askPatterns(kind) {
    if (!AppState.personId) { toast('请先选择人物', true); return; }
    _ensureChatOpen();
    const content = kind === 'ziwei' ? '紫微斗数格局分析' : '十神格局分析';
    sendMessage({ content, action: { type: kind === 'ziwei' ? 'ziwei_geju' : 'bazi_geju' } });
}

function askLifeEvent(name) {
    if (!AppState.personId) { toast('请先选择人物', true); return; }
    _ensureChatOpen();
    if (name) sendMessage({ content: `人生喜事：${name}`, action: { type: 'life_event', event: name } });
    else sendMessage({ content: '人生喜事总览', action: { type: 'life_events' } });
}
