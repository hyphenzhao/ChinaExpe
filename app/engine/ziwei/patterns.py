"""紫微斗数格局：只判「成格方向」，不判破格。纯代码，不接 AI。

规则取自紫微斗数全书卷一（定富局、定贵局、定贫贱局、定杂局）与中州/三合通行口径，
开源 x-iztro 的规则集作参照。文墨天机没有公开格局清单，这里不宣称与其一致。
每条命中都附上三方四正与夹宫里的煞、忌、空、陷等「事实」，由 AI 去评估破格程度。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional

from .view import BRIGHT, DARK, KONG, LIUHE, SHA, ChartView, from_astrolabe

VERSION = "zw-geju-1"


@dataclass
class Rule:
    id: str
    name: str
    kind: str                       # 吉 | 凶
    group: str                      # 主星格 | 日月格 | 辅佐格 | 四化格 | 夹格 | 煞格
    check: Callable[[ChartView, int], Optional[list[str]]]
    note: str = ""
    aliases: tuple = ()
    also_body: bool = False         # 身宫也按同样条件检查
    supersedes: tuple = ()          # 命中本条时隐藏这些较弱的规则


# ------------------------------------------------------------------ helpers
def _br(v: ChartView, i: int) -> str:
    return v.branch(i)


def _in_ming(v: ChartView, m: int, *stars: str, branches: str = "", borrow: bool = True) -> Optional[list[str]]:
    """命宫（无主星时借对宫）同时有这些星，且地支在 branches 内。"""
    pool = set(v.stars(m)) | set(v.majors(m, borrow=borrow))
    if not all(s in pool for s in stars):
        return None
    if branches and _br(v, m) not in branches:
        return None
    ev = [f"{'、'.join(stars)}在命宫({_br(v, m)})"]
    if borrow and not v.majors(m) and any(s in v.majors(m, borrow=True) for s in stars):
        ev.append("命宫无主星，借迁移宫主星")
    return ev


def _pair_at(v: ChartView, a: str, b: str, i: int, j: int) -> bool:
    """a、b 两星分别位于 i、j 两宫（顺序不限）。"""
    wa, wb = v.where(a), v.where(b)
    return {wa, wb} == {i % 12, j % 12} and wa != wb


def _in_sfsz(v: ChartView, m: int, *stars: str) -> bool:
    return v.has(v.sfsz(m), *stars)


def _lu_in(v: ChartView, idxs) -> list[str]:
    idxs = [idxs] if isinstance(idxs, int) else idxs
    out = []
    if v.where("禄存") in idxs:
        out.append("禄存")
    if v.hua_where("禄") in idxs:
        out.append(f"{v.hua_star('禄')}化禄")
    return out


def _hua_in(v: ChartView, idxs, hua: str) -> Optional[str]:
    idxs = [idxs] if isinstance(idxs, int) else idxs
    w = v.hua_where(hua)
    return f"{v.hua_star(hua)}化{hua}" if w is not None and w in idxs else None


def _jia_pair(v: ChartView, m: int, a: str, b: str) -> Optional[list[str]]:
    l, r = v.jia(m)
    if (a in v.stars(l) and b in v.stars(r)) or (b in v.stars(l) and a in v.stars(r)):
        return [f"{a}、{b}分居{v.name(l)}与{v.name(r)}，夹命"]
    return None


# ------------------------------------------------------------------ 吉格
def r_zifu_tonggong(v, m):
    return _in_ming(v, m, "紫微", "天府", branches="寅申")


def r_zifu_chaoyuan(v, m):
    """紫微、天府从命宫之外的三方四正朝照；命宫坐紫微或天府者不论此格。"""
    if v.any_of(m, ("紫微", "天府")) or not _in_sfsz(v, m, "紫微", "天府"):
        return None
    return [f"紫微在{v.name(v.where('紫微'))}、天府在{v.name(v.where('天府'))}，会照命宫三方四正"]


def r_tianfu_chaoyuan(v, m):
    if _br(v, m) == "戌" and v.majors(m) == ["天府"]:
        return ["天府独坐命宫戌"]
    return None


def r_junchen(v, m):
    """宽口径：紫微坐命，左辅或右弼至少一颗在三方四正，或左右夹命。"""
    if "紫微" not in v.stars(m):
        return None
    fu = v.any_of(v.sfsz(m), ("左辅", "右弼"))
    if fu:
        return ["紫微坐命", f"{'、'.join(fu)}会于三方四正"]
    if _jia_pair(v, m, "左辅", "右弼"):
        return ["紫微坐命", "左辅右弼夹命"]
    return None


def r_jixiang_liming(v, m):
    return _in_ming(v, m, "紫微", branches="午", borrow=False)


def r_fuxiang_chaoyuan(v, m):
    """宽口径：天府、天相于命宫三方四正会照（含坐命）。狭义为命无主星、府相分居官禄与财帛。"""
    if not _in_sfsz(v, m, "天府", "天相"):
        return None
    ev = [f"天府在{v.name(v.where('天府'))}、天相在{v.name(v.where('天相'))}，会于命宫三方四正"]
    if _pair_at(v, "天府", "天相", v.at(m, "官"), v.at(m, "财")) and not v.majors(m):
        ev.append("命无主星、府相分居财官，合狭义正格")
    return ev


def r_jiyue_tongliang(v, m):
    if _in_sfsz(v, m, "天机", "太阴", "天同", "天梁"):
        return ["天机、太阴、天同、天梁齐会命宫三方四正"]
    return None


def r_shapolang(v, m):
    hit = [s for s in ("七杀", "破军", "贪狼") if s in v.majors(m, borrow=True)]
    if not hit:
        return None
    if not v.majors(m):
        return [f"命宫无主星，借迁移宫{'、'.join(hit)}"]
    return [f"{'、'.join(hit)}坐命"]


def r_qisha_chaodou(v, m):
    b = _br(v, m)
    if "七杀" in v.stars(m) and b in "子午寅申":
        return [f"七杀坐命{b}（本系统：午申为朝斗，子寅为仰斗）"]
    return None


def r_riyue_bingming(v, m):
    """日月会于三方四正，且太阳巳/太阴酉或太阳辰/太阴戌（日月皆旺）。"""
    sf = v.sfsz(m)
    if not v.has(sf, "太阳", "太阴"):
        return None
    pos = (v.branch(v.where("太阳")), v.branch(v.where("太阴")))
    if pos in (("巳", "酉"), ("辰", "戌")):
        return [f"太阳在{pos[0]}、太阴在{pos[1]}，皆旺，会于三方四正"]
    if v.brightness("太阳") in BRIGHT and v.brightness("太阴") in BRIGHT:
        return ["太阳、太阴皆庙旺，会于命宫三方四正"]
    return None


def r_danchi_guichi(v, m):
    b = _br(v, m)
    if "太阳" in v.stars(m) and b in "辰巳":
        return [f"太阳坐命于{b}（丹墀）"]
    if "太阴" in v.stars(m) and b in "酉戌":
        return [f"太阴坐命于{b}（桂墀）"]
    return None


def r_rizhao_leimen(v, m):
    """太阳坐命于卯（日出扶桑）；与天梁同宫为日照雷门正格。"""
    ev = _in_ming(v, m, "太阳", branches="卯", borrow=False)
    if ev and "天梁" in v.stars(m):
        ev.append("太阳天梁同宫，合日照雷门正格")
    return ev


def r_erya_tonglin(v, m):
    """命宫丑或未无主星，日月在对宫照命。"""
    o = v.at(m, "迁")
    if _br(v, m) in "丑未" and not v.majors(m) and v.has(o, "太阳", "太阴"):
        return [f"命宫{_br(v, m)}无主星，太阳太阴在对宫{v.branch(o)}照命"]
    return None


def r_jincan_guanghui(v, m):
    return _in_ming(v, m, "太阳", branches="午", borrow=False)


def r_yuelang_tianmen(v, m):
    return _in_ming(v, m, "太阴", branches="亥", borrow=False)


def r_shuicheng_guie(v, m):
    return _in_ming(v, m, "太阴", branches="子", borrow=False)


def r_yuesheng_canghai(v, m):
    return _in_ming(v, m, "天同", "太阴", branches="子", borrow=False)


def r_mingzhu_chuhai(v, m):
    if _br(v, m) != "未" or v.majors(m):
        return None
    sun, moon = v.where("太阳"), v.where("太阴")
    if sun is not None and moon is not None and v.branch(sun) == "卯" and v.branch(moon) == "亥":
        return ["命宫未宫无主星", "太阳在卯、太阴在亥，拱照命宫"]
    return None


def r_riyue_jiaming(v, m):
    return _jia_pair(v, m, "太阳", "太阴")


def r_riyue_tonggong(v, m):
    return _in_ming(v, m, "太阳", "太阴", branches="丑未", borrow=False)


def r_riyue_zhaobi(v, m):
    t = v.at(m, "田")
    return ["太阳、太阴同在田宅宫"] if v.has(t, "太阳", "太阴") else None


def r_shizhong_yinyu(v, m):
    return _in_ming(v, m, "巨门", branches="子午", borrow=False)


def r_juri_tonggong(v, m):
    return _in_ming(v, m, "太阳", "巨门", branches="寅申", borrow=False)


def r_jiju_tonglin(v, m):
    """巨门天机坐命卯或酉，无化忌同宫（酉宫见忌另归巨机化酉）。"""
    ev = _in_ming(v, m, "天机", "巨门", branches="卯酉", borrow=False)
    if ev and _hua_in(v, m, "忌"):
        return None
    return ev


def r_shanyin_chaogang(v, m):
    return _in_ming(v, m, "天机", "天梁", branches="辰戌", borrow=False)


def r_wenliang_zhenji(v, m):
    if "天梁" in v.stars(m) and v.any_of(m, ("文昌", "文曲")):
        return ["天梁与" + "、".join(v.any_of(m, ("文昌", "文曲"))) + "同坐命宫"]
    return None


def r_lianzhen_wenwu(v, m):
    if "廉贞" in v.stars(m) and "武曲" in v.stars(v.at(m, "官")) and v.any_of(v.sfsz(m), ("文昌", "文曲")):
        return ["廉贞坐命，官禄宫武曲", "三方见" + "、".join(v.any_of(v.sfsz(m), ("文昌", "文曲")))]
    return None


def r_huaxing_fangui(v, m):
    b = _br(v, m)
    if "天同" in v.stars(m) and b == "戌" and v.year_stem == "丁":
        return ["天同坐命戌，丁年生（天同化权、太阴化禄、天机化科）"]
    if "巨门" in v.stars(m) and b == "辰" and v.year_stem == "辛":
        return ["巨门坐命辰，辛年生（巨门化禄）"]
    return None


def r_yangliang_changlu(v, m):
    sf = v.sfsz(m)
    lu = _lu_in(v, sf)
    if v.has(sf, "太阳", "天梁", "文昌") and lu:
        ev = ["太阳、天梁、文昌会于三方四正", "禄见" + "、".join(lu)]
        if "禄存" not in lu:
            ev.append("以化禄代禄存，属宽口径")
        return ev
    return None


def r_shouxing_rumiao(v, m):
    return _in_ming(v, m, "天梁", branches="午", borrow=False)


def r_yingxing_rumiao(v, m):
    return _in_ming(v, m, "破军", branches="子午", borrow=False)


def r_matou_daijian(v, m):
    """宽口径：擎羊坐命于午。正格为天同太阴或贪狼同宫、丙戊年生。"""
    if _br(v, m) != "午" or "擎羊" not in v.stars(m):
        return None
    majors = v.majors(m, borrow=True)
    ev = ["擎羊坐命于午" + ("，与" + "、".join(majors) + "同宫" if majors else "")]
    if {"天同", "太阴"} & set(majors) or "贪狼" in majors:
        ev.append("同阴或贪狼同宫，合正格")
    return ev


def r_qingyang_rumiao(v, m):
    if "擎羊" in v.stars(m) and _br(v, m) in "丑辰未戌":
        return [f"擎羊坐命于{_br(v, m)}（四墓入庙）"]
    return None


def _huo_ling_tan(v, m, sha):
    if "贪狼" not in v.majors(m, borrow=True):
        return None
    if sha in v.stars(m):
        return [f"贪狼与{sha}同坐命宫"]
    if _in_sfsz(v, m, sha):
        return [f"贪狼坐命，{sha}在三方四正"]
    return None


def r_huotan(v, m):
    return _huo_ling_tan(v, m, "火星")


def r_lingtan(v, m):
    return _huo_ling_tan(v, m, "铃星")


def r_huolingtan(v, m):
    a, b = _huo_ling_tan(v, m, "火星"), _huo_ling_tan(v, m, "铃星")
    return (a + b) if a and b else None


def r_tanwu(v, m):
    return _in_ming(v, m, "武曲", "贪狼", branches="丑未", borrow=False)


def r_jiangxing_dedi(v, m):
    """武曲坐命于辰戌（通行软件口径）；一说武曲庙旺守命即是。"""
    if "武曲" in v.stars(m) and _br(v, m) in "辰戌":
        return [f"武曲坐命于{_br(v, m)}"]
    return None


def r_xiongsu_chaoyuan(v, m):
    """廉贞坐命寅申（独坐为上）；另有廉贞在未申守命称权星朝垣之说。"""
    b = _br(v, m)
    if "廉贞" in v.stars(m) and b in "寅申":
        return [f"廉贞坐命于{b}" + ("，独坐" if v.majors(m) == ["廉贞"] else "")]
    return None


def r_luma_jiaochi(v, m):
    sf = v.sfsz(m)
    lu = _lu_in(v, sf)
    if "天马" in [s for i in sf for s in v.stars(i)] and lu:
        return ["天马与" + "、".join(lu) + "会于命宫三方四正"]
    return None


def r_luma_peiyin(v, m):
    return ["禄存、天马、天相同坐命宫"] if v.has(m, "禄存", "天马", "天相") else None


def r_shuanglu(v, m):
    sf = v.sfsz(m)
    lu = _lu_in(v, sf)
    return ["禄存与化禄齐会三方四正（" + "、".join(lu) + "）"] if len(lu) == 2 else None


def r_luhe_yuanyang(v, m):
    lu = _lu_in(v, [m])
    return ["禄存与化禄同坐命宫"] if len(lu) == 2 else None


def r_minglu_anlu(v, m):
    lu_m = _lu_in(v, [m])
    if len(lu_m) != 1:
        return None
    partner = next((p.index for p in v.palaces if p.branch == LIUHE[_br(v, m)]), None)
    other = _lu_in(v, [partner]) if partner is not None else []
    if other and other != lu_m:
        return [f"命宫见{lu_m[0]}，六合位{v.branch(partner)}见{other[0]}"]
    return None


def r_sanqi(v, m):
    sf = v.sfsz(m)
    hits = [x for x in (_hua_in(v, sf, h) for h in "禄权科") if x]
    return ["生年禄权科齐会三方四正：" + "、".join(hits)] if len(hits) == 3 else None


def r_quanlu_xunfeng(v, m):
    sf = v.sfsz(m)
    lu, quan = _hua_in(v, sf, "禄"), _hua_in(v, sf, "权")
    if lu and quan:
        in_ming = "，且有一颗坐命" if (_hua_in(v, m, "禄") or _hua_in(v, m, "权")) else ""
        return [f"{lu}、{quan}会于命宫三方四正{in_ming}"]
    return None


def r_keming_huilu(v, m):
    ke, lu = _hua_in(v, m, "科"), _hua_in(v, v.sfsz(m), "禄")
    return [f"{ke}坐命", f"{lu}在三方四正"] if ke and lu else None


def r_keming_luan(v, m):
    ke = _hua_in(v, m, "科")
    partner = next((p.index for p in v.palaces if p.branch == LIUHE[_br(v, m)]), None)
    if ke and partner is not None and "禄存" in v.stars(partner):
        return [f"{ke}坐命", f"六合位{v.branch(partner)}见禄存"]
    return None


def r_luwen_gongming(v, m):
    if "禄存" in v.stars(m) and _in_sfsz(v, m, "文昌", "文曲"):
        return ["禄存坐命，文昌文曲会于三方四正"]
    return None


def r_shuanglu_jiaming(v, m):
    l, r = v.jia(m)
    a, b = _lu_in(v, [l]), _lu_in(v, [r])
    if a and b and set(a) != set(b):
        return [f"{a[0]}在{v.name(l)}、{b[0]}在{v.name(r)}，夹命"]
    return None


def r_cailu_jiama(v, m):
    if "天马" not in v.stars(m):
        return None
    l, r = v.jia(m)
    for x, y in ((l, r), (r, l)):
        lu = _lu_in(v, [y])
        if "武曲" in v.stars(x) and lu:
            return ["天马坐命", f"武曲在{v.name(x)}、{lu[0]}在{v.name(y)}，夹命"]
    return None


def r_caiyin_jiayin(v, m):
    if "天相" not in v.stars(m):
        return None
    l, r = v.jia(m)
    for x, y in ((l, r), (r, l)):
        lu = _hua_in(v, x, "禄")
        if lu and "天梁" in v.stars(y):
            return ["天相坐命", f"{lu}在{v.name(x)}、天梁在{v.name(y)}，夹命"]
    return None


def r_zifu_jiaming(v, m):
    return _jia_pair(v, m, "紫微", "天府")


def r_kequanlu_jia(v, m):
    l, r = v.jia(m)
    side = {h: v.hua_where(h) for h in "禄权科"}
    left = [h for h, w in side.items() if w == l]
    right = [h for h, w in side.items() if w == r]
    if left and right:
        return [f"化{'、'.join(left)}在{v.name(l)}，化{'、'.join(right)}在{v.name(r)}，夹命"]
    return None


def r_jiadi_dengyong(v, m):
    ke = _hua_in(v, m, "科")
    quan = _hua_in(v, v.sfsz(m), "权")
    return [f"{ke}坐命", f"{quan}在三方四正"] if ke and quan else None


def r_zuoyou_tonggong(v, m):
    return ["左辅右弼同坐" + v.name(m)] if v.has(m, "左辅", "右弼") else None


def r_zuoyou_jia(v, m):
    return _jia_pair(v, m, "左辅", "右弼")


def r_changqu_jia(v, m):
    return _jia_pair(v, m, "文昌", "文曲")


def r_kuiyue_jia(v, m):
    return _jia_pair(v, m, "天魁", "天钺")


def r_zuogui_xianggui(v, m):
    """魁钺一颗坐命，另一颗在三方四正会照（对宫为正格）。"""
    sf = v.sfsz(m)
    for a, b in (("天魁", "天钺"), ("天钺", "天魁")):
        if a in v.stars(m) and v.where(b) in sf and v.where(b) != m:
            where = "对宫" if v.where(b) == v.at(m, "迁") else v.name(v.where(b))
            return [f"{a}坐命，{b}在{where}会照"]
    return None


def r_fugong_wenxing(v, m):
    wen = v.any_of(m, ("文昌", "文曲"))
    if not wen:
        return None
    fu = v.any_of(v.sfsz(m), ("左辅", "右弼"))
    if fu:
        return [f"{'、'.join(wen)}坐命", f"{'、'.join(fu)}会于三方四正"]
    if _jia_pair(v, m, "左辅", "右弼"):
        return [f"{'、'.join(wen)}坐命", "左辅右弼夹命"]
    return None


def r_tianyi_gongming(v, m):
    return ["天魁、天钺会于命宫三方四正"] if _in_sfsz(v, m, "天魁", "天钺") else None


def r_wengui_wenhua(v, m):
    return _in_ming(v, m, "文昌", "文曲", branches="丑未", borrow=False)


def r_wenxing_chaoming(v, m):
    return ["文昌、文曲会于命宫三方四正"] if _in_sfsz(v, m, "文昌", "文曲") else None


# ------------------------------------------------------------------ 凶格
def r_lingchang_tuowu(v, m):
    return ["铃星、文昌、陀罗、武曲齐会三方四正"] if _in_sfsz(v, m, "铃星", "文昌", "陀罗", "武曲") else None


def r_maluo_kongwang(v, m):
    """天马在命宫三方四正，同宫见空亡，或对宫有地空地劫冲照。"""
    for i in v.sfsz(m):
        if "天马" in v.stars(i):
            kong = [s for s in v.stars(i) if s in KONG]
            if kong:
                return [f"天马与{'、'.join(kong)}同在{v.name(i)}"]
            opp = v.any_of((i + 6) % 12, ("地空", "地劫"))
            if opp:
                return [f"天马在{v.name(i)}，对宫{'、'.join(opp)}冲照"]
    return None


def r_mingwu_zhengyao(v, m):
    return ["命宫无十四主星（借对宫主星论）"] if not v.majors(m) else None


def r_jiju_maoyou(v, m):
    return _in_ming(v, m, "紫微", "贪狼", branches="卯酉", borrow=False)


def r_juji_huayou(v, m):
    ev = _in_ming(v, m, "天机", "巨门", branches="酉", borrow=False)
    ji = _hua_in(v, m, "忌")
    return ev + [f"{ji}同宫"] if ev and ji else None


def r_zhensha_tonggong(v, m):
    return _in_ming(v, m, "廉贞", "七杀", branches="丑未", borrow=False)


def r_wenxing_yujia(v, m):
    wen = v.any_of(m, ("文昌", "文曲"))
    if not wen:
        return None
    for a, b in (("地空", "地劫"), ("火星", "铃星"), ("擎羊", "陀罗")):
        j = _jia_pair(v, m, a, b)
        if j:
            return [f"{'、'.join(wen)}坐命"] + j
    return None


def r_xingji_jiayin(v, m):
    if "天相" not in v.stars(m):
        return None
    l, r = v.jia(m)
    for x, y in ((l, r), (r, l)):
        ji = _hua_in(v, x, "忌")
        other = v.any_of(y, ("天梁", "擎羊"))
        if ji and other:
            return ["天相坐命", f"{ji}在{v.name(x)}、{other[0]}在{v.name(y)}，夹命"]
    return None


def r_lufeng_chongpo(v, m):
    lu = _lu_in(v, [m])
    k = v.any_of(v.sfsz(m), ("地空", "地劫"))
    return [f"{'、'.join(lu)}坐命", f"三方四正见{'、'.join(k)}"] if lu and k else None


def r_fengliu_caizhang(v, m):
    if "贪狼" in v.stars(m) and _br(v, m) == "寅" and "陀罗" in v.stars(m):
        return ["贪狼坐命于寅，与陀罗同宫"]
    return None


def r_yangtuo_jiaji(v, m):
    ji = _hua_in(v, m, "忌")
    j = _jia_pair(v, m, "擎羊", "陀罗")
    return [f"{ji}坐命"] + j if ji and j else None


def r_yangtuo_jiaming(v, m):
    return _jia_pair(v, m, "擎羊", "陀罗")


def r_huoling_jiaming(v, m):
    if "贪狼" in v.stars(m):
        return None                     # 火铃夹贪狼反作吉论，不入此格
    return _jia_pair(v, m, "火星", "铃星")


def r_kongjie_jiaming(v, m):
    return _jia_pair(v, m, "地空", "地劫")


def r_xingqiu_jiayin(v, m):
    if v.has(m, "廉贞", "天相") and v.any_of(m, ("擎羊", "天刑")):
        return ["廉贞、天相与" + "、".join(v.any_of(m, ("擎羊", "天刑"))) + f"同在{v.name(m)}"]
    return None


def r_ju_feng_sisha(v, m):
    """巨门守命，羊陀火铃在同宫或三方四正会照。"""
    if "巨门" in v.stars(m):
        sha = v.any_of(v.sfsz(m), ("擎羊", "陀罗", "火星", "铃星"))
        if sha:
            return [f"巨门坐命，三方四正见{'、'.join(sha)}"]
    return None


def r_mingli_fengkong(v, m):
    k = v.any_of(m, ("地空", "地劫"))
    return [f"命宫见{'、'.join(k)}"] if k else None


def r_sheng_bu_fengshi(v, m):
    k = v.any_of(m, ("地空", "地劫", "旬空", "截空"))
    return [f"廉贞坐命，同宫见{'、'.join(k)}"] if "廉贞" in v.stars(m) and k else None


def r_liangchong_huagai(v, m):
    lu = _lu_in(v, [m])
    k = v.any_of(m, ("地空", "地劫"))
    return ["禄存与化禄同坐命宫", f"同宫见{'、'.join(k)}"] if len(lu) == 2 and k else None


def r_riyue_fanbei(v, m):
    sf = v.sfsz(m)
    if v.has(sf, "太阳", "太阴") and v.brightness("太阳") in DARK and v.brightness("太阴") in DARK:
        return ["太阳、太阴皆落陷，会于命宫三方四正"]
    return None


def r_liangma_piaodang(v, m):
    return ["天梁、天马同坐命宫"] if v.has(m, "天梁", "天马") else None


def r_fanshui_taohua(v, m):
    """贪狼坐命于子；或廉贞贪狼坐命于亥、与陀罗同宫。"""
    b = _br(v, m)
    if "贪狼" in v.stars(m) and b == "子":
        return ["贪狼坐命于子"]
    if v.has(m, "廉贞", "贪狼", "陀罗") and b == "亥":
        return ["廉贞贪狼坐命于亥，与陀罗同宫"]
    return None


RULES: list[Rule] = [
    # 主星格
    Rule("zifu_tonggong", "紫府同宫", "吉", "主星格", r_zifu_tonggong, supersedes=("zifu_chaoyuan",)),
    Rule("zifu_chaoyuan", "紫府朝垣", "吉", "主星格", r_zifu_chaoyuan,
         note="紫府从命宫之外朝照；正格四种：武相寅申、廉贞寅申、廉相子午、天相丑未坐命"),
    Rule("tianfu_chaoyuan", "天府朝垣", "吉", "主星格", r_tianfu_chaoyuan, note="另有一说天府在午亦是"),
    Rule("junchen_qinghui", "君臣庆会", "吉", "主星格", r_junchen, aliases=("辅弼拱主",),
         note="宽口径：紫微坐命，左右至少一颗会照或夹命；全书要求府相昌曲等群臣齐会"),
    Rule("jixiang_liming", "极向离明", "吉", "主星格", r_jixiang_liming),
    Rule("fuxiang_chaoyuan", "府相朝垣", "吉", "主星格", r_fuxiang_chaoyuan,
         note="宽口径：天府天相于命宫三方四正会照；狭义为命无主星、府相分居财官"),
    Rule("jiyue_tongliang", "机月同梁", "吉", "主星格", r_jiyue_tongliang),
    Rule("shanyin_chaogang", "善荫朝纲", "吉", "主星格", r_shanyin_chaogang, aliases=("机梁加会",)),
    Rule("wenliang_zhenji", "文梁振纪", "吉", "主星格", r_wenliang_zhenji),
    Rule("lianzhen_wenwu", "廉贞文武", "吉", "主星格", r_lianzhen_wenwu),
    Rule("shapolang", "杀破狼", "吉", "主星格", r_shapolang, note="变动开创之格，吉凶视会照而定"),
    Rule("qisha_chaodou", "七杀朝斗", "吉", "主星格", r_qisha_chaodou, aliases=("七杀仰斗",),
         note="各家地支归属不一：一说寅为仰斗、申为朝斗；x-iztro 以子寅为仰斗、午申为朝斗"),
    Rule("jiangxing_dedi", "将星得地", "吉", "主星格", r_jiangxing_dedi, aliases=("武曲守垣",)),
    Rule("xiongsu_chaoyuan", "雄宿朝垣", "吉", "主星格", r_xiongsu_chaoyuan, aliases=("雄宿朝元", "权星朝垣")),
    Rule("tanwu_tongxing", "贪武同行", "吉", "主星格", r_tanwu, also_body=True),
    Rule("huolingtan", "火铃贪格", "吉", "主星格", r_huolingtan, supersedes=("huotan", "lingtan")),
    Rule("huotan", "火贪格", "吉", "主星格", r_huotan),
    Rule("lingtan", "铃贪格", "吉", "主星格", r_lingtan),
    Rule("shizhong_yinyu", "石中隐玉", "吉", "主星格", r_shizhong_yinyu, note="辛癸年生尤佳"),
    Rule("juri_tonggong", "巨日同宫", "吉", "主星格", r_juri_tonggong, note="寅宫为上，申宫次之"),
    Rule("jiju_tonglin", "巨机同宫", "吉", "主星格", r_jiju_tonglin, aliases=("机巨同临",), note="卯宫为上"),
    Rule("huaxing_fangui", "化星返贵", "吉", "主星格", r_huaxing_fangui),
    Rule("shouxing_rumiao", "寿星入庙", "吉", "主星格", r_shouxing_rumiao),
    Rule("yingxing_rumiao", "英星入庙", "吉", "主星格", r_yingxing_rumiao),
    Rule("matou_daijian", "马头带箭", "吉", "主星格", r_matou_daijian),
    Rule("qingyang_rumiao", "擎羊入庙", "吉", "主星格", r_qingyang_rumiao, note="武贵之格"),
    # 日月格
    Rule("riyue_bingming", "日月并明", "吉", "日月格", r_riyue_bingming),
    Rule("danchi_guichi", "丹墀桂墀", "吉", "日月格", r_danchi_guichi),
    Rule("rizhao_leimen", "日照雷门", "吉", "日月格", r_rizhao_leimen, aliases=("日出扶桑",)),
    Rule("jincan_guanghui", "金灿光辉", "吉", "日月格", r_jincan_guanghui, aliases=("日丽中天",)),
    Rule("yuelang_tianmen", "月朗天门", "吉", "日月格", r_yuelang_tianmen, aliases=("月落亥宫",)),
    Rule("yuesheng_canghai", "月生沧海", "吉", "日月格", r_yuesheng_canghai, supersedes=("shuicheng_guie",)),
    Rule("shuicheng_guie", "水澄桂萼", "吉", "日月格", r_shuicheng_guie),
    Rule("mingzhu_chuhai", "明珠出海", "吉", "日月格", r_mingzhu_chuhai),
    Rule("riyue_jiaming", "日月夹命", "吉", "夹格", r_riyue_jiaming),
    Rule("riyue_tonggong", "日月同宫", "吉", "日月格", r_riyue_tonggong, note="丑宫胜于未宫"),
    Rule("erya_tonglin", "二曜同临", "吉", "日月格", r_erya_tonglin),
    Rule("riyue_zhaobi", "日月照璧", "吉", "日月格", r_riyue_zhaobi),
    Rule("yangliang_changlu", "阳梁昌禄", "吉", "日月格", r_yangliang_changlu),
    # 四化与禄马格
    Rule("luma_jiaochi", "禄马交驰", "吉", "四化格", r_luma_jiaochi),
    Rule("luma_peiyin", "禄马佩印", "吉", "四化格", r_luma_peiyin),
    Rule("luhe_yuanyang", "禄合鸳鸯", "吉", "四化格", r_luhe_yuanyang, supersedes=("shuanglu_chaoyuan",)),
    Rule("shuanglu_chaoyuan", "双禄朝垣", "吉", "四化格", r_shuanglu, aliases=("双禄交流",)),
    Rule("shuanglu_jiaming", "双禄夹命", "吉", "夹格", r_shuanglu_jiaming),
    Rule("minglu_anlu", "明禄暗禄", "吉", "四化格", r_minglu_anlu),
    Rule("keming_luan", "科明禄暗", "吉", "四化格", r_keming_luan),
    Rule("luwen_gongming", "禄文拱命", "吉", "四化格", r_luwen_gongming),
    Rule("sanqi_jiahui", "三奇加会", "吉", "四化格", r_sanqi, aliases=("三奇嘉会",),
         supersedes=("quanlu_xunfeng", "keming_huilu", "jiadi_dengyong")),
    Rule("quanlu_xunfeng", "权禄巡逢", "吉", "四化格", r_quanlu_xunfeng),
    Rule("keming_huilu", "科名会禄", "吉", "四化格", r_keming_huilu),
    Rule("jiadi_dengyong", "甲第登庸", "吉", "四化格", r_jiadi_dengyong, aliases=("甲第登科",)),
    Rule("kequanlu_jia", "科权禄夹", "吉", "夹格", r_kequanlu_jia),
    # 辅佐与夹格
    Rule("zuoyou_tonggong", "左右同宫", "吉", "辅佐格", r_zuoyou_tonggong, also_body=True),
    Rule("fugong_wenxing", "辅拱文星", "吉", "辅佐格", r_fugong_wenxing),
    Rule("zifu_jiaming", "紫府夹命", "吉", "夹格", r_zifu_jiaming),
    Rule("zuoyou_jiaming", "左右夹命", "吉", "夹格", r_zuoyou_jia),
    Rule("changqu_jiaming", "昌曲夹命", "吉", "夹格", r_changqu_jia, aliases=("文星暗拱",)),
    Rule("kuiyue_jiaming", "魁钺夹命", "吉", "夹格", r_kuiyue_jia),
    Rule("caiyin_jiayin", "财荫夹印", "吉", "夹格", r_caiyin_jiayin),
    Rule("cailu_jiama", "财禄夹马", "吉", "夹格", r_cailu_jiama, note="主富不主贵"),
    Rule("zuogui_xianggui", "坐贵向贵", "吉", "辅佐格", r_zuogui_xianggui, supersedes=("tianyi_gongming",)),
    Rule("tianyi_gongming", "天乙拱命", "吉", "辅佐格", r_tianyi_gongming),
    Rule("wengui_wenhua", "文桂文华", "吉", "辅佐格", r_wengui_wenhua, supersedes=("wenxing_chaoming",)),
    Rule("wenxing_chaoming", "文星拱命", "吉", "辅佐格", r_wenxing_chaoming, aliases=("文星朝命", "文昌拱命")),
    # 凶格
    Rule("mingwu_zhengyao", "命无正曜", "凶", "主星格", r_mingwu_zhengyao, note="约六分之一命盘如此，并非罕见"),
    Rule("jiju_maoyou", "极居卯酉", "凶", "主星格", r_jiju_maoyou),
    Rule("juji_huayou", "巨机化酉", "凶", "主星格", r_juji_huayou),
    Rule("zhensha_tonggong", "贞杀同宫", "凶", "主星格", r_zhensha_tonggong),
    Rule("lingchang_tuowu", "铃昌陀武", "凶", "煞格", r_lingchang_tuowu),
    Rule("maluo_kongwang", "马落空亡", "凶", "煞格", r_maluo_kongwang),
    Rule("yangtuo_jiaji", "羊陀夹忌", "凶", "夹格", r_yangtuo_jiaji, supersedes=("yangtuo_jiaming",)),
    Rule("yangtuo_jiaming", "羊陀夹命", "凶", "夹格", r_yangtuo_jiaming),
    Rule("huoling_jiaming", "火铃夹命", "凶", "夹格", r_huoling_jiaming),
    Rule("kongjie_jiaming", "空劫夹命", "凶", "夹格", r_kongjie_jiaming),
    Rule("wenxing_yujia", "文星遇夹", "凶", "夹格", r_wenxing_yujia),
    Rule("xingji_jiayin", "刑忌夹印", "凶", "夹格", r_xingji_jiayin),
    Rule("xingqiu_jiayin", "刑囚夹印", "凶", "煞格", r_xingqiu_jiayin, also_body=True),
    Rule("ju_feng_sisha", "巨逢四煞", "凶", "煞格", r_ju_feng_sisha),
    Rule("mingli_fengkong", "命里逢空", "凶", "煞格", r_mingli_fengkong),
    Rule("sheng_bu_fengshi", "生不逢时", "凶", "煞格", r_sheng_bu_fengshi),
    Rule("liangchong_huagai", "两重华盖", "凶", "煞格", r_liangchong_huagai, supersedes=("lufeng_chongpo",)),
    Rule("lufeng_chongpo", "禄逢冲破", "凶", "煞格", r_lufeng_chongpo),
    Rule("riyue_fanbei", "日月反背", "凶", "日月格", r_riyue_fanbei),
    Rule("liangma_piaodang", "梁马飘荡", "凶", "煞格", r_liangma_piaodang),
    Rule("fanshui_taohua", "泛水桃花", "凶", "煞格", r_fanshui_taohua),
    Rule("fengliu_caizhang", "风流彩杖", "凶", "煞格", r_fengliu_caizhang),
]


# ------------------------------------------------------------------ 事实（交给 AI 判破格）
def context_facts(v: ChartView, m: int) -> dict:
    area = v.sfsz(m) + list(v.jia(m))
    rel = {v.sfsz(m)[0]: "本宫", v.sfsz(m)[1]: "官禄位", v.sfsz(m)[2]: "财帛位", v.sfsz(m)[3]: "对宫",
           v.jia(m)[0]: "夹宫", v.jia(m)[1]: "夹宫"}
    sha, kong, ji, xian, self_ji = [], [], [], [], []
    for i in area:
        for s, info in v.stars(i).items():
            where = f"{v.name(i)}({rel[i]})"
            if s in SHA:
                sha.append(f"{s}@{where}")
            if s in KONG and s not in ("地空", "地劫"):
                kong.append(f"{s}@{where}")
            if info.get("birth_hua") == "忌":
                ji.append(f"{s}生年忌@{where}")
            if info.get("self_out") == "忌":
                self_ji.append(f"{s}离心自化忌@{where}")
            if info.get("brightness") in DARK and s in v.majors(i):
                xian.append(f"{s}[{info.get('brightness')}]@{where}")
    return {"sha": sha, "kong": kong, "ji": ji, "self_ji": self_ji, "xian": xian}


def detect(astro_or_view) -> dict:
    v = astro_or_view if isinstance(astro_or_view, ChartView) else from_astrolabe(astro_or_view)
    bases = [("命", v.soul)] + ([("身", v.body)] if v.body != v.soul else [])
    hits: dict[str, dict] = {}
    for level, base in bases:
        for rule in RULES:
            if level == "身" and not rule.also_body:
                continue
            if rule.id in hits:
                continue
            ev = rule.check(v, base)
            if ev:
                hits[rule.id] = {"id": rule.id, "name": rule.name, "kind": rule.kind, "group": rule.group,
                                 "level": level, "evidence": ev, "note": rule.note,
                                 "aliases": list(rule.aliases)}
    hidden = {h for r in RULES if r.id in hits for h in r.supersedes}
    patterns = [h for rid, h in hits.items() if rid not in hidden]
    m = v.soul
    return {
        "version": VERSION,
        "ming": {"index": m, "branch": v.branch(m), "majors": v.majors(m),
                 "borrowed": not v.majors(m), "borrowed_majors": v.majors(m, borrow=True)},
        "patterns": patterns,
        "counts": {"吉": sum(p["kind"] == "吉" for p in patterns), "凶": sum(p["kind"] == "凶" for p in patterns)},
        "context": context_facts(v, m),
        "method": "按全书与中州/三合通行口径判成格方向；破格不判，只列煞忌空陷等事实",
    }
