/* ===== 上下调日期与时辰：预览相邻的盘（不落盘） =====
   一天 13 个时辰位（早子、丑…亥、晚子），「时 ▶」到亥之后是当天晚子，再往后是次日早子。
   预览期间运限条暂停；「应用到此人」才会写回出生时间。 */

function previewBar() {
    if (!AppState.personId) return '';
    const P = AppState.preview;
    const btn = (label, d, s, title) => `<button class="pv-btn" title="${title}" onclick="event.stopPropagation(); previewStep(${d}, ${s})">${label}</button>`;
    const steps = `${btn('◀日', -1, 0, '前一天，时辰不变')}${btn('◀时', 0, -1, '前一个时辰')}`;
    const steps2 = `${btn('时▶', 0, 1, '后一个时辰')}${btn('日▶', 1, 0, '后一天，时辰不变')}`;
    if (!P) {
        return `<div class="row pv-bar">${steps}<span class="pv-label text-muted">不确定时辰？前后调着看</span>${steps2}</div>`;
    }
    const L = P.data.label, O = P.data.original;
    return `<div class="row pv-bar active">${steps}<span class="pv-label"><b>预览 ${esc(L.label)}</b>
            <small>真太阳 ${esc(L.true_solar.slice(11))} · 钟表 ${esc(L.clock)}｜原 ${esc(O.label)}</small></span>${steps2}
        <span class="pv-actions"><button class="btn btn-ghost btn-sm" onclick="event.stopPropagation(); previewReset()">恢复</button>
        <button class="btn btn-primary btn-sm" onclick="event.stopPropagation(); previewApply()">应用到此人</button></span></div>`;
}

function _previewRerender() {
    AppState.selectedPalace = null;
    AppState.level = { decadal: null, yearly: null, monthly: null, daily: null, hourly: null };
    AppState.levelData = { decadal: null, yearly: null, monthly: null, daily: null, hourly: null };
    if (AppState.chart === 'ziwei') { renderZiwei(); renderStrips(); }
    else { renderBazi(); renderBaziStrips(); const ch = document.getElementById('bz-chain'); if (ch && AppState.preview) ch.innerHTML = ''; }
}

async function previewStep(dDays, dSlots) {
    if (!AppState.personId) return;
    const cur = AppState.preview || { days: 0, slots: 0 };
    const next = { days: cur.days + dDays, slots: cur.slots + dSlots };
    if (!next.days && !next.slots) { previewReset(); return; }
    try {
        const r = await API.get(`/api/people/${AppState.personId}/preview?days=${next.days}&slots=${next.slots}`);
        if (!AppState.preview) AppState.savedCharts = { ziwei: AppState.ziwei, bazi: AppState.bazi, timeline: AppState.baziTimeline };
        AppState.preview = { ...next, data: r };
        AppState.ziwei = r.ziwei; AppState.bazi = r.bazi; AppState.baziTimeline = null;
        _previewRerender();
    } catch (e) { toast('预览失败: ' + e.message, true); }
}

function previewReset() {
    const s = AppState.savedCharts;
    AppState.preview = null; AppState.savedCharts = null;
    if (s) { AppState.ziwei = s.ziwei; AppState.bazi = s.bazi; AppState.baziTimeline = s.timeline; }
    if (AppState.chart === 'ziwei') { renderZiwei(); initHoroscopeStrip(); }
    else { renderBazi(); loadBaziTimeline(fmtDate(new Date())); }
}

async function previewApply() {
    const P = AppState.preview; const person = AppState.person;
    if (!P || !person) return;
    const from = P.data.original.label, to = P.data.label.label;
    if (!confirm(`把 ${person.display_name} 的出生时间改为预览的时辰？\n\n${from}  →  ${to}\n（钟表时间 ${P.data.birth.solar}）`)) return;
    try {
        await API.put(`/api/people/${person.id}`, { birth: { ...person.birth, solar: P.data.birth.solar, hour_override: null } });
        await API.post(`/api/people/${person.id}/notes`, { text: `时辰调整：${from} → ${to}（页面预览后应用）`, author: 'user' });
        AppState.preview = null; AppState.savedCharts = null;
        AppState.ziwei = null; AppState.bazi = null; AppState.baziTimeline = null;
        await selectPerson(person.id, { keepSession: true });
        toast(`已改为 ${to}，并记入备注`);
    } catch (e) { toast('应用失败: ' + e.message, true); }
}

function previewStripNote() {
    return `<div class="strip pv-strip-note">预览模式：运限条暂停。确认时辰后点「应用到此人」，或点「恢复」回到原盘。</div>`;
}
