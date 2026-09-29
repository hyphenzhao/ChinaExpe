"""按时辰前后挪动出生时间，用于「上下调日期时辰」预览与反推时辰的候选盘。

做法：在**真太阳时**上把时间挪到目标时辰的中点，再按经度反算钟表时间，交给两套引擎重算。
不用 `hour_override`：它只改紫微的时辰，八字时柱、日柱与农历都不会跟着变。

一天按 13 个时辰位排列：早子(00:00–01:00) 丑 寅 … 亥 晚子(23:00–24:00)。
沿时间顺序连续编号，所以「亥时往后一格」是当天晚子，再往后一格是次日早子，跨日自然成立。
默认设置下（晚子不换日），当天晚子与次日早子是两张不同的盘。
"""
from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, time, timedelta
from typing import Optional

from . import calendar as cal
from .settings import BirthInput

SLOT_NAMES = ["早子", "丑", "寅", "卯", "辰", "巳", "午", "未", "申", "酉", "戌", "亥", "晚子"]
SLOT_MID = [time(0, 30)] + [time(2 * i, 0) for i in range(1, 12)] + [time(23, 30)]
SLOT_RANGE = ["00:00–01:00"] + [f"{2 * i - 1:02d}:00–{2 * i + 1:02d}:00" for i in range(1, 12)] + ["23:00–24:00"]
PER_DAY = 13


def to_true_solar(birth: BirthInput, clock: Optional[datetime] = None) -> datetime:
    dt = clock or birth.solar
    return cal.true_solar_time(dt, birth.longitude) if birth.use_true_solar_time else dt


def clock_for_true_solar(target: datetime, birth: BirthInput) -> datetime:
    """反算：给定真太阳时，求对应的钟表时间（均时差随日期变，迭代两次）。"""
    if not birth.use_true_solar_time:
        return target
    guess = target
    for _ in range(3):
        ts = cal.true_solar_time(guess, birth.longitude)
        diff = target - ts
        if abs(diff.total_seconds()) < 60:
            break
        guess = guess + diff
    return guess.replace(second=0, microsecond=0)


def current_slot(birth: BirthInput) -> tuple[date, int]:
    """(真太阳时日期, 时辰位 0..12)；手动指定时辰时以指定为准。"""
    ts = to_true_solar(birth)
    slot = birth.hour_override if birth.hour_override is not None else cal.hour_index(ts)
    return ts.date(), int(slot)


def _at_slot(birth: BirthInput, d: date, slot: int) -> BirthInput:
    target = datetime.combine(d, SLOT_MID[slot])
    return replace(birth, solar=clock_for_true_solar(target, birth), hour_override=None)


def shift(birth: BirthInput, days: int = 0, slots: int = 0) -> BirthInput:
    """前后挪 `days` 天、`slots` 个时辰位。只挪日期时保留原分钟，已知的准确时间不被改动。"""
    if slots == 0:
        if days == 0:
            return birth
        return replace(birth, solar=birth.solar + timedelta(days=days))
    d, s = current_slot(birth)
    linear = s + slots
    return _at_slot(birth, d + timedelta(days=days + linear // PER_DAY), linear % PER_DAY)


def describe(birth: BirthInput) -> dict:
    d, s = current_slot(birth)
    ts = to_true_solar(birth)
    return {"date": d.isoformat(), "slot": s, "slot_name": SLOT_NAMES[s] + ("时" if 0 < s < 12 else ""),
            "true_solar": ts.strftime("%Y-%m-%d %H:%M"), "clock": birth.solar.strftime("%Y-%m-%d %H:%M"),
            "range": SLOT_RANGE[s], "label": f"{d.isoformat()} {SLOT_NAMES[s]}{'时' if 0 < s < 12 else ''}"}


def candidates(birth: BirthInput, approx: Optional[datetime] = None, radius: int = 2) -> list[BirthInput]:
    """反推时辰的候选盘。

    - 给了大致时间（钟表时间）：取该时辰前后各 `radius` 个位，共 2×radius+1 个，可跨日。
    - 没给：出生日（真太阳时）的全部 13 个位，外加前一天的晚子，共 14 个。
    """
    if approx is not None:
        base = replace(birth, solar=approx, hour_override=None)
        return [shift(base, slots=k) if k else _at_slot(base, *current_slot(base))
                for k in range(-radius, radius + 1)]
    d, _ = current_slot(birth)
    out = [_at_slot(birth, d - timedelta(days=1), 12)]
    out += [_at_slot(birth, d, s) for s in range(PER_DAY)]
    return out
