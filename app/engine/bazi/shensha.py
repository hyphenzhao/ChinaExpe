"""神煞 rules (测测 App 口径, verified against real 测测 exports kept in data/golden).

A rule is evaluated for a *target pillar* (natal pillar or a 大运/流年/流月/流日
pillar) against the natal context (年干, 年支, 日干, 日支, 月支, 日柱纳音 …).
"""
from __future__ import annotations

from dataclasses import dataclass

from .constants import (BRANCHES, FUXING, GUOYIN, HONGYAN, JINYU, KUIGANG, LIUXIU_DAYS, LIU_E, LUSHEN,
                        MU_KU, SANHE_SHA, SHIE_DABAI, STEM_HE, TAIJI, TIANDE, TIANYI, WENCHANG, WUXING,
                        XUETANG_BY_NAYIN, CIGUAN_BY_NAYIN, YANGREN, YINCHA_YANGCUO, YUEDE, sanhe_group)
from lunar_python.util import LunarUtil

_LIUHE = {"子": "丑", "丑": "子", "寅": "亥", "亥": "寅", "卯": "戌", "戌": "卯", "辰": "酉", "酉": "辰",
          "巳": "申", "申": "巳", "午": "未", "未": "午"}


def _nayin_wx(gz: str) -> str:
    n = LunarUtil.NAYIN[gz]
    for w in WUXING:
        if w in n:
            return w
    return ""


@dataclass
class Context:
    year_gz: str
    month_gz: str
    day_gz: str
    hour_gz: str
    is_male: bool

    @property
    def year_stem(self): return self.year_gz[0]
    @property
    def year_branch(self): return self.year_gz[1]
    @property
    def month_branch(self): return self.month_gz[1]
    @property
    def day_stem(self): return self.day_gz[0]
    @property
    def day_branch(self): return self.day_gz[1]
    @property
    def yang_year(self): return "甲乙丙丁戊己庚辛壬癸".index(self.year_stem) % 2 == 0


def pillar_shensha(ctx: Context, gz: str, pos: str) -> list[str]:
    """Return 神煞 names for a pillar ``gz`` at position ``pos``.

    ``pos`` in 年柱/月柱/日柱/时柱 for natal pillars, or 大运/流年/流月/流日/流时.
    """
    g, z = gz[0], gz[1]
    out: list[str] = []
    ys, yb, ds, db, mb = ctx.year_stem, ctx.year_branch, ctx.day_stem, ctx.day_branch, ctx.month_branch
    natal = pos in ("年柱", "月柱", "日柱", "时柱")

    def add(name: str):
        if name not in out:
            out.append(name)

    # 干-based lookups (年干 & 日干 -> branch)
    for src in (ys, ds):
        if z in TIANYI[src]:
            add("天乙贵人")
    stems_present = {ctx.year_gz[0], ctx.month_gz[0], ctx.day_gz[0], ctx.hour_gz[0]}
    branches_present = {ctx.year_gz[1], ctx.month_gz[1], ctx.day_gz[1], ctx.hour_gz[1]}
    td = TIANDE[mb]
    if td in "甲乙丙丁戊己庚辛壬癸":
        if g == td:
            add("天德贵人")
        if g == STEM_HE[td] and td in stems_present:   # 测测: 合 only when 天德 itself is present
            add("天德合")
    else:
        if z == td:
            add("天德贵人")
        if z == _LIUHE[td] and td in branches_present:
            add("天德合")
    yd = YUEDE[mb]
    if g == yd:
        add("月德贵人")
    if g == STEM_HE[yd] and yd in stems_present:
        add("月德合")
    for src in (ys, ds):
        if z in WENCHANG[src]:
            add("文昌贵人")
    for src in (ys, ds):
        if z == GUOYIN[src]:
            add("国印")
    for src in (ys, ds):
        if z in TAIJI[src]:
            add("太极贵人")
    for src in (ys, ds):
        if z in FUXING.get(src, ""):
            add("福星贵人")
    if z == JINYU[ds]:
        add("金舆")
    if z == LUSHEN[ds]:
        add("禄神")
    if ds in YANGREN and z == YANGREN[ds]:
        add("羊刃")
    if z == HONGYAN[ds]:
        add("红艳")
    # 五行正印: 年柱纳音五行之墓库
    if z == MU_KU[_nayin_wx(ctx.year_gz)]:
        add("五行正印")
    # 支-based (年支 / 日支 三合 group), source pillar excluded for natal pillars
    for src_pos, src in (("年柱", yb), ("日柱", db)):
        if natal and pos == src_pos:
            continue
        tab = SANHE_SHA[sanhe_group(src)]
        for name, target in tab.items():
            if z == target:
                add(name)
    # 孤辰 寡宿 (年支)
    gu, gua = {"亥": ("寅", "戌"), "子": ("寅", "戌"), "丑": ("寅", "戌"), "寅": ("巳", "丑"), "卯": ("巳", "丑"),
               "辰": ("巳", "丑"), "巳": ("申", "辰"), "午": ("申", "辰"), "未": ("申", "辰"), "申": ("亥", "未"),
               "酉": ("亥", "未"), "戌": ("亥", "未")}[yb]
    if z == gu:
        add("孤辰")
    if z == gua:
        add("寡宿")
    # 勾绞 (年支 ± 3)
    yi = BRANCHES.index(yb)
    if z in (BRANCHES[(yi + 3) % 12], BRANCHES[(yi - 3) % 12]):
        add("勾绞")
    # 元辰: 阳男阴女 = 冲后一位; 阴男阳女 = 冲前一位
    chong = BRANCHES[(yi + 6) % 12]
    same = ctx.yang_year == ctx.is_male
    yuanchen = BRANCHES[(BRANCHES.index(chong) + (1 if same else -1)) % 12]
    if z == yuanchen:
        add("元辰")
    if z == LIU_E[sanhe_group(yb)]:
        add("六厄")
    # 学堂 / 词馆: 日柱纳音五行
    if z == XUETANG_BY_NAYIN[_nayin_wx(ctx.day_gz)]:
        add("学堂")
    # 空亡: 日柱旬空
    if z in LunarUtil.getXunKong(ctx.day_gz) and not (natal and pos == "日柱"):
        add("空亡")
    # 童子: 月令季节 + 年柱纳音, natal 日/时 only
    if pos in ("日柱", "时柱"):
        season_targets = "寅子" if mb in "寅卯辰申酉戌" else "卯未辰"
        nw = _nayin_wx(ctx.year_gz)
        nayin_targets = "午卯" if nw in "金木" else ("酉戌" if nw in "水火" else "辰巳")
        if z in season_targets or z in nayin_targets:
            add("童子")
    # 日柱 specials (also for 流日)
    if pos in ("日柱", "流日"):
        if gz in LIUXIU_DAYS:
            add("六秀日")
        if gz in YINCHA_YANGCUO:
            add("阴差阳错")
        if gz in KUIGANG:
            add("魁罡")
        if gz in SHIE_DABAI:
            add("十恶大败")
    # 天医 (月支前一位), 血刃 (月支)
    if z == BRANCHES[(BRANCHES.index(mb) - 1) % 12]:
        add("天医")
    xueren = {"寅": "丑", "卯": "未", "辰": "寅", "巳": "申", "午": "卯", "未": "酉", "申": "辰", "酉": "戌",
              "戌": "巳", "亥": "亥", "子": "午", "丑": "子"}[mb]
    if z == xueren:
        add("血刃")
    return out
