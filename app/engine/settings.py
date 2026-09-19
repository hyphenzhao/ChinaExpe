"""Engine settings (流派选项) and birth input."""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional


@dataclass
class ZiweiSettings:
    profile: str = "wenmo"          # 预设名称（仅标识）
    hua_table: str = "default"      # 四化表: default(文墨/全书) | zhongzhou | ...
    huoling: str = "year_hour"      # 火铃起法: year_hour(全书, 年支+时支) | year(中州, 仅年支)
    tianma: str = "year"            # 天马: year(年支) | month(月支)
    year_divide: str = "lunar"      # 年分界: lunar(正月初一) | lichun(立春)
    leap_month: str = "half"        # 闰月: half(前半月算本月, 后半月算下月) | current(算本月) | next(算下月)
    late_zi: str = "current"        # 晚子时: current(算当日) | next(算次日)
    tianshang_tianshi: str = "default"  # default(伤在交友 使在疾厄) | zhongzhou
    age_divide: str = "lunar_year"  # 虚岁分界: lunar_year(正月初一) | birthday

    def as_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Optional[dict]) -> "ZiweiSettings":
        d = d or {}
        s = cls()
        for k, v in d.items():
            if hasattr(s, k) and v is not None:
                setattr(s, k, v)
        return s


@dataclass
class BaziSettings:
    yun_sect: int = 2              # lunar_python 起运流派: 1 | 2 (2 = 按天数精确折算)
    zi_hour_day: str = "current"   # 晚子时日柱: current | next

    def as_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Optional[dict]) -> "BaziSettings":
        d = d or {}
        s = cls()
        for k, v in d.items():
            if hasattr(s, k) and v is not None:
                setattr(s, k, v)
        return s


@dataclass
class BirthInput:
    """Birth data.  ``solar`` is the clock time (UTC+8); the engine derives 真太阳时."""
    solar: datetime
    gender: str                       # 男 | 女
    longitude: float = 120.0
    use_true_solar_time: bool = True
    hour_override: Optional[int] = None   # 手动指定时辰 index (0..12)
    place: str = ""

    @property
    def is_male(self) -> bool:
        return self.gender in ("男", "male", "M", "m")

    def as_dict(self) -> dict:
        return {
            "solar": self.solar.strftime("%Y-%m-%d %H:%M"),
            "gender": "男" if self.is_male else "女",
            "longitude": self.longitude,
            "use_true_solar_time": self.use_true_solar_time,
            "hour_override": self.hour_override,
            "place": self.place,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "BirthInput":
        from .calendar import parse_dt
        return cls(
            solar=parse_dt(d["solar"]),
            gender=d.get("gender", "男"),
            longitude=float(d.get("longitude", 120.0)),
            use_true_solar_time=bool(d.get("use_true_solar_time", True)),
            hour_override=d.get("hour_override"),
            place=d.get("place", "") or "",
        )
