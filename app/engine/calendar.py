"""Calendar helpers: 真太阳时, 农历, 节气四柱, 干支 utilities.

All datetimes are naive and interpreted as Beijing time (UTC+8), which is what
文墨天机 / 测测 use for Chinese charts.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta

from lunar_python import Lunar, Solar  # vendored

STEMS = "甲乙丙丁戊己庚辛壬癸"
BRANCHES = "子丑寅卯辰巳午未申酉戌亥"
BRANCH_HOURS = "子丑寅卯辰巳午未申酉戌亥"
CN_NUM = "零一二三四五六七八九十"

# 农历日名
LUNAR_DAY_NAMES = [
    "初一", "初二", "初三", "初四", "初五", "初六", "初七", "初八", "初九", "初十",
    "十一", "十二", "十三", "十四", "十五", "十六", "十七", "十八", "十九", "二十",
    "廿一", "廿二", "廿三", "廿四", "廿五", "廿六", "廿七", "廿八", "廿九", "三十",
]
LUNAR_MONTH_NAMES = ["正", "二", "三", "四", "五", "六", "七", "八", "九", "十", "冬", "腊"]


def stem_index(stem: str) -> int:
    return STEMS.index(stem)


def branch_index(branch: str) -> int:
    return BRANCHES.index(branch)


def ganzhi(stem_i: int, branch_i: int) -> str:
    return STEMS[stem_i % 10] + BRANCHES[branch_i % 12]


def ganzhi_from_cycle(n: int) -> str:
    """0 -> 甲子 ... 59 -> 癸亥."""
    return STEMS[n % 10] + BRANCHES[n % 12]


def cycle_index(gz: str) -> int:
    """甲子 -> 0 ... 癸亥 -> 59."""
    s, b = stem_index(gz[0]), branch_index(gz[1])
    for n in range(60):
        if n % 10 == s and n % 12 == b:
            return n
    raise ValueError(gz)


# ---------------------------------------------------------------------------
# 真太阳时
# ---------------------------------------------------------------------------

def _julian_day(dt_utc: datetime) -> float:
    y, m = dt_utc.year, dt_utc.month
    d = dt_utc.day + (dt_utc.hour + dt_utc.minute / 60.0 + dt_utc.second / 3600.0) / 24.0
    if m <= 2:
        y -= 1
        m += 12
    a = y // 100
    b = 2 - a + a // 4
    return int(365.25 * (y + 4716)) + int(30.6001 * (m + 1)) + d + b - 1524.5


def equation_of_time_minutes(dt: datetime, tz_hours: float = 8.0) -> float:
    """Equation of time in minutes (apparent − mean solar time), Meeus ch. 28.

    Accuracy is a few seconds, which matters because 文墨天机 truncates the
    真太阳时 to the minute.
    """
    jd = _julian_day(dt - timedelta(hours=tz_hours))
    t = (jd - 2451545.0) / 36525.0
    rad = math.radians
    l0 = (280.46646 + 36000.76983 * t + 0.0003032 * t * t) % 360.0
    m = rad((357.52911 + 35999.05029 * t - 0.0001537 * t * t) % 360.0)
    c = ((1.914602 - 0.004817 * t - 0.000014 * t * t) * math.sin(m)
         + (0.019993 - 0.000101 * t) * math.sin(2 * m)
         + 0.000289 * math.sin(3 * m))
    sun_true = l0 + c
    omega = rad(125.04 - 1934.136 * t)
    lam = rad(sun_true - 0.00569 - 0.00478 * math.sin(omega))
    eps0 = 23.0 + (26.0 + (21.448 - t * (46.8150 + t * (0.00059 - t * 0.001813))) / 60.0) / 60.0
    eps = rad(eps0 + 0.00256 * math.cos(omega))
    alpha = math.degrees(math.atan2(math.cos(eps) * math.sin(lam), math.cos(lam))) % 360.0
    delta_psi = -0.00478 * math.sin(omega)
    e_deg = l0 - 0.0057183 - alpha + delta_psi * math.cos(eps)
    e_deg = (e_deg + 180.0) % 360.0 - 180.0
    return e_deg * 4.0


def true_solar_time(dt: datetime, longitude: float, tz_meridian: float = 120.0) -> datetime:
    """Convert clock time (UTC+8) to 真太阳时 for ``longitude`` (east positive).

    文墨天机 truncates the result to whole minutes, which we replicate.
    """
    offset = 4.0 * (longitude - tz_meridian) + equation_of_time_minutes(dt)
    result = dt.replace(second=0, microsecond=0) + timedelta(seconds=round(offset * 60))
    # truncate to whole minute (文墨 shows 19:8 for 19:08.7)
    return result.replace(second=0, microsecond=0)


def hour_index(dt: datetime) -> int:
    """时辰 index: 0 早子(00-01), 1 丑 ... 11 亥(21-23), 12 晚子(23-24)."""
    h = dt.hour
    if h == 23:
        return 12
    return (h + 1) // 2


def hour_branch(dt: datetime) -> str:
    return BRANCHES[hour_index(dt) % 12]


# ---------------------------------------------------------------------------
# 农历 / 四柱
# ---------------------------------------------------------------------------

@dataclass
class LunarInfo:
    year: int            # 农历年 (numeric, e.g. 1994)
    month: int           # 1..12 (positive even when leap)
    day: int             # 1..30
    is_leap: bool
    year_gz: str         # 甲戌 (by 正月初一)
    hour_branch: str     # 戌
    hour_index: int      # 0..12
    text: str            # e.g. 庚辰年正月初一日子时

    @property
    def month_name(self) -> str:
        return ("闰" if self.is_leap else "") + LUNAR_MONTH_NAMES[self.month - 1] + "月"


@dataclass
class Pillars:
    jieqi: list[str]      # 节气四柱 (年以立春, 月以节)
    non_jieqi: list[str]  # 非节气四柱 (年以正月初一, 月以农历月)

    def as_dict(self) -> dict:
        return {"jieqi": list(self.jieqi), "non_jieqi": list(self.non_jieqi)}


def to_solar(dt: datetime) -> Solar:
    return Solar.fromYmdHms(dt.year, dt.month, dt.day, dt.hour, dt.minute, dt.second)


def lunar_info(dt: datetime) -> LunarInfo:
    """农历 date for a (true-solar) datetime.  晚子时 (23:00+) is kept on the same day."""
    solar = to_solar(dt)
    lunar = solar.getLunar()
    month = lunar.getMonth()
    is_leap = month < 0
    month = abs(month)
    year = lunar.getYear()
    hb = hour_branch(dt)
    year_gz = lunar.getYearInGanZhi()  # by 正月初一
    text = f"{year_gz}年{'闰' if is_leap else ''}{LUNAR_MONTH_NAMES[month - 1]}月{LUNAR_DAY_NAMES[lunar.getDay() - 1]}日{hb}时"
    return LunarInfo(year=year, month=month, day=lunar.getDay(), is_leap=is_leap,
                     year_gz=year_gz, hour_branch=hb, hour_index=hour_index(dt), text=text)


def four_pillars(dt: datetime) -> Pillars:
    """节气四柱 and 非节气四柱 for a (true-solar) datetime."""
    lunar = to_solar(dt).getLunar()
    ec = lunar.getEightChar()
    ec.setSect(2)  # 晚子时日柱算当天 (文墨/测测 default)
    jieqi = [ec.getYear(), ec.getMonth(), ec.getDay(), ec.getTime()]
    # 非节气: 年柱按正月初一, 月柱按农历月 (lunar_python: getYearInGanZhi / getMonthInGanZhi)
    non = [lunar.getYearInGanZhi(), lunar.getMonthInGanZhi(), ec.getDay(), ec.getTime()]
    return Pillars(jieqi=jieqi, non_jieqi=non)


def eight_char(dt: datetime):
    """Return a lunar_python EightChar (sect 2) for a (true-solar) datetime."""
    ec = to_solar(dt).getLunar().getEightChar()
    ec.setSect(2)
    return ec


def solar_from_lunar(year: int, month: int, day: int, is_leap: bool = False) -> datetime:
    """农历 -> 公历 (noon)."""
    lunar = Lunar.fromYmd(year, -month if is_leap else month, day)
    s = lunar.getSolar()
    return datetime(s.getYear(), s.getMonth(), s.getDay(), 12, 0)


def lunar_month_days(year: int, month: int, is_leap: bool = False) -> int:
    from lunar_python import LunarMonth
    m = LunarMonth.fromYm(year, -month if is_leap else month)
    return m.getDayCount()


def lunar_leap_month(year: int) -> int:
    """Return the leap month number of a lunar year (0 if none)."""
    from lunar_python import LunarYear
    return LunarYear.fromYear(year).getLeapMonth()


def year_ganzhi_of(year: int) -> str:
    """干支 of a calendar/lunar year number (1984 -> 甲子)."""
    return ganzhi_from_cycle((year - 1984) % 60)


def day_ganzhi(dt: datetime) -> str:
    ec = eight_char(dt)
    return ec.getDay()


def month_ganzhi_by_jieqi(dt: datetime) -> str:
    return eight_char(dt).getMonth()


def year_ganzhi_by_jieqi(dt: datetime) -> str:
    return eight_char(dt).getYear()


def parse_dt(s: str) -> datetime:
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    raise ValueError(f"bad datetime: {s}")
