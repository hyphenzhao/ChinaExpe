/* ===== 引导式反推时辰：问卷（代码定义、按回答逐步展开）→ 候选时辰评分 → 预览或交给 AI ===== */
let _rq = null;           // 问题清单
let _rfacts = {};         // 当前答案

async function openRectify() {
    if (!AppState.personId) { toast('请先选择人物', true); return; }
    try {
        if (!_rq) _rq = await API.get('/api/people/meta/rectify-questions');
        _rfacts = await API.get(`/api/people/${AppState.personId}/facts`) || {};
    } catch (e) { toast('载入问卷失败: ' + e.message, true); return; }
    document.getElementById('rectify-result').innerHTML = '';
    openModal('modal-rectify');
    renderRectifyForm();
}

function _rqVisible(q) {
    if (!q.show_if) return true;
    return Object.entries(q.show_if).every(([k, cond]) => {
        const v = _rfacts[k];
        if (cond === '>0') return Number(v) > 0;
        if (typeof cond === 'string' && cond.startsWith('!')) return v != null && v !== '' && v !== cond.slice(1);
        return v === cond;
    });
}

function renderRectifyForm() {
    const box = document.getElementById('rectify-form');
    box.innerHTML = _rq.filter(_rqVisible).map(q => {
        const v = _rfacts[q.id] == null ? '' : _rfacts[q.id];
        let field;
        if (q.type === 'choice') {
            field = `<div class="rq-choices">${q.options.map(o => `<button type="button" class="rq-opt ${v === o ? 'on' : ''}" onclick="setFact('${q.id}','${o}', true)">${o}</button>`).join('')}</div>`;
        } else if (q.type === 'text') {
            field = `<textarea class="input" rows="2" oninput="setFact('${q.id}', this.value)">${esc(v)}</textarea>`;
        } else if (q.type === 'time') {
            field = `<input type="time" class="input" value="${esc(v)}" onchange="setFact('${q.id}', this.value)">`;
        } else if (q.type === 'years') {
            field = `<input type="text" class="input" placeholder="如 2012, 2018" value="${esc(Array.isArray(v) ? v.join(', ') : v)}" oninput="setFact('${q.id}', this.value)">`;
        } else {
            const ph = q.type === 'year' ? '如 2015' : '数字';
            field = `<input type="number" class="input" placeholder="${ph}" value="${esc(v)}" onchange="setFact('${q.id}', this.value === '' ? '' : Number(this.value), true)">`;
        }
        return `<div class="form-group rq-item"><label>${esc(q.q)}</label>${field}</div>`;
    }).join('');
}

/* rerender=true 用于会改变后续问题是否出现的字段 */
function setFact(id, value, rerender) {
    if (value === '' || value == null) delete _rfacts[id]; else _rfacts[id] = value;
    if (rerender) renderRectifyForm();
}

async function runRectify() {
    const pid = AppState.personId; const out = document.getElementById('rectify-result');
    out.innerHTML = '<div class="text-muted" style="font-size:.75rem;">正在排候选盘并打分…</div>';
    try {
        // 未出现的问题不提交，免得旧答案干扰
        const visible = new Set(_rq.filter(_rqVisible).map(q => q.id));
        const payload = {};
        _rq.forEach(q => { payload[q.id] = visible.has(q.id) && _rfacts[q.id] != null ? _rfacts[q.id] : ''; });
        await API.put(`/api/people/${pid}/facts`, payload);
        const r = await API.post(`/api/people/${pid}/rectify`, {});
        out.innerHTML = _rectifyTable(r);
    } catch (e) { out.innerHTML = `<div class="text-red">评分失败：${esc(e.message)}</div>`; }
}

function _rectifyTable(r) {
    const conf = { 高: 'text-green', 中: '', 低: 'text-red' }[r.confidence] || '';
    const rows = r.candidates.map((c, i) => `<tr class="${c.flags.is_current ? 'rq-cur' : ''}">
        <td>${i + 1}</td><td><b>${esc(c.label)}</b>${c.flags.is_current ? ' <small>现盘</small>' : ''}<br><small>${esc(c.range)}</small></td>
        <td>${esc(c.brief.ming)} ${esc(c.brief.majors.join('') || '无主星')}<br><small>${esc(c.brief.bureau)} · 时柱${esc(c.brief.hour_pillar)}${c.flags.day_changed ? ' · 日柱变' : ''}</small></td>
        <td><b>${c.score}</b></td>
        <td><button class="btn btn-ghost btn-sm" title="${esc(c.rows.map(x => `${x.fact} ${x.contribution > 0 ? '+' : ''}${x.contribution}：${x.why}`).join('\n'))}" onclick="closeModal('modal-rectify'); previewGoto(${c.offset_slots})">预览</button></td>
    </tr>`).join('');
    return `<div class="rq-result">
        <div class="rq-sum">置信度 <b class="${conf}">${r.confidence}</b> · 第一名领先 ${r.gap == null ? '—' : r.gap} 分 · 带年份的经历 ${r.dated_facts} 条 · ${esc(r.mode)}</div>
        <div class="rq-table-wrap"><table class="rq-table"><tr><th>#</th><th>候选</th><th>命宫与局</th><th>分</th><th></th></tr>${rows}</table></div>
        <div class="text-muted" style="font-size:.68rem;margin:.3rem 0;">鼠标停在「预览」上可看每条经历的得分。${esc(r.method)}</div>
        <div class="pd-actions"><button class="btn btn-primary btn-sm" onclick="askRectify()">💬 交给 AI 比对并补问</button></div>
    </div>`;
}

function askRectify() {
    closeModal('modal-rectify');
    _ensureChatOpen();
    sendMessage({ content: '反推时辰', action: { type: 'rectify' } });
}
