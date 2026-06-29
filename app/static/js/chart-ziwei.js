/* ===== Ziwei Doushu 12-Palace Interactive Grid ===== */

// Star categories for coloring
const STAR_CATEGORY = {
    zhu: ['紫微','天机','太阳','武曲','天同','廉贞','天府','太阴','贪狼','巨门','天相','天梁','七杀','破军'],
    fu: ['文昌','文曲','左辅','右弼','天魁','天钺','禄存','天马','台辅','封诰','龙池','凤阁','三台','八座','恩光','天贵','天官','天福','天厨','天巫','解神','天德','月德','博士','力士','青龙','小耗','将军','奏书','飞廉','喜神','病符','大耗','伏兵','官府'],
    sha: ['擎羊','陀罗','火星','铃星','地空','地劫','天空','截空','旬空','天刑','天姚','阴煞','天伤','天使','蜚廉','破碎'],
    za: ['红鸾','天喜','咸池','沐浴','长生','冠带','临官','帝旺','衰','病','死','墓','绝','胎','养','大耗','小耗','孤辰','寡宿','华盖','白虎','天哭','天虚','岁破','龙德','岁驿','攀鞍','将星','亡神','贯索','晦气','丧门','吊客','息神','劫煞','灾煞','月煞'],
};

function _starCat(name) {
    if (STAR_CATEGORY.zhu.includes(name)) return 'zhu';
    if (STAR_CATEGORY.fu.includes(name)) return 'fu';
    if (STAR_CATEGORY.sha.includes(name)) return 'sha';
    return 'za';
}

function _renderStarTag(s, max) {
    const cat = _starCat(s.name);
    const nameTag = `<span class="star-tag star-cat-${cat}" title="${s.name}">${s.name}</span>`;
    let extraTags = '';
    if (s.brightness && s.brightness !== '—') {
        const b = s.brightness;
        const bIdx = ['庙','旺','得','利','平','不','陷'].indexOf(b);
        const bCls = bIdx >= 0 ? `brightness-${bIdx}` : '';
        extraTags += `<span class="star-tag star-brightness ${bCls}" title="亮度:${b}">${b}</span>`;
    }
    if (s.transform) {
        const t = s.transform;
        const tCls = { '禄':'sihua-lu','权':'sihua-quan','科':'sihua-ke','忌':'sihua-ji' }[t] || '';
        extraTags += `<span class="star-tag star-sihua ${tCls}" title="化${t}">${t}</span>`;
    }
    if (max && s._more) {
        extraTags += `<span class="star-tag star-more">+${s._more}</span>`;
    }
    return `<span class="star-row">${nameTag}${extraTags}</span>`;
}

function renderZiweiGrid(data) {
    const chartDisplay = document.getElementById('chart-display');
    if (!chartDisplay) return;
    chartDisplay.classList.remove('hidden');

    if (!data || !data.palaces) {
        chartDisplay.innerHTML = '<div class="empty-state">命盘数据不完整</div>';
        return;
    }

    let html = '<div class="chart-section-title">🔮 紫微斗数 · ' + (data.display_name || data.person) + '</div>';
    html += '<div class="ziwei-grid">';

    for (let row = 0; row < 4; row++) {
        for (let col = 0; col < 4; col++) {
            const palace = data.palaces.find(p => p.grid_row === row && p.grid_col === col);
            if (!palace) continue;

            if (palace.is_empty) {
                html += '<div class="ziwei-palace empty"></div>';
            } else {
                let classes = 'ziwei-palace';
                if (palace.shen_gong_here) classes += ' shen-gong';
                if (palace.lai_yin_here) classes += ' lai-yin';

                const MAX = 5;
                let stars = palace.stars.slice(0, MAX);
                if (palace.stars.length > MAX) {
                    stars = stars.concat([{ name: '…', brightness: null, transform: null, _more: palace.stars.length - MAX }]);
                }
                if (palace.stars.length === 0) {
                    stars = [{ name: '—', brightness: null, transform: null }];
                }
                let starsHtml = stars.map(s => _renderStarTag(s)).join('');

                let markersHtml = '';
                if (palace.lai_yin_here) markersHtml += '<span class="palace-laiyin-marker">来因</span>';
                if (palace.shen_gong_here) markersHtml += '<span class="palace-shen-marker">身宫</span>';
                if (palace.markers && palace.markers.length > 0 && !palace.shen_gong_here && !palace.lai_yin_here) {
                    markersHtml += `<span class="palace-marker">${palace.markers[0]}</span>`;
                }

                html += `<div class="${classes}" onclick="openPalaceDetail('${palace.name}', '${palace.stem_branch}', ${row}, ${col})">
                    ${markersHtml}
                    <div class="palace-name">${palace.name}</div>
                    <div class="palace-stem-branch">${palace.stem_branch}</div>
                    <div class="palace-stars">${starsHtml}</div>
                </div>`;
            }
        }
    }
    html += '</div>';
    chartDisplay.innerHTML = html;
}

function openPalaceDetail(name, stemBranch, row, col) {
    // Add palace to context
    AppState.selectedContext = {
        ...AppState.selectedContext,
        palace: name,
        stem_branch: stemBranch,
    };
    updateContextTags();

    // Find the palace data
    const palace = AppState.ziweiData.palaces.find(
        p => p.name === name && p.stem_branch === stemBranch
    );
    if (!palace) return;

    // Build modal content
    const modal = document.getElementById('modal-palace');
    document.getElementById('modal-palace-title').textContent = `${name} · ${stemBranch}`;

    let body = '<div class="palace-detail">';

    // Palace info badges
    body += '<div class="palace-info-badges">';
    if (palace.changsheng) {
        body += `<span class="palace-badge">长生: ${palace.changsheng}</span>`;
    }
    if (palace.major_limit) {
        body += `<span class="palace-badge">大限: ${palace.major_limit}</span>`;
    }
    if (palace.shen_gong_here) {
        body += '<span class="palace-badge" style="color:var(--accent-purple)">身宫</span>';
    }
    if (palace.lai_yin_here) {
        body += '<span class="palace-badge" style="color:var(--accent-gold)">来因宫</span>';
    }
    body += '</div>';

    // Stars list with category/brightness/sihua tags
    body += '<div class="stars-list">';
    if (palace.stars.length === 0) {
        body += '<div class="empty-state">此宫无星曜</div>';
    } else {
        palace.stars.forEach(s => {
            const cat = _starCat(s.name);
            let bCls = '', bLabel = '';
            if (s.brightness && s.brightness !== '—') {
                const bIdx = ['庙','旺','得','利','平','不','陷'].indexOf(s.brightness);
                bCls = bIdx >= 0 ? `brightness-${bIdx}` : '';
                bLabel = s.brightness;
            }
            let tCls = '', tLabel = '';
            if (s.transform) {
                tCls = { '禄':'sihua-lu','权':'sihua-quan','科':'sihua-ke','忌':'sihua-ji' }[s.transform] || '';
                tLabel = s.transform;
            }
            body += `<div class="star-item" onclick="selectStar('${s.name}', '${s.brightness || ''}', '${s.transform || ''}')">
                <span class="star-row">
                    <span class="star-tag star-cat-${cat} star-tag-lg">${s.name}</span>
                    ${bLabel ? `<span class="star-tag star-brightness star-tag-lg ${bCls}">${bLabel}</span>` : ''}
                    ${tLabel ? `<span class="star-tag star-sihua star-tag-lg ${tCls}">${tLabel}</span>` : ''}
                </span>
                <span style="color:var(--text-muted);font-size:0.7rem;">↗ 提问</span>
            </div>`;
        });
    }
    body += '</div>';
    body += '</div>';

    document.getElementById('modal-palace-body').innerHTML = body;
    openModal('modal-palace');
}

function selectStar(starName, brightness, transform) {
    // Set context
    AppState.selectedContext = {
        ...AppState.selectedContext,
        star: starName,
        brightness: brightness || undefined,
        transform: transform || undefined,
    };
    updateContextTags();

    // Close modal
    closeModal('modal-palace');

    // Focus the input
    document.getElementById('message-input').focus();
}
