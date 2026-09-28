/* ===== Global state ===== */
const AppState = {
    config: {},
    people: [],            // summaries
    personId: null,
    person: null,          // full person record
    chart: 'ziwei',        // 'ziwei' | 'bazi'
    ziwei: null,           // /api/people/{id}/ziwei
    bazi: null,            // /api/people/{id}/bazi
    baziTimeline: null,
    layers: { sihua: true, sanhe: false, feixing: false, minor: true, links: false },
    selectedPalace: null,  // palace index 0..11
    // horoscope selection
    level: { decadal: null, yearly: null, monthly: null, daily: null, hourly: null },
    levelData: { decadal: null, yearly: null, monthly: null, daily: null, hourly: null },
    lists: { yearly: [], monthly: [], daily: [], hourly: [] },
    // chat
    sessions: [],
    sessionId: null,
    session: null,
    catalog: null,          // /api/config/catalog：模型库 + 能力 + 跳板状态
    pendingPick: null,      // 会话还没创建时先记住选的模型/思考档位
    selectedContext: {},
    isStreaming: false,
    abort: null,
    pendingUpdate: null,
};

function viewContext() {
    const vc = { chart: AppState.chart === 'ziwei' ? '紫微斗数' : '子平八字' };
    if (AppState.chart === 'ziwei') {
        const on = Object.entries(AppState.layers).filter(([k, v]) => v && k !== 'minor' && k !== 'links').map(([k]) => ({ sihua: '四化', sanhe: '三合', feixing: '飞星' }[k]));
        if (on.length) vc.layer = on.join('/');
        const lv = [];
        const L = AppState.levelData;
        if (L.decadal) lv.push(`大限 ${L.decadal.ganzhi}(${L.decadal.palace_name} ${L.decadal.start_age}-${L.decadal.end_age}岁)`);
        if (L.yearly) lv.push(`流年 ${L.yearly.year} ${L.yearly.ganzhi}(${L.yearly.palace_name})`);
        if (L.monthly) lv.push(`流月 ${L.monthly.month_name || ''} ${L.monthly.ganzhi}(${L.monthly.palace_name})`);
        if (L.daily) lv.push(`流日 ${L.daily.solar_date} ${L.daily.ganzhi}(${L.daily.palace_name})`);
        if (L.hourly) lv.push(`流时 ${L.hourly.ganzhi}(${L.hourly.palace_name})`);
        if (lv.length) vc.level = lv.join('；');
        if (AppState.selectedPalace != null && AppState.ziwei) {
            const p = AppState.ziwei.palaces[AppState.selectedPalace];
            vc.selected_palace = `${p.name}(${p.ganzhi})`;
        }
    } else if (AppState.baziTimeline) {
        const t = AppState.baziTimeline;
        vc.date = t.date;
        vc.level = `大运 ${t.dayun && t.dayun.ganzhi}；流年 ${t.liunian.ganzhi}；流月 ${t.liuyue.ganzhi}；流日 ${t.liuri.ganzhi}`;
    }
    return vc;
}
