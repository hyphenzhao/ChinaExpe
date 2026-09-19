"""四化 helpers: 宫干飞化, 三方四正."""
from __future__ import annotations

from .astrolabe import Astrolabe
from .constants import HUA


def fly(astro: Astrolabe, palace_index: int) -> dict:
    """宫干飞四化: which stars (and palaces) the given palace's stem transforms."""
    p = astro.palaces[palace_index % 12]
    table = astro.hua_of_stem(p.stem)
    out = {"from_index": p.index, "from_name": p.name, "stem": p.stem, "targets": []}
    for hua in HUA:
        star = table[hua]
        found = astro.find_star(star)
        if not found:
            out["targets"].append({"hua": hua, "star": star, "to_index": None, "to_name": None, "self": False})
            continue
        tp, _ = found
        out["targets"].append({"hua": hua, "star": star, "to_index": tp.index, "to_name": tp.name,
                               "self": tp.index == p.index, "opposite": tp.index == (p.index + 6) % 12})
    return out


def fly_all(astro: Astrolabe) -> list[dict]:
    return [fly(astro, i) for i in range(12)]


def sanfang(palace_index: int) -> dict:
    """三方四正 indices for a palace."""
    i = palace_index % 12
    return {"self": i, "opposite": (i + 6) % 12, "sanhe": [(i + 4) % 12, (i + 8) % 12],
            "all": [i, (i + 4) % 12, (i + 6) % 12, (i + 8) % 12]}


def hua_by_stem(astro: Astrolabe, stem: str) -> list[dict]:
    """Where a stem's 四化 land (used for 大限/流年/流月/流日 overlays)."""
    table = astro.hua_of_stem(stem)
    res = []
    for hua in HUA:
        star = table[hua]
        found = astro.find_star(star)
        res.append({"hua": hua, "star": star, "palace_index": found[0].index if found else None,
                    "palace_name": found[0].name if found else None})
    return res
