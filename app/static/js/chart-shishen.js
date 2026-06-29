/* ===== ShiShen (Ten Gods / Bazi) Four-Pillar Interactive Display ===== */

function renderShiShenDisplay(data) {
    const chartDisplay = document.getElementById('chart-display');
    chartDisplay.classList.remove('hidden');

    if (!data || !data.pillars) {
        chartDisplay.innerHTML = '<div class="empty-state">命盘数据不完整</div>';
        return;
    }

    let html = '<div class="chart-section-title">🪷 十神·子平命理 · ' + (data.display_name || data.person);
    if (data.day_master) {
        html += ' · 日主: ' + data.day_master;
    }
    html += '</div>';

    html += '<div class="shishen-display">';

    data.pillars.forEach(pillar => {
        const hs = pillar.heavenly_stem;
        const eb = pillar.earthly_branch;
        const hidden = pillar.hidden_stems || [];

        html += `
            <div class="shishen-pillar">
                <div class="pillar-header">${pillar.pillar}</div>
                <div class="pillar-body">
                    <!-- Heavenly Stem -->
                    <div class="pillar-row">
                        <span class="pillar-row-label">天干</span>
                        <div class="heavenly-stem" onclick="selectShiShenStem('${pillar.pillar}', '${hs.stem}', '${hs.shishen || ''}', event)" title="点击提问">
                            ${hs.stem}
                            ${hs.shishen ? `<span class="stem-shishen-tag">${hs.shishen}</span>` : ''}
                        </div>
                    </div>

                    <!-- Earthly Branch -->
                    <div class="pillar-row">
                        <span class="pillar-row-label">地支</span>
                        <span class="earthly-branch">${eb.branch}</span>
                    </div>

                    <!-- Hidden Stems -->
                    <div class="pillar-row">
                        <span class="pillar-row-label">藏干</span>
                        <div class="hidden-stems">
                            ${hidden.map(h => `
                                <div class="hidden-stem-item" onclick="selectHiddenStem('${pillar.pillar}', '${h.stem}', '${h.shishen || ''}', event)" title="点击提问">
                                    <span class="hidden-stem-text">${h.stem}</span>
                                    ${h.shishen ? `<span class="hidden-stem-shishen">${h.shishen}</span>` : ''}
                                </div>
                            `).join('')}
                        </div>
                    </div>

                    <!-- Extras -->
                    <div class="pillar-extras">
                        ${pillar.nayin ? `纳音: ${pillar.nayin}` : ''}
                        ${pillar.kongwang ? ` 空亡: ${pillar.kongwang}` : ''}
                        ${pillar.dishi ? ` 地势: ${pillar.dishi}` : ''}
                    </div>
                </div>
            </div>`;
    });

    html += '</div>';
    chartDisplay.innerHTML = html;
}

function selectShiShenStem(pillar, stem, shishen, event) {
    event.stopPropagation();
    AppState.selectedContext = {
        pillar: pillar,
        stem: stem,
        shishen: shishen || undefined,
        source: '天干',
    };
    updateContextTags();
    document.getElementById('message-input').focus();
}

function selectHiddenStem(pillar, stem, shishen, event) {
    event.stopPropagation();
    AppState.selectedContext = {
        pillar: pillar,
        stem: stem,
        shishen: shishen || undefined,
        source: '藏干',
    };
    updateContextTags();
    document.getElementById('message-input').focus();
}
