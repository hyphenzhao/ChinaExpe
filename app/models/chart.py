"""Chart data models for Ziwei Doushu and ShiShen (Bazi)."""
from pydantic import BaseModel
from typing import Optional


# ---- Ziwei Doushu models ----

class StarInfo(BaseModel):
    """A single star in a palace."""
    name: str
    brightness: Optional[str] = None  # 庙/旺/得/利/平/不/陷
    transform: Optional[str] = None   # 禄/权/科/忌 (四化)


class PalaceInfo(BaseModel):
    """A single palace in the Ziwei grid."""
    name: str           # 命宫/父母宫/福德宫/...
    stem_branch: str    # 干支 e.g. 癸未
    grid_row: int       # 0-3 in the 4x4 grid
    grid_col: int       # 0-3
    is_empty: bool = False  # True for the 4 empty center cells
    stars: list[StarInfo] = []
    changsheng: Optional[str] = None  # 十二长生
    major_limit: Optional[str] = None  # 大限
    markers: list[str] = []  # 来因/身宫 etc.
    shen_gong_here: bool = False
    lai_yin_here: bool = False


class ZiweiGridData(BaseModel):
    """Frontend-friendly Ziwei chart data."""
    person: str
    display_name: Optional[str] = None
    gender: Optional[str] = None
    bureau: Optional[str] = None  # 局数
    ming_zhu: Optional[str] = None  # 命主
    shen_zhu: Optional[str] = None  # 身主
    four_pillars: Optional[dict] = None  # {jieqi: [...], non_jieqi: [...]}
    shen_gong: Optional[str] = None
    lai_yin_gong: Optional[str] = None
    palaces: list[PalaceInfo] = []
    transformations: list[dict] = []  # [{star, transform, palace}]
    major_limits: list[dict] = []     # [{pillar, age, year}]


# ---- ShiShen (Bazi Ten Gods) models ----

class StemInfo(BaseModel):
    """A heavenly stem with its Ten God relation."""
    stem: str
    shishen: Optional[str] = None  # 正官/七杀/正印/...


class BranchInfo(BaseModel):
    """An earthly branch."""
    branch: str


class HiddenStemInfo(BaseModel):
    """A hidden stem within an earthly branch."""
    stem: str
    shishen: Optional[str] = None


class PillarInfo(BaseModel):
    """A single pillar (年/月/日/时柱)."""
    pillar: str          # 年柱/月柱/日柱/时柱
    heavenly_stem: StemInfo
    earthly_branch: BranchInfo
    hidden_stems: list[HiddenStemInfo] = []
    nayin: Optional[str] = None     # 纳音
    kongwang: Optional[str] = None  # 空亡
    dishi: Optional[str] = None     # 地势


class ShiShenData(BaseModel):
    """Frontend-friendly ShiShen (Bazi) chart data."""
    person: str
    display_name: Optional[str] = None
    day_master: Optional[str] = None  # e.g. "丙火"
    pillars: list[PillarInfo] = []
    summary: Optional[dict] = None    # {visible_shishen: [...], hidden_shishen: [...]}
    shensha: Optional[dict] = None    # 神煞
    five_elements_status: Optional[dict] = None  # 五行状态


# ---- People list ----

class PersonInfo(BaseModel):
    """Summary of a person's available charts."""
    name: str
    has_ziwei: bool = False
    has_shishen: bool = False
    display_name: Optional[str] = None
