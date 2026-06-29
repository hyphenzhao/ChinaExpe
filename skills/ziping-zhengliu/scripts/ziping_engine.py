#!/usr/bin/env python3
"""
子平正解 - 八字排盘与流年分析核心引擎
基于《渊海子平》蒸馏笔记的知识规则库
"""

import datetime
import json
import sys

gan_list = ['甲', '乙', '丙', '丁', '戊', '己', '庚', '辛', '壬', '癸']
zhi_list = ['子', '丑', '寅', '卯', '辰', '巳', '午', '未', '申', '酉', '戌', '亥']
elements = ['木', '火', '土', '金', '水']

hidden_stems = {
    '子': ['癸'], '丑': ['己','癸','辛'], '寅': ['甲','丙','戊'],
    '卯': ['乙'], '辰': ['戊','乙','癸'], '巳': ['丙','庚','戊'],
    '午': ['丁','己'], '未': ['己','丁','乙'], '申': ['庚','壬','戊'],
    '酉': ['辛'], '戌': ['戊','辛','丁'], '亥': ['壬','甲'],
}

zhi_element = {
    '寅':'木','卯':'木','巳':'火','午':'火','辰':'土','戌':'土',
    '丑':'土','未':'土','申':'金','酉':'金','亥':'水','子':'水'
}

# 节气近似日期（公历）
jie_qi_approx = {
    '立春': (2, 4), '雨水': (2, 19),
    '惊蛰': (3, 6), '春分': (3, 21),
    '清明': (4, 5), '谷雨': (4, 20),
    '立夏': (5, 6), '小满': (5, 21),
    '芒种': (6, 6), '夏至': (6, 21),
    '小暑': (7, 7), '大暑': (7, 23),
    '立秋': (8, 8), '处暑': (8, 23),
    '白露': (9, 8), '秋分': (9, 23),
    '寒露': (10, 8), '霜降': (10, 23),
    '立冬': (11, 7), '小雪': (11, 22),
    '大雪': (12, 7), '冬至': (12, 22),
}

# 月令地支对应（节气后换月）
month_zhi_map = {
    1: '丑', 2: '寅', 3: '卯', 4: '辰', 5: '巳', 6: '午',
    7: '未', 8: '申', 9: '酉', 10: '戌', 11: '亥', 12: '子'
}


def get_elem(gan):
    return elements[gan_list.index(gan) // 2]


def get_yin_yang(gan):
    return gan_list.index(gan) % 2 == 0


def ten_god(dm, target):
    """计算十神关系"""
    dm_idx = gan_list.index(dm)
    t_idx = gan_list.index(target)
    if t_idx == dm_idx:
        return '比肩' if get_yin_yang(dm) == get_yin_yang(target) else '劫财'
    dm_elem = dm_idx // 2
    t_elem = t_idx // 2
    same_yy = get_yin_yang(dm) == get_yin_yang(target)
    if (t_elem + 1) % 5 == dm_elem:
        return '正印' if same_yy else '偏印'
    if (dm_elem + 1) % 5 == t_elem:
        return '食神' if same_yy else '伤官'
    if (t_elem + 2) % 5 == dm_elem:
        return '正官' if not same_yy else '七杀'
    if (dm_elem + 2) % 5 == t_elem:
        return '正财' if not same_yy else '偏财'
    return '?'


def calculate_four_pillars(year, month, day, hour=12):
    """
    排四柱八字（简化版，非天文精确）
    使用1900-01-01 = 甲戌日为参考
    """
    ref = datetime.date(1900, 1, 1)
    target = datetime.date(year, month, day)
    days_diff = (target - ref).days

    # 日柱
    day_gan = gan_list[(0 + days_diff) % 10]
    day_zhi = zhi_list[(10 + days_diff) % 12]

    # 年柱（以立春为界，简化处理：2月4日前算上一年）
    calc_year = year
    if month < 2 or (month == 2 and day < 4):
        calc_year -= 1
    year_offset = calc_year - 1984  # 1984 = 甲子年
    year_gan = gan_list[(0 + year_offset) % 10]
    year_zhi = zhi_list[(0 + year_offset) % 12]

    # 月柱（简化版，以节气为界）
    month_zhi = month_zhi_map[month]
    # 月干根据年干推算
    year_gan_idx = gan_list.index(year_gan)
    month_gan_start_map = {0: '丙', 1: '戊', 2: '庚', 3: '壬', 4: '甲'}
    month_gan_start = month_gan_start_map[year_gan_idx % 5]
    month_gan_idx_base = gan_list.index(month_gan_start)
    # 寅月=正月，对应month_zhi_map中2月=寅
    month_offset = (month_zhi_list.index(month_zhi) - 2) % 12
    month_gan = gan_list[(month_gan_idx_base + month_offset) % 10]

    # 时柱
    hour_zhi_idx = hour_to_zhi_index(hour)
    hour_zhi = zhi_list[hour_zhi_idx]
    day_gan_idx = gan_list.index(day_gan)
    hour_stem_start_map = {0: '甲', 1: '丙', 2: '戊', 3: '庚', 4: '壬'}
    hour_stem_start = hour_stem_start_map[day_gan_idx % 5]
    hour_stem_idx_base = gan_list.index(hour_stem_start)
    hour_gan = gan_list[(hour_stem_idx_base + hour_zhi_idx) % 10]

    return {
        'year': f"{year_gan}{year_zhi}",
        'month': f"{month_gan}{month_zhi}",
        'day': f"{day_gan}{day_zhi}",
        'hour': f"{hour_gan}{hour_zhi}",
        'year_gan': year_gan, 'year_zhi': year_zhi,
        'month_gan': month_gan, 'month_zhi': month_zhi,
        'day_gan': day_gan, 'day_zhi': day_zhi,
        'hour_gan': hour_gan, 'hour_zhi': hour_zhi,
        'dm': day_gan,
    }


month_zhi_list = ['子', '丑', '寅', '卯', '辰', '巳', '午', '未', '申', '酉', '戌', '亥']


def hour_to_zhi_index(hour):
    """时辰对应地支索引"""
    # 子时23-1, 丑时1-3, ..., 申时15-17, 酉时17-19, ...
    if hour >= 23 or hour < 1:
        return 0   # 子
    elif hour < 3:
        return 1   # 丑
    elif hour < 5:
        return 2   # 寅
    elif hour < 7:
        return 3   # 卯
    elif hour < 9:
        return 4   # 辰
    elif hour < 11:
        return 5   # 巳
    elif hour < 13:
        return 6   # 午
    elif hour < 15:
        return 7   # 未
    elif hour < 17:
        return 8   # 申
    elif hour < 19:
        return 9   # 酉
    elif hour < 21:
        return 10  # 戌
    else:
        return 11  # 亥


def analyze_chart(pillars, gender='male'):
    """基于蒸馏笔记的规则库进行命理分析"""
    dm = pillars['dm']
    results = {}

    # 1. 十神分析
    stem_tengshen = {}
    for name, gan in [('year', pillars['year_gan']), ('month', pillars['month_gan']), ('hour', pillars['hour_gan'])]:
        stem_tengshen[name] = ten_god(dm, gan)

    hidden_tengshen = {}
    for name, zhi in [('year', pillars['year_zhi']), ('month', pillars['month_zhi']),
                       ('day', pillars['day_zhi']), ('hour', pillars['hour_zhi'])]:
        stems = hidden_stems.get(zhi, [])
        hidden_tengshen[name] = [(s, ten_god(dm, s)) for s in stems]

    results['stem_tengshen'] = stem_tengshen
    results['hidden_tengshen'] = hidden_tengshen

    # 2. 日主强弱
    all_stems = [pillars['year_gan'], pillars['month_gan'], pillars['hour_gan']]
    all_hidden = []
    for z in [pillars['year_zhi'], pillars['month_zhi'], pillars['day_zhi'], pillars['hour_zhi']]:
        all_hidden.extend(hidden_stems.get(z, []))

    dm_elem = get_elem(dm)
    # 得令检查
    month_elem = zhi_element[pillars['month_zhi']]
    de_ling = (dm_elem == month_elem)

    # 帮扶 vs 克泄耗
    stats = {'正印':0, '偏印':0, '比肩':0, '劫财':0,
             '正财':0, '偏财':0, '食神':0, '伤官':0,
             '正官':0, '七杀':0}
    for s in all_stems + all_hidden:
        tg = ten_god(dm, s)
        if tg in stats:
            stats[tg] += 1

    support = stats['正印'] + stats['偏印'] + stats['比肩'] + stats['劫财']
    weaken = stats['正财'] + stats['偏财'] + stats['食神'] + stats['伤官'] + stats['正官'] + stats['七杀']

    if support > weaken:
        strength = '偏旺'
    elif support < weaken:
        strength = '偏弱'
    else:
        strength = '中和'

    results['strength'] = strength
    results['de_ling'] = de_ling
    results['stats'] = stats

    # 3. 用神忌神
    if strength == '偏旺':
        results['yong_shen'] = ['食神', '伤官', '正财', '偏财']
        results['ji_shen'] = ['正印', '偏印', '比肩', '劫财']
    elif strength == '偏弱':
        results['yong_shen'] = ['正印', '偏印', '比肩', '劫财']
        results['ji_shen'] = ['食神', '伤官', '正财', '偏财']
    else:
        results['yong_shen'] = []
        results['ji_shen'] = []

    # 4. 格局判断
    # 简单判断：看月支藏干是否有透到天干的
    month_hidden = hidden_stems.get(pillars['month_zhi'], [])
    geju = None
    for s in month_hidden:
        tg = ten_god(dm, s)
        if tg in ['正官', '七杀', '正财', '偏财', '正印', '偏印', '食神', '伤官']:
            if s in [pillars['year_gan'], pillars['month_gan'], pillars['hour_gan']]:
                geju = tg
                break
    if not geju:
        # 默认取月令本气
        main_stem = month_hidden[0] if month_hidden else '?'
        geju = ten_god(dm, main_stem)

    results['geju'] = geju

    # 5. 事业方向推断
    career_advice = get_career_advice(results)
    results['career'] = career_advice

    # 6. 财富层次
    wealth = get_wealth_level(results)
    results['wealth'] = wealth

    # 7. 健康重点
    health = get_health_analysis(pillars, results)
    results['health'] = health

    return results


def get_career_advice(results):
    geju = results['geju']
    stem_ts = results['stem_tengshen']

    advices = []
    if geju in ['七杀', '正官']:
        advices.append('管理/军警/司法（官杀格传统路径）')
        advices.append('法律/咨询/顾问（官杀格决断力）')
    if stem_ts.get('month') in ['伤官', '食神']:
        advices.append('技术/创意/表达类（食伤才华型）')
        advices.append('技术型管理/工程师/IT')
    if stem_ts.get('hour') in ['正财', '偏财']:
        advices.append('商业/创业/投资（财星透时）')

    if not advices:
        advices.append('需结合完整命盘分析')

    return advices


def get_wealth_level(results):
    stats = results['stats']
    cai_count = stats['正财'] + stats['偏财']
    strength = results['strength']

    level = '中等'
    if cai_count >= 3 and strength in ['偏旺', '中和']:
        level = '中产偏上'
    elif cai_count >= 2 and strength == '偏旺':
        level = '中产偏上'
    elif cai_count >= 4:
        level = '富裕'
    elif cai_count <= 1:
        level = '普通'

    return {'level': level, 'cai_count': cai_count}


def get_health_analysis(pillars, results):
    dm = pillars['dm']
    dm_elem = get_elem(dm)
    issues = []

    # 检查五行失衡
    all_elems = [get_elem(g) for g in [pillars['year_gan'], pillars['month_gan'], pillars['hour_gan']]]
    all_elems.append(dm_elem)

    elem_count = {}
    for e in all_elems:
        elem_count[e] = elem_count.get(e, 0) + 1

    if elem_count.get('火', 0) >= 2 and '金' == dm_elem:
        issues.append('呼吸系统/肺部（火克金）')
        issues.append('眼睛/视力（水火相激）')
    if elem_count.get('水', 0) <= 1:
        issues.append('肾脏/泌尿系统（水弱）')
    if '木' in all_elems:
        issues.append('肝胆/腰背（金木相克）')

    return issues


def calculate_da_yun(pillars, gender='male', start_year=2026):
    """排大运"""
    year_gan = pillars['year_gan']
    month_gan_idx = gan_list.index(pillars['month_gan'])
    month_zhi_idx = zhi_list.index(pillars['month_zhi'])

    is_yang = get_yin_yang(year_gan)
    forward = (gender == 'male' and is_yang) or (gender == 'female' and not is_yang)

    # 起运年龄（简化：约10岁起运）
    start_age = 10

    da_yun = []
    for i in range(8):
        if forward:
            g = (month_gan_idx + 1 + i) % 10
            z = (month_zhi_idx + 1 + i) % 12
        else:
            g = (month_gan_idx - 1 - i) % 10
            z = (month_zhi_idx - 1 - i) % 12

        gz = f"{gan_list[g]}{zhi_list[z]}"
        age = start_age + i * 10
        year_start = start_year + (age - (start_year - 2026))
        year_start = start_year + (start_age - (start_year - 2026)) + i * 10

        da_yun.append({
            'pillar': gz,
            'gan': gan_list[g],
            'zhi': zhi_list[z],
            'age': age,
            'year_start': year_start,
            'year_end': year_start + 9,
            'stem_tengshen': ten_god(pillars['dm'], gan_list[g]),
        })

    return da_yun


def calculate_liu_nian(da_yun, pillars, start_year=2026):
    """计算流年"""
    dm = pillars['dm']
    # 2024 = 甲辰
    ref_year = 2024
    ref_gan_idx = 0  # 甲
    ref_zhi_idx = 4  # 辰

    chong_map = {'子':'午','午':'子','卯':'酉','酉':'卯','辰':'戌','戌':'辰',
                 '巳':'亥','亥':'巳','寅':'申','申':'寅','丑':'未','未':'丑'}

    all_liu_nian = []
    for dy in da_yun:
        for year in range(dy['year_start'], dy['year_end'] + 1):
            gan_idx = (ref_gan_idx + (year - ref_year)) % 10
            zhi_idx = (ref_zhi_idx + (year - ref_year)) % 12
            ln_gz = f"{gan_list[gan_idx]}{zhi_list[zhi_idx]}"

            events = []
            tg_gan = ten_god(dm, gan_list[gan_idx])
            ln_zhi = zhi_list[zhi_idx]

            # 断语匹配
            if tg_gan == '正官':
                events.append('伤官见官：职场冲突/口舌是非')
            elif tg_gan == '七杀':
                events.append('逢杀看印：压力增大但有升职机会')
            elif tg_gan == '伤官':
                events.append('伤官流年：才华发挥，忌见正官')
            elif tg_gan == '食神':
                events.append('食神有气胜财官：口福才华期')
            elif tg_gan in ['正财', '偏财']:
                events.append(f'{tg_gan}运：利求财/婚恋')
            elif tg_gan in ['比肩', '劫财']:
                events.append('比劫：竞争加剧/注意破财')
            elif tg_gan in ['正印', '偏印']:
                events.append(f'{tg_gan}：利学习考试')

            # 地支冲
            if ln_zhi in chong_map:
                events.append(f'冲{chong_map[ln_zhi]}：注意相关事项')

            all_liu_nian.append({
                'year': year,
                'gz': ln_gz,
                'age': year - start_year,
                'da_yun': dy['pillar'],
                'stem_tengshen': tg_gan,
                'events': events,
            })

    return all_liu_nian


def full_analysis(year, month, day, hour=12, gender='male'):
    """完整分析流程"""
    pillars = calculate_four_pillars(year, month, day, hour)
    analysis = analyze_chart(pillars, gender)
    da_yun = calculate_da_yun(pillars, gender, year)
    liu_nian = calculate_liu_nian(da_yun, pillars, year)

    return {
        'pillars': pillars,
        'analysis': analysis,
        'da_yun': da_yun,
        'liu_nian': liu_nian,
    }


if __name__ == '__main__':
    # Test
    result = full_analysis(2026, 5, 6, 16, 'male')
    print(json.dumps(result, ensure_ascii=False, indent=2))
