from datetime import datetime

from conftest import SAMPLE
from app.engine import calendar as cal


def test_hour_index():
    assert cal.hour_index(datetime(2020, 1, 1, 0, 30)) == 0
    assert cal.hour_index(datetime(2020, 1, 1, 1, 0)) == 1
    assert cal.hour_index(datetime(2020, 1, 1, 22, 59)) == 11
    assert cal.hour_index(datetime(2020, 1, 1, 23, 0)) == 12


def test_true_solar_time_sample():
    # 116.4°E is 14.4 min behind the 120°E zone meridian; the equation of time
    # on 1 January is about -3 min, so true solar time is about 11:42.
    t = cal.true_solar_time(cal.parse_dt(SAMPLE["solar"]), SAMPLE["longitude"])
    minutes = t.hour * 60 + t.minute
    assert 11 * 60 + 40 <= minutes <= 11 * 60 + 44
    assert t.second == 0  # truncated to the minute (文墨天机 convention)


def test_four_pillars_sample():
    # 2000-01-01 is before 立春 (己卯 year), in the 子 month, on a 戊午 day; noon is the 午 hour.
    t = cal.true_solar_time(cal.parse_dt(SAMPLE["solar"]), SAMPLE["longitude"])
    p = cal.four_pillars(t)
    assert p.jieqi == ["己卯", "丙子", "戊午", "戊午"]
