"""Parser for 文墨天机 紫微斗数命盘 text exports.

The export is a tree-drawn text (├ │ └).  We normalise it into a plain dict
that mirrors the engine's output so golden tests can compare field by field.

Also understands the simplified ``ziwei.txt`` format produced by the old app::

    命宫 (甲申): 贪狼(平), 禄存(庙), 铃星(陷)[忌], ...
"""
from __future__ import annotations

import re
from typing import Any

_TREE_CHARS = "│├└┌┐┏┓─ \t"
_BRIGHT = "庙旺得利平不陷"

PALACE_NAMES = ["命宫", "兄弟宫", "夫妻宫", "子女宫", "财帛宫", "疾厄宫",
                "迁移宫", "交友宫", "官禄宫", "田宅宫", "福德宫", "父母宫"]
_PALACE_ALIASES = {"命  宫": "命宫", "命 宫": "命宫", "仆役宫": "交友宫", "奴仆宫": "交友宫",
                   "事业宫": "官禄宫", "夫妻宫": "夫妻宫"}


def _clean(line: str) -> str:
    line = line.replace("\\", "")  # markdown-escaped exports (\[ \] \~)
    return line.lstrip(_TREE_CHARS).rstrip()


def _norm_palace(name: str) -> str:
    name = name.replace(" ", "")
    return _PALACE_ALIASES.get(name, name)


_STAR_RE = re.compile(r"([^\[\],，]+?)((?:\[[^\]]*\])*)(?:,|，|$)")
_TAG_RE = re.compile(r"\[([^\]]*)\]")


def parse_star_list(text: str) -> list[dict[str, Any]]:
    """'巨门[旺][生年忌][↑忌],文昌[得][↓科]' -> list of star dicts."""
    text = text.strip()
    if not text or text == "无":
        return []
    out = []
    for m in _STAR_RE.finditer(text):
        name = m.group(1).strip()
        if not name:
            continue
        tags = _TAG_RE.findall(m.group(2))
        star = {"name": name, "brightness": None, "birth_hua": None,
                "self_hua_out": None, "self_hua_in": None}
        for t in tags:
            t = t.strip()
            if t in _BRIGHT:
                star["brightness"] = t
            elif t.startswith("生年"):
                star["birth_hua"] = t[-1]
            elif t.startswith("↓"):
                star["self_hua_out"] = t[-1]
            elif t.startswith("↑"):
                star["self_hua_in"] = t[-1]
            elif t in "禄权科忌":
                # simplified format: ambiguous, keep as birth_hua candidate
                star["birth_hua"] = t
        out.append(star)
    return out


def _ages(text: str) -> list[int]:
    return [int(x) for x in re.findall(r"\d+", text)]


def parse_wenmo_export(text: str) -> dict[str, Any]:
    """Parse the full 文墨天机 export text."""
    lines = [_clean(l) for l in text.splitlines()]
    lines = [l for l in lines if l]

    result: dict[str, Any] = {"basic": {}, "palaces": [], "decadals": []}
    basic = result["basic"]
    palaces = result["palaces"]
    decadals = result["decadals"]

    section = None
    cur_palace: dict | None = None
    cur_decadal: dict | None = None
    cur_year: dict | None = None
    hua_re = re.compile(r"([一-龥]+?)(禄|权|科|忌)(?:,|，|$)")

    for line in lines:
        if line.startswith("基本信息"):
            section = "basic"
            continue
        if line.startswith("命盘十二宫"):
            section = "palaces"
            continue
        if line.startswith("大限流年信息"):
            section = "decadals"
            continue
        if line.startswith("[备注"):
            break

        if section == "basic":
            m = re.match(r"(.+?)\s*[:：]\s*(.*)", line)
            if not m:
                continue
            key, val = m.group(1).strip(), m.group(2).strip()
            if key == "性别":
                basic["gender"] = val
            elif key == "地理经度":
                basic["longitude"] = float(val)
            elif key == "钟表时间":
                basic["clock_time"] = val
            elif key == "真太阳时":
                basic["true_solar_time"] = val
            elif key == "农历时间":
                basic["lunar"] = val
            elif key == "节气四柱":
                basic["pillars_jieqi"] = val.split()
            elif key == "非节气四柱":
                basic["pillars_non_jieqi"] = val.split()
            elif key == "五行局数":
                basic["bureau"] = val
            elif key.startswith("身主"):
                # 身主:文昌; 命主:文曲; 子年斗君:巳; 身宫:巳
                for part in re.split(r"[;；]", key + ":" + val):
                    mm = re.match(r"\s*(\S+?)\s*[:：]\s*(\S+)", part)
                    if mm:
                        k, v = mm.group(1), mm.group(2)
                        basic[{"身主": "shen_zhu", "命主": "ming_zhu", "子年斗君": "zi_dou", "身宫": "shen_gong"}.get(k, k)] = v
            continue

        if section == "palaces":
            m = re.match(r"^([^\[\]:：]+?)\s*\[([甲乙丙丁戊己庚辛壬癸][子丑寅卯辰巳午未申酉戌亥])\]((?:\[[^\]]*\])*)$", line)
            if m:
                cur_palace = {
                    "name": _norm_palace(m.group(1)),
                    "ganzhi": m.group(2),
                    "markers": _TAG_RE.findall(m.group(3)),
                    "major": [], "minor": [], "adjective": [],
                    "suiqian": None, "jiangqian": None, "changsheng": None, "boshi": None,
                    "decadal": None, "ages": [], "yearly_ages": [],
                }
                palaces.append(cur_palace)
                continue
            if cur_palace is None:
                continue
            m = re.match(r"(.+?)\s*[:：]\s*(.*)", line)
            if not m:
                continue
            key, val = m.group(1).strip(), m.group(2).strip()
            if key == "主星":
                cur_palace["major"] = parse_star_list(val)
            elif key == "辅星":
                cur_palace["minor"] = parse_star_list(val)
            elif key == "小星":
                cur_palace["adjective"] = parse_star_list(val)
            elif key == "岁前星":
                cur_palace["suiqian"] = val
            elif key == "将前星":
                cur_palace["jiangqian"] = val.replace("將", "将")
            elif key == "十二长生":
                cur_palace["changsheng"] = val
            elif key == "太岁煞禄":
                cur_palace["boshi"] = val
            elif key == "大限":
                a = _ages(val)
                cur_palace["decadal"] = [a[0], a[1]] if len(a) >= 2 else None
            elif key == "小限":
                cur_palace["ages"] = _ages(val)
            elif key == "流年":
                cur_palace["yearly_ages"] = _ages(val)
            continue

        if section == "decadals":
            m = re.match(r"^第(\d+)大限\[(\S\S)\]$", line)
            if m:
                cur_decadal = {"index": int(m.group(1)), "ganzhi": m.group(2), "years": []}
                decadals.append(cur_decadal)
                cur_year = None
                continue
            if cur_decadal is None:
                continue
            m = re.match(r"^起止年份\s*[:：]\s*(\d+)年\((\d+)虚岁\)\s*~\s*(\d+)年\((\d+)虚岁\)", line)
            if m:
                cur_decadal["start_year"], cur_decadal["start_age"] = int(m.group(1)), int(m.group(2))
                cur_decadal["end_year"], cur_decadal["end_age"] = int(m.group(3)), int(m.group(4))
                continue
            m = re.match(r"^大限四化\s*[:：]\s*(.*)$", line)
            if m:
                cur_decadal["hua"] = {h: s for s, h in hua_re.findall(m.group(1))}
                continue
            m = re.match(r"^(\d+)年\[(\S\S)\]\((\d+)虚岁\)$", line)
            if m:
                cur_year = {"year": int(m.group(1)), "ganzhi": m.group(2), "age": int(m.group(3))}
                cur_decadal["years"].append(cur_year)
                continue
            if cur_year is not None:
                m = re.match(r"^命宫干支\s*[:：]\s*(\S\S)$", line)
                if m:
                    cur_year["soul_ganzhi"] = m.group(1)
                    continue
                m = re.match(r"^流年四化\s*[:：]\s*(.*)$", line)
                if m:
                    cur_year["hua"] = {h: s for s, h in hua_re.findall(m.group(1))}
                    continue
    return result


_SIMPLE_LINE = re.compile(r"^(\S+?)\s*\(([甲乙丙丁戊己庚辛壬癸][子丑寅卯辰巳午未申酉戌亥])\)\s*[:：]\s*(.*)$")
_SIMPLE_STAR = re.compile(r"([^\s,，()]+)\(([^)]*)\)((?:\[[^\]]*\])*)")


def parse_simple_txt(text: str) -> dict[str, Any]:
    """Parse the old app's ``ziwei.txt`` ('命宫 (甲申): 贪狼(平), 禄存(庙)[忌]')."""
    result: dict[str, Any] = {"basic": {}, "palaces": []}
    for raw in text.splitlines():
        line = raw.strip()
        m = re.match(r"^(性别|局数|姓名)\s*[:：]\s*(.+)$", line)
        if m:
            result["basic"][{"性别": "gender", "局数": "bureau", "姓名": "name"}[m.group(1)]] = m.group(2).strip()
            continue
        m = re.match(r"^命主\s*[:：]\s*(\S+)\s+身主\s*[:：]\s*(\S+)", line)
        if m:
            result["basic"]["ming_zhu"], result["basic"]["shen_zhu"] = m.group(1), m.group(2)
            continue
        m = re.match(r"^(jieqi|non_jieqi)\s*[:：]\s*(.+)$", line)
        if m:
            result["basic"]["pillars_" + m.group(1)] = m.group(2).split()
            continue
        m = _SIMPLE_LINE.match(line)
        if not m:
            continue
        stars = []
        for sm in _SIMPLE_STAR.finditer(m.group(3)):
            b = sm.group(2).strip() or None
            tags = _TAG_RE.findall(sm.group(3))
            stars.append({"name": sm.group(1), "brightness": b if (b and b in _BRIGHT) else None,
                          "hua_tags": tags})
        result["palaces"].append({"name": _norm_palace(m.group(1)), "ganzhi": m.group(2), "stars": stars})
    return result
