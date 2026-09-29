/* ===== 新对话欢迎区：两个格局分析入口 + 【人生喜事】卡 + 反推时辰入口 =====
   数据来自 /api/people/{id}/analysis（全部代码计算）；点击后把预置问题发给 AI，
   服务端会把对应的代码结果附在消息后面。 */

const XISHI = ['结婚', '发财', '高升', '搬迁', '添丁', '高中'];
const XISHI_ICON = { 结婚: '💍', 发财: '💰', 高升: '📈', 搬迁: '🏠', 添丁: '👶', 高中: '🎓' };
let _xishiOpen = null;

async function loadAnalysis() {
    if (!AppState.personId) return null;
    if (AppState.analysis && AppState.analysis._pid === AppState.personId) return AppState.analysis;
    try {
        const a = await API.get(`/api/people/${AppState.personId}/analysis`);
        a._pid = AppState.personId;
        AppState.analysis = a;
        return a;
    } catch (e) { return null; }
}

async function renderWelcomeExtra() {
    const box = document.getElementById('welcome-extra');
    if (!box) return;
    box.innerHTML = '<div class="text-muted" style="font-size:.75rem;margin-top:.6rem;">正在计算格局与喜事年份…</div>';
    const a = await loadAnalysis();
    const el = document.getElementById('welcome-extra');   // 可能已被新消息替换
    if (!el) return;
    if (!a) { el.innerHTML = ''; return; }
    el.innerHTML = `${_analysisCards(a)}${_xishiCard(a.life_events)}
        <div class="wl-row"><button class="wl-chip" onclick="openRectify()">🧭 不确定出生时辰？引导式反推</button></div>`;
}

function _analysisCards(a) {
    const zp = a.patterns || { patterns: [], counts: {} };
    const zname = zp.patterns.slice(0, 3).map(p => p.name).join('、') || '未见常见格局';
    const b = a.bazi || {};
    const bz = b.strength ? `${(b.geju.primary || {}).name || ''} · ${b.strength.label} ${b.strength.same_pct}% · 用${b.yongshen.ranking[0].element}` : '';
    return `<div class="wl-cards">
        <button class="wl-card" onclick="askPatterns('ziwei')"><b>🏯 紫微斗数格局分析</b>
            <small>吉${zp.counts['吉'] || 0} 凶${zp.counts['凶'] || 0}：${esc(zname)}</small><span>由 AI 评估破格程度 →</span></button>
        <button class="wl-card" onclick="askPatterns('bazi')"><b>⚖ 十神格局分析</b>
            <small>${esc(bz)}</small><span>由 AI 评估破格程度 →</span></button>
    </div>`;
}

function _xishiCard(ev) {
    if (!ev || !ev.events) return '';
    const tile = (name, area) => {
        const e = ev.events[name];
        const top = e && e.future_top[0];
        const line = top ? `${top.year}<small>${top.months[0] ? '农历' + top.months[0].name : ''}</small>` : '<small>已过常见年龄段</small>';
        const past = e && e.past_strong.length ? `<em>往年 ${e.past_strong.slice(0, 2).map(r => r.year).join('·')}</em>` : '';
        return `<button class="xs-tile ${_xishiOpen === name ? 'open' : ''}" data-name="${name}" style="grid-area:${area}" onclick="toggleXishi('${name}')">
            <span class="xs-name">${XISHI_ICON[name]} ${name}</span><span class="xs-year">${line}</span>${past}</button>`;
    };
    const areas = { 结婚: 'a', 发财: 'b', 高升: 'c', 搬迁: 'd', 添丁: 'e', 高中: 'f' };
    return `<div class="xs-card">
        <div class="xs-grid">${XISHI.map(n => tile(n, areas[n])).join('')}
            <div class="xs-center" style="grid-area:m" onclick="askLifeEvent()">【人生喜事】<small>点四周看年份<br>点这里让 AI 总览</small></div>
        </div>
        <div id="xs-detail">${_xishiOpen ? _xishiDetail(ev, _xishiOpen) : ''}</div>
        <div class="xs-note">按大限与流年的四化、流曜、叠宫打分，八字流年十神辅助；只比较同一人不同年份的相对强弱。</div>
    </div>`;
}

function _xishiDetail(ev, name) {
    const e = ev.events[name]; if (!e) return '';
    const row = r => `<div class="xs-row"><b>${r.year}</b><span>${r.age}岁</span><span class="xs-bar"><i style="width:${Math.max(4, Math.min(100, r.pct))}%"></i></span>
        <span>${r.months.map(m => '农历' + m.name).join('、')}</span></div>`;
    return `<div class="xs-detail">
        <div class="xs-dh">${XISHI_ICON[name]} ${name} · 看${e.palace}</div>
        ${e.future_top.length ? `<div class="xs-sub">未来 20 年最强</div>${e.future_top.map(row).join('')}` : '<div class="xs-sub">未来已不在常见年龄段</div>'}
        ${e.past_strong.length ? `<div class="xs-sub">往年强年（可核对）</div>${e.past_strong.map(row).join('')}` : ''}
        <div class="pd-actions"><button class="btn btn-primary btn-sm" onclick="askLifeEvent('${name}')">💬 让 AI 解读${name}</button></div>
    </div>`;
}

function toggleXishi(name) {
    _xishiOpen = _xishiOpen === name ? null : name;
    const a = AppState.analysis; if (!a) return;
    document.querySelectorAll('.xs-tile').forEach(t => t.classList.toggle('open', t.dataset.name === _xishiOpen));
    const d = document.getElementById('xs-detail');
    if (d) d.innerHTML = _xishiOpen ? _xishiDetail(a.life_events, _xishiOpen) : '';
}

function _ensureChatOpen() {
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
