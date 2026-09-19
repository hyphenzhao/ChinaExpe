"""安星: build the natal 紫微斗数 astrolabe.

Algorithms follow 《紫微斗数全书》 as implemented by iztro (MIT), adapted to
文墨天机's default conventions (see engine/settings.py).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from .. import calendar as cal
from ..settings import BirthInput, ZiweiSettings
from .constants import (ADJECTIVE_STARS, BODY_MASTER, BOSHI12, BRANCHES, BUREAU_NAMES,
                        CHANGSHENG12, CHANGSHENG_START, HUA, HUA_TABLES, JIANGQIAN12,
                        MAJOR_STARS, MINOR_STARS, PALACE_NAMES, SOUL_MASTER, STEMS,
                        SUIQIAN12, TIGER_RULE, brightness, pbranch, pidx, sanhe_group)


@dataclass
class Star:
    name: str
    category: str                      # major | minor | adjective
    brightness: Optional[str] = None
    birth_hua: Optional[str] = None    # 生年四化
    self_hua_out: Optional[str] = None  # ↓ 离心自化 (本宫干)
    self_hua_in: Optional[str] = None   # ↑ 向心自化 (对宫干)

    def as_dict(self) -> dict:
        return {"name": self.name, "category": self.category, "brightness": self.brightness,
                "birth_hua": self.birth_hua, "self_hua_out": self.self_hua_out,
                "self_hua_in": self.self_hua_in}


@dataclass
class Palace:
    index: int                # 0 = 寅
    branch: str
    stem: str
    name: str
    stars: list[Star] = field(default_factory=list)
    changsheng: str = ""
    boshi: str = ""
    suiqian: str = ""
    jiangqian: str = ""
    decadal_start: int = 0
    decadal_end: int = 0
    ages: list[int] = field(default_factory=list)          # 小限 虚岁
    yearly_ages: list[int] = field(default_factory=list)   # 流年 虚岁
    is_body: bool = False
    is_laiyin: bool = False

    @property
    def ganzhi(self) -> str:
        return self.stem + self.branch

    def star(self, name: str) -> Optional[Star]:
        for s in self.stars:
            if s.name == name:
                return s
        return None

    def as_dict(self, birth_year: int) -> dict:
        return {
            "index": self.index, "branch": self.branch, "stem": self.stem, "ganzhi": self.ganzhi,
            "name": self.name, "is_body": self.is_body, "is_laiyin": self.is_laiyin,
            "stars": [s.as_dict() for s in self.stars],
            "changsheng": self.changsheng, "boshi": self.boshi,
            "suiqian": self.suiqian, "jiangqian": self.jiangqian,
            "decadal": {"start": self.decadal_start, "end": self.decadal_end,
                        "start_year": birth_year + self.decadal_start - 1,
                        "end_year": birth_year + self.decadal_end - 1},
            "ages": list(self.ages), "yearly_ages": list(self.yearly_ages),
        }


@dataclass
class Astrolabe:
    birth: BirthInput
    settings: ZiweiSettings
    solar: datetime               # clock time
    true_solar: datetime          # 真太阳时 (== solar if disabled)
    lunar: cal.LunarInfo
    pillars: cal.Pillars
    year_stem: str
    year_branch: str
    hour_index: int               # 0..12
    lunar_month_index: int        # 0-based month used for 安星 (after leap fix)
    lunar_day: int
    soul_index: int
    body_index: int
    bureau_num: int
    palaces: list[Palace]
    birth_hua: dict[str, str]     # 禄/权/科/忌 -> star
    laiyin_index: int
    zi_dou_branch: str            # 子年斗君

    # ---- helpers ----
    @property
    def is_male(self) -> bool:
        return self.birth.is_male

    @property
    def yang_year(self) -> bool:
        return STEMS.index(self.year_stem) % 2 == 0

    @property
    def forward(self) -> bool:
        """阳男阴女 -> True (顺行)."""
        return self.yang_year == self.is_male

    @property
    def bureau(self) -> str:
        return BUREAU_NAMES[self.bureau_num]

    @property
    def soul_palace(self) -> Palace:
        return self.palaces[self.soul_index]

    @property
    def ming_zhu(self) -> str:
        return SOUL_MASTER[pbranch(self.soul_index)]

    @property
    def shen_zhu(self) -> str:
        return BODY_MASTER[self.year_branch]

    @property
    def birth_year(self) -> int:
        return self.lunar.year

    def palace_by_name(self, name: str) -> Palace:
        for p in self.palaces:
            if p.name == name:
                return p
        raise KeyError(name)

    def palace_by_branch(self, branch: str) -> Palace:
        return self.palaces[pidx(branch)]

    def find_star(self, name: str) -> Optional[tuple[Palace, Star]]:
        for p in self.palaces:
            s = p.star(name)
            if s:
                return p, s
        return None

    def hua_table(self) -> dict[str, list[str]]:
        return HUA_TABLES.get(self.settings.hua_table, HUA_TABLES["default"])

    def hua_of_stem(self, stem: str) -> dict[str, str]:
        return dict(zip(HUA, self.hua_table()[stem]))

    def as_dict(self) -> dict:
        return {
            "birth": {
                "solar": self.solar.strftime("%Y-%m-%d %H:%M"),
                "true_solar": self.true_solar.strftime("%Y-%m-%d %H:%M"),
                "use_true_solar_time": self.birth.use_true_solar_time,
                "longitude": self.birth.longitude,
                "gender": "男" if self.is_male else "女",
                "yinyang_gender": ("阳" if self.yang_year else "阴") + ("男" if self.is_male else "女"),
                "lunar": self.lunar.text,
                "lunar_year": self.lunar.year, "lunar_month": self.lunar.month,
                "lunar_day": self.lunar.day, "is_leap_month": self.lunar.is_leap,
                "hour_index": self.hour_index, "hour_branch": BRANCHES[self.hour_index % 12],
            },
            "pillars": self.pillars.as_dict(),
            "year_ganzhi": self.year_stem + self.year_branch,
            "bureau": self.bureau, "bureau_num": self.bureau_num,
            "ming_zhu": self.ming_zhu, "shen_zhu": self.shen_zhu, "zi_dou": self.zi_dou_branch,
            "soul_index": self.soul_index, "body_index": self.body_index, "laiyin_index": self.laiyin_index,
            "forward": self.forward,
            "birth_hua": dict(self.birth_hua),
            "palaces": [p.as_dict(self.birth_year) for p in self.palaces],
            "settings": self.settings.as_dict(),
        }


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _fix(i: int, n: int = 12) -> int:
    return i % n


def nayin_bureau(stem: str, branch: str) -> int:
    """五行局 from 命宫干支 (纳音).  木3 金4 水2 火6 土5."""
    table = [3, 4, 2, 6, 5]  # 木 金 水 火 土 -> index 1..5
    s = STEMS.index(stem) // 2 + 1
    b = (BRANCHES.index(branch) % 6) // 2 + 1
    idx = s + b
    while idx > 5:
        idx -= 5
    return table[idx - 1]


def soul_body_index(month_index: int, hour_index: int) -> tuple[int, int]:
    """month_index: 0 = 正月; hour_index 0..12 (12 -> 子)."""
    h = hour_index % 12
    return _fix(month_index - h), _fix(month_index + h)


def ziwei_index(bureau: int, lunar_day: int) -> int:
    offset = -1
    while True:
        offset += 1
        divisor = lunar_day + offset
        if divisor % bureau == 0:
            quotient = divisor // bureau
            break
    quotient %= 12
    idx = quotient - 1
    idx = idx + offset if offset % 2 == 0 else idx - offset
    return _fix(idx)


def lu_yang_tuo_ma(year_stem: str, year_branch: str) -> tuple[int, int, int, int]:
    lu_branch = {"甲": "寅", "乙": "卯", "丙": "巳", "戊": "巳", "丁": "午", "己": "午",
                 "庚": "申", "辛": "酉", "壬": "亥", "癸": "子"}[year_stem]
    ma_branch = {"寅": "申", "申": "寅", "巳": "亥", "亥": "巳"}[sanhe_group(year_branch)]
    lu = pidx(lu_branch)
    return lu, _fix(lu + 1), _fix(lu - 1), pidx(ma_branch)


def kui_yue(stem: str) -> tuple[int, int]:
    k, y = {"甲": "丑未", "戊": "丑未", "庚": "丑未", "乙": "子申", "己": "子申", "辛": "午寅",
            "丙": "亥酉", "丁": "亥酉", "壬": "卯巳", "癸": "卯巳"}[stem]
    return pidx(k), pidx(y)


def chang_qu_by_stem(stem: str) -> tuple[int, int]:
    c, q = {"甲": "巳酉", "乙": "午申", "丙": "申午", "戊": "申午", "丁": "酉巳", "己": "酉巳",
            "庚": "亥卯", "辛": "子寅", "壬": "寅子", "癸": "卯亥"}[stem]
    return pidx(c), pidx(q)


def luan_xi(branch: str) -> tuple[int, int]:
    hl = _fix(pidx("卯") - BRANCHES.index(branch))
    return hl, _fix(hl + 6)


def nianjie_index(branch: str) -> int:
    return pidx("戌酉申未午巳辰卯寅丑子亥"[BRANCHES.index(branch)])


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def compute_astrolabe(birth: BirthInput, settings: Optional[ZiweiSettings] = None) -> Astrolabe:
    settings = settings or ZiweiSettings()
    solar = birth.solar
    true_solar = cal.true_solar_time(solar, birth.longitude) if birth.use_true_solar_time else solar
    # 晚子时 handling: 文墨 default treats 23:xx as 子时 of the same day
    hour_index = birth.hour_override if birth.hour_override is not None else cal.hour_index(true_solar)
    lunar = cal.lunar_info(true_solar)
    pillars = cal.four_pillars(true_solar)

    # year 干支 for 安星: 正月初一 分界 (default) or 立春
    if settings.year_divide == "lichun":
        ygz = pillars.jieqi[0]
    else:
        ygz = lunar.year_gz
    year_stem, year_branch = ygz[0], ygz[1]

    # lunar month index used for 安星 (0 = 正月), with leap-month rule
    month_index = lunar.month - 1
    if lunar.is_leap:
        if settings.leap_month == "next" or (settings.leap_month == "half" and lunar.day > 15):
            month_index = _fix(month_index + 1)
    lunar_day = lunar.day
    if hour_index == 12 and settings.late_zi == "next":
        lunar_day += 1  # simplistic; caller should prefer late_zi=current

    soul_index, body_index = soul_body_index(month_index, hour_index)
    start_stem_i = STEMS.index(TIGER_RULE[year_stem])
    palaces: list[Palace] = []
    for i in range(12):
        stem = STEMS[(start_stem_i + i) % 10]
        name = PALACE_NAMES[_fix(i - soul_index)]
        palaces.append(Palace(index=i, branch=pbranch(i), stem=stem, name=name))
    soul = palaces[soul_index]
    bureau = nayin_bureau(soul.stem, soul.branch)
    palaces[body_index].is_body = True

    def put(idx: int, name: str, category: str):
        b = pbranch(idx)
        palaces[_fix(idx)].stars.append(Star(name=name, category=category, brightness=brightness(name, b)))

    # ---- 主星 ----
    zw = ziwei_index(bureau, lunar_day)
    tf = _fix(12 - zw)
    for i, s in enumerate(["紫微", "天机", "", "太阳", "武曲", "天同", "", "", "廉贞"]):
        if s:
            put(zw - i, s, "major")
    for i, s in enumerate(["天府", "太阴", "贪狼", "巨门", "天相", "天梁", "七杀", "", "", "", "破军"]):
        if s:
            put(tf + i, s, "major")

    # ---- 辅星 ----
    h = hour_index % 12
    zuo = _fix(pidx("辰") + month_index)
    you = _fix(pidx("戌") - month_index)
    chang = _fix(pidx("戌") - h)
    qu = _fix(pidx("辰") + h)
    kui, yue = kui_yue(year_stem)
    lu, yang, tuo, ma = lu_yang_tuo_ma(year_stem, year_branch)
    if settings.tianma == "month":
        ma = pidx({"寅": "申", "申": "寅", "巳": "亥", "亥": "巳"}[sanhe_group(pbranch(month_index))])
    kong = _fix(pidx("亥") - h)
    jie = _fix(pidx("亥") + h)
    grp = sanhe_group(year_branch)
    huo_start, ling_start = {"寅": ("丑", "卯"), "申": ("寅", "戌"), "巳": ("卯", "戌"), "亥": ("酉", "戌")}[grp]
    if settings.huoling == "year":
        huo, ling = pidx(huo_start), pidx(ling_start)
    else:
        huo, ling = _fix(pidx(huo_start) + h), _fix(pidx(ling_start) + h)
    for idx, name in [(chang, "文昌"), (qu, "文曲"), (zuo, "左辅"), (you, "右弼"), (kui, "天魁"), (yue, "天钺"),
                      (lu, "禄存"), (ma, "天马"), (yang, "擎羊"), (tuo, "陀罗"), (huo, "火星"), (ling, "铃星"),
                      (kong, "地空"), (jie, "地劫")]:
        put(idx, name, "minor")

    # ---- 小星 ----
    yb = BRANCHES.index(year_branch)
    ys = STEMS.index(year_stem)
    adj: dict[str, int] = {}
    adj["天官"] = pidx("未辰巳寅卯酉亥酉戌午"[ys])
    adj["天福"] = pidx("酉申子亥卯寅午巳午巳"[ys])
    adj["天厨"] = pidx("巳午子巳午申寅午酉亥"[ys])
    adj["天刑"] = _fix(pidx("酉") + month_index)
    adj["天姚"] = _fix(pidx("丑") + month_index)
    adj["解神"] = pidx("申戌子寅辰午"[month_index // 2])
    adj["天巫"] = pidx("巳申寅亥"[month_index % 4])
    adj["天月"] = pidx("戌巳辰寅未卯亥未寅午戌寅"[month_index])
    adj["阴煞"] = pidx("寅子戌申午辰"[month_index % 6])
    adj["台辅"] = _fix(pidx("午") + h)
    adj["封诰"] = _fix(pidx("寅") + h)
    adj["天空"] = _fix(pidx(year_branch) + 1)
    adj["天哭"] = _fix(pidx("午") - yb)
    adj["天虚"] = _fix(pidx("午") + yb)
    adj["龙池"] = _fix(pidx("辰") + yb)
    adj["凤阁"] = _fix(pidx("戌") - yb)
    hl, tx = luan_xi(year_branch)
    adj["红鸾"], adj["天喜"] = hl, tx
    gu, gua = {"寅": ("巳", "丑"), "卯": ("巳", "丑"), "辰": ("巳", "丑"), "巳": ("申", "辰"), "午": ("申", "辰"),
               "未": ("申", "辰"), "申": ("亥", "未"), "酉": ("亥", "未"), "戌": ("亥", "未"), "亥": ("寅", "戌"),
               "子": ("寅", "戌"), "丑": ("寅", "戌")}[year_branch]
    adj["孤辰"], adj["寡宿"] = pidx(gu), pidx(gua)
    adj["蜚廉"] = pidx("申酉戌巳午未寅卯辰亥子丑"[yb])
    adj["破碎"] = pidx("巳丑酉"[yb % 3])
    adj["华盖"] = pidx({"寅": "戌", "申": "辰", "巳": "丑", "亥": "未"}[grp])
    adj["咸池"] = pidx({"寅": "卯", "申": "酉", "巳": "午", "亥": "子"}[grp])
    adj["天德"] = _fix(pidx("酉") + yb)
    adj["月德"] = _fix(pidx("巳") + yb)
    adj["天才"] = _fix(soul_index + yb)
    adj["天寿"] = _fix(body_index + yb)
    day_i = lunar_day - 1
    adj["三台"] = _fix(zuo + day_i)
    adj["八座"] = _fix(you - day_i)
    adj["恩光"] = _fix(chang + day_i - 1)
    adj["天贵"] = _fix(qu + day_i - 1)
    # 龙德 = 岁前 龙德 (年支 + 7); 大耗 (年系): 年支对冲, 阳顺阴逆一位; 劫煞 (年支)
    adj["龙德"] = _fix(pidx(year_branch) + 7)
    adj["大耗"] = pidx("未午酉申亥戌丑子卯寅巳辰"[yb])
    adj["劫煞"] = pidx({"申": "巳", "亥": "申", "寅": "亥", "巳": "寅"}[grp])
    # 截空/副截 (截路空亡): 甲己申酉 乙庚午未 丙辛辰巳 丁壬寅卯 戊癸子丑; 阳干->阳支 is 正截空
    jielu = pidx("申午辰寅子"[ys % 5])
    kongwang = pidx("酉未巳卯丑"[ys % 5])
    if ys % 2 == 0:
        adj["截空"], adj["副截"] = jielu, kongwang
    else:
        adj["截空"], adj["副截"] = kongwang, jielu
    # 旬空/副旬: 旬中空亡 two branches; the one matching year-branch parity is 旬空
    xk = _fix(pidx(year_branch) + (9 - ys) + 1)
    other = _fix(xk + 1)
    if (yb % 2) != (BRANCHES.index(pbranch(xk)) % 2):
        xk, other = other, xk
    adj["旬空"], adj["副旬"] = xk, other
    # 天伤 (交友宫) / 天使 (疾厄宫)
    tianshang = _fix(soul_index + 5)
    tianshi = _fix(soul_index + 7)
    if settings.tianshang_tianshi == "zhongzhou":
        same = (yb % 2 == 0) == birth.is_male
        if not same:
            tianshang, tianshi = tianshi, tianshang
    adj["天伤"], adj["天使"] = tianshang, tianshi
    adj["年解"] = nianjie_index(year_branch)
    for name in ADJECTIVE_STARS:
        put(adj[name], name, "adjective")

    # ---- 神煞 / 长生 ----
    forward = (ys % 2 == 0) == birth.is_male
    cs_start = pidx(CHANGSHENG_START[bureau])
    bs_start = lu
    sq_start = pidx(year_branch)
    jq_start = pidx({"寅": "午", "申": "子", "巳": "酉", "亥": "卯"}[grp])
    for i in range(12):
        palaces[_fix(cs_start + i if forward else cs_start - i)].changsheng = CHANGSHENG12[i]
        palaces[_fix(bs_start + i if forward else bs_start - i)].boshi = BOSHI12[i]
        palaces[_fix(sq_start + i)].suiqian = SUIQIAN12[i]
        palaces[_fix(jq_start + i)].jiangqian = JIANGQIAN12[i]

    # ---- 大限 / 小限 / 流年岁 ----
    for i in range(12):
        idx = _fix(soul_index + i if forward else soul_index - i)
        palaces[idx].decadal_start = bureau + 10 * i
        palaces[idx].decadal_end = bureau + 10 * i + 9
    age_start = pidx({"寅": "辰", "申": "戌", "巳": "未", "亥": "丑"}[grp])
    for i in range(12):
        idx = _fix(age_start + i if birth.is_male else age_start - i)
        palaces[idx].ages = [12 * j + i + 1 for j in range(5)]
        yidx = _fix(pidx(year_branch) + i)
        palaces[yidx].yearly_ages = [12 * j + i + 1 for j in range(5)]

    # ---- 四化 ----
    table = HUA_TABLES.get(settings.hua_table, HUA_TABLES["default"])
    birth_hua = dict(zip(HUA, table[year_stem]))
    laiyin_index = next(p.index for p in palaces if p.stem == year_stem)
    palaces[laiyin_index].is_laiyin = True
    for p in palaces:
        own = dict(zip(table[p.stem], HUA))
        opp = dict(zip(table[palaces[_fix(p.index + 6)].stem], HUA))
        for s in p.stars:
            for hua, star in birth_hua.items():
                if star == s.name:
                    s.birth_hua = hua
            if s.name in own:
                s.self_hua_out = own[s.name]
            if s.name in opp:
                s.self_hua_in = opp[s.name]

    # ---- 子年斗君: 子宫起正月逆数至生月, 再顺数至生时 ----
    zd = _fix(pidx("子") - month_index + h)
    zi_dou_branch = pbranch(zd)

    return Astrolabe(birth=birth, settings=settings, solar=solar, true_solar=true_solar, lunar=lunar,
                     pillars=pillars, year_stem=year_stem, year_branch=year_branch, hour_index=hour_index,
                     lunar_month_index=month_index, lunar_day=lunar_day, soul_index=soul_index,
                     body_index=body_index, bureau_num=bureau, palaces=palaces, birth_hua=birth_hua,
                     laiyin_index=laiyin_index, zi_dou_branch=zi_dou_branch)
