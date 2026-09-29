"""格局规则与事件打分读的轻量盘面视图。

规则只需要「哪颗星在哪一宫、亮度、生年四化」，不必拖着整个 Astrolabe。
`make_view` 让测试可以手工摆盘，逐条验证规则。宫位索引与引擎一致：0 = 寅。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .constants import pidx

# 以某宫为命时其余各宫的偏移（与引擎 PALACE_NAMES 一致）
OFFSET = {"命": 0, "父": 1, "福": 2, "田": 3, "官": 4, "友": 5, "迁": 6, "疾": 7,
          "财": 8, "子": 9, "夫": 10, "兄": 11}
SHA = ("擎羊", "陀罗", "火星", "铃星", "地空", "地劫")
KONG = ("地空", "地劫", "旬空", "截空", "天空")
MAJORS = ("紫微", "天机", "太阳", "武曲", "天同", "廉贞", "天府", "太阴", "贪狼", "巨门",
          "天相", "天梁", "七杀", "破军")
BRIGHT = ("庙", "旺")
DARK = ("陷", "不")
LIUHE = {"子": "丑", "丑": "子", "寅": "亥", "亥": "寅", "卯": "戌", "戌": "卯",
         "辰": "酉", "酉": "辰", "巳": "申", "申": "巳", "午": "未", "未": "午"}


@dataclass
class PalaceView:
    index: int
    branch: str
    stem: str = ""
    name: str = ""
    stars: dict[str, dict] = field(default_factory=dict)   # name -> {brightness, birth_hua, self_out}


@dataclass
class ChartView:
    palaces: list[PalaceView]
    soul: int
    body: int
    year_stem: str = ""
    birth_hua: dict[str, str] = field(default_factory=dict)   # 禄/权/科/忌 -> 星名

    # ---- 位置
    def at(self, base: int, key: str) -> int:
        return (base + OFFSET[key]) % 12

    @staticmethod
    def sfsz(i: int) -> list[int]:
        """三方四正：本宫、官禄位、财帛位、对宫。"""
        return [i % 12, (i + 4) % 12, (i + 8) % 12, (i + 6) % 12]

    @staticmethod
    def jia(i: int) -> tuple[int, int]:
        return ((i - 1) % 12, (i + 1) % 12)

    # ---- 星曜
    def stars(self, i: int) -> dict[str, dict]:
        return self.palaces[i % 12].stars

    def majors(self, i: int, borrow: bool = False) -> list[str]:
        own = [s for s in self.stars(i) if s in MAJORS]
        if own or not borrow:
            return own
        return [s for s in self.stars(i + 6) if s in MAJORS]

    def where(self, star: str) -> Optional[int]:
        for p in self.palaces:
            if star in p.stars:
                return p.index
        return None

    def has(self, idxs, *stars: str) -> bool:
        pool = set()
        for i in ([idxs] if isinstance(idxs, int) else idxs):
            pool |= set(self.stars(i))
        return all(s in pool for s in stars)

    def any_of(self, idxs, stars) -> list[str]:
        idxs = [idxs] if isinstance(idxs, int) else idxs
        return [s for i in idxs for s in self.stars(i) if s in stars]

    def brightness(self, star: str) -> Optional[str]:
        i = self.where(star)
        return None if i is None else self.stars(i)[star].get("brightness")

    def hua_star(self, hua: str) -> Optional[str]:
        return self.birth_hua.get(hua)

    def hua_where(self, hua: str) -> Optional[int]:
        s = self.hua_star(hua)
        return None if s is None else self.where(s)

    def lu_positions(self) -> list[int]:
        """禄存与生年化禄所在宫。"""
        return [i for i in (self.where("禄存"), self.hua_where("禄")) if i is not None]

    def branch(self, i: int) -> str:
        return self.palaces[i % 12].branch

    def name(self, i: int) -> str:
        return self.palaces[i % 12].name


def from_astrolabe(a) -> ChartView:
    palaces = []
    for p in a.palaces:
        palaces.append(PalaceView(
            index=p.index, branch=p.branch, stem=p.stem, name=p.name,
            stars={s.name: {"brightness": s.brightness, "birth_hua": s.birth_hua,
                            "self_out": s.self_hua_out, "self_in": s.self_hua_in} for s in p.stars}))
    return ChartView(palaces=palaces, soul=a.soul_index, body=a.body_index,
                     year_stem=a.year_stem, birth_hua=dict(a.birth_hua))


_NAMES = ["命宫", "父母宫", "福德宫", "田宅宫", "官禄宫", "交友宫", "迁移宫", "疾厄宫",
          "财帛宫", "子女宫", "夫妻宫", "兄弟宫"]
_BRANCHES = "寅卯辰巳午未申酉戌亥子丑"


def make_view(layout: dict[str, list[str]], soul_branch: str, body_branch: Optional[str] = None,
              birth_hua: Optional[dict[str, str]] = None, year_stem: str = "甲") -> ChartView:
    """测试用：`{"寅": ["紫微:庙", "天府"]}`，冒号后是亮度。"""
    soul = pidx(soul_branch)
    body = pidx(body_branch) if body_branch else soul
    hua = birth_hua or {}
    by_star = {v: k for k, v in hua.items()}
    palaces = []
    for i, br in enumerate(_BRANCHES):
        stars = {}
        for token in layout.get(br, []):
            name, _, bright = token.partition(":")
            stars[name] = {"brightness": bright or None, "birth_hua": by_star.get(name),
                           "self_out": None, "self_in": None}
        palaces.append(PalaceView(index=i, branch=br, name=_NAMES[(i - soul) % 12], stars=stars))
    return ChartView(palaces=palaces, soul=soul, body=body, year_stem=year_stem, birth_hua=hua)
