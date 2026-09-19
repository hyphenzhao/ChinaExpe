"""Person store (data/people/<id>.json) + engine facade with caching.

Everything the API / AI tools need about a person goes through here, so the
engine is invoked in exactly one place and results are cached per
(person file mtime, settings).
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from ..engine import calendar as cal
from ..engine.settings import BaziSettings, BirthInput, ZiweiSettings
from ..engine.ziwei.astrolabe import Astrolabe, compute_astrolabe
from ..engine.ziwei import horoscope as H
from ..engine.ziwei import hua as HUA
from ..engine.bazi.chart import compute_bazi
from ..engine.bazi import timeline as TL
from ..models.person import Note, Person, PersonCreate, PersonSummary, PersonUpdate

ROOT = Path(__file__).resolve().parent.parent.parent
PEOPLE_DIR = ROOT / "data" / "people"


def _slug(name: str) -> str:
    s = re.sub(r"[^a-z0-9_-]", "", name.lower())
    return s or "p" + datetime.now().strftime("%m%d%H%M")


class PersonService:
    def __init__(self):
        self._astro_cache: dict[str, tuple[str, Astrolabe]] = {}
        self._bazi_cache: dict[str, tuple[str, dict]] = {}

    # ---------------------------------------------------------------- store
    def _path(self, pid: str) -> Path:
        return PEOPLE_DIR / f"{pid}.json"

    def list_ids(self) -> list[str]:
        PEOPLE_DIR.mkdir(parents=True, exist_ok=True)
        return sorted(p.stem for p in PEOPLE_DIR.glob("*.json"))

    def get(self, pid: str) -> Optional[Person]:
        path = self._path(pid)
        if not path.exists():
            return None
        try:
            return Person(**json.loads(path.read_text(encoding="utf-8")))
        except Exception:
            return None

    def save(self, person: Person) -> Person:
        PEOPLE_DIR.mkdir(parents=True, exist_ok=True)
        person.updated_at = datetime.now().isoformat(timespec="seconds")
        self._path(person.id).write_text(person.model_dump_json(indent=2), encoding="utf-8")
        self._astro_cache.pop(person.id, None)
        self._bazi_cache.pop(person.id, None)
        return person

    def create(self, req: PersonCreate) -> Person:
        pid = req.id or _slug(req.display_name)
        if self._path(pid).exists():
            raise ValueError(f"人物 {pid} 已存在")
        person = Person(id=pid, display_name=req.display_name, gender=req.gender, birth=req.birth,
                        settings=req.settings or {}, tags=req.tags)
        return self.save(person)

    def update(self, pid: str, req: PersonUpdate) -> Person:
        person = self.get(pid)
        if not person:
            raise KeyError(pid)
        data = req.model_dump(exclude_none=True)
        for k, v in data.items():
            setattr(person, k, type(getattr(person, k))(**v) if isinstance(v, dict) and k in ("birth", "settings") else v)
        return self.save(person)

    def delete(self, pid: str) -> bool:
        path = self._path(pid)
        if path.exists():
            path.unlink()
            self._astro_cache.pop(pid, None)
            self._bazi_cache.pop(pid, None)
            return True
        return False

    def add_note(self, pid: str, text: str, author: str = "user") -> Person:
        person = self.get(pid)
        if not person:
            raise KeyError(pid)
        person.notes.append(Note(text=text, author=author))
        return self.save(person)

    # --------------------------------------------------------------- engine
    def birth_input(self, person: Person) -> BirthInput:
        b = person.birth
        return BirthInput(solar=cal.parse_dt(b.solar), gender=person.gender, longitude=b.longitude,
                          use_true_solar_time=b.use_true_solar_time, hour_override=b.hour_override,
                          place=b.place)

    def _cache_key(self, person: Person) -> str:
        return json.dumps({"b": person.birth.model_dump(), "g": person.gender,
                           "s": person.settings.model_dump()}, sort_keys=True, ensure_ascii=False)

    def astrolabe(self, pid: str) -> Astrolabe:
        person = self.get(pid)
        if not person:
            raise KeyError(pid)
        key = self._cache_key(person)
        hit = self._astro_cache.get(pid)
        if hit and hit[0] == key:
            return hit[1]
        astro = compute_astrolabe(self.birth_input(person), ZiweiSettings.from_dict(person.settings.ziwei))
        self._astro_cache[pid] = (key, astro)
        return astro

    def bazi(self, pid: str) -> dict:
        person = self.get(pid)
        if not person:
            raise KeyError(pid)
        key = self._cache_key(person)
        hit = self._bazi_cache.get(pid)
        if hit and hit[0] == key:
            return hit[1]
        data = compute_bazi(self.birth_input(person), BaziSettings.from_dict(person.settings.bazi))
        data["person"] = {"id": person.id, "display_name": person.display_name}
        self._bazi_cache[pid] = (key, data)
        return data

    def bazi_settings(self, pid: str) -> BaziSettings:
        person = self.get(pid)
        return BaziSettings.from_dict(person.settings.bazi if person else None)

    def bazi_timeline(self, pid: str, date: datetime) -> dict:
        person = self.get(pid)
        if not person:
            raise KeyError(pid)
        return TL.timeline_for_date(self.birth_input(person), date, self.bazi_settings(pid))

    def ziwei_json(self, pid: str) -> dict:
        person = self.get(pid)
        astro = self.astrolabe(pid)
        data = astro.as_dict()
        data["person"] = {"id": person.id, "display_name": person.display_name, "gender": person.gender,
                          "notes": [n.model_dump() for n in person.notes]}
        data["decadals"] = H.decadal_list(astro)
        data["fly"] = HUA.fly_all(astro)
        return data

    def summary(self, pid: str) -> PersonSummary:
        person = self.get(pid)
        try:
            astro = self.astrolabe(pid)
            return PersonSummary(id=person.id, display_name=person.display_name, gender=person.gender,
                                 birth_solar=person.birth.solar,
                                 yinyang_gender=("阳" if astro.yang_year else "阴") + person.gender,
                                 bureau=astro.bureau, lunar=astro.lunar.text, updated_at=person.updated_at,
                                 note_count=len(person.notes))
        except Exception:
            return PersonSummary(id=person.id, display_name=person.display_name, gender=person.gender,
                                 birth_solar=person.birth.solar, updated_at=person.updated_at,
                                 note_count=len(person.notes))

    def list_summaries(self) -> list[PersonSummary]:
        out = []
        for pid in self.list_ids():
            if self.get(pid):
                out.append(self.summary(pid))
        return out

    # ------------------------------------------------------- text for LLM
    def ziwei_text(self, pid: str, detail: str = "full") -> str:
        """Compact but complete textual chart for the LLM (生年四化/自化 分开标注)."""
        person = self.get(pid)
        a = self.astrolabe(pid)
        lines = [f"# {person.display_name}（{pid}）紫微斗数命盘（引擎排盘，文墨天机口径）",
                 f"性别: {'阳' if a.yang_year else '阴'}{person.gender}；钟表时间 {a.solar:%Y-%m-%d %H:%M}"
                 f"{'，真太阳时 ' + a.true_solar.strftime('%H:%M') if a.birth.use_true_solar_time else ''}；农历 {a.lunar.text}",
                 f"四柱: {' '.join(a.pillars.jieqi)}；五行局: {a.bureau}；命主 {a.ming_zhu}，身主 {a.shen_zhu}；"
                 f"身宫在{a.palaces[a.body_index].name}({a.palaces[a.body_index].ganzhi})；来因宫 {a.palaces[a.laiyin_index].name}；子年斗君 {a.zi_dou_branch}",
                 f"生年四化: " + "、".join(f"{s}化{h}" for h, s in a.birth_hua.items()),
                 "标记说明: [生年X]=生年四化; [↓X]=离心自化(本宫宫干化本宫星); [↑X]=向心自化(对宫宫干化入)",
                 "", "## 十二宫（按命宫起顺行）"]
        order = [(a.soul_index + i) % 12 for i in range(12)]
        for idx in order:
            p = a.palaces[idx]
            def fmt(s):
                t = s.name + (f"[{s.brightness}]" if s.brightness else "")
                if s.birth_hua:
                    t += f"[生年{s.birth_hua}]"
                if s.self_hua_out:
                    t += f"[↓{s.self_hua_out}]"
                if s.self_hua_in:
                    t += f"[↑{s.self_hua_in}]"
                return t
            major = [fmt(s) for s in p.stars if s.category == "major"]
            minor = [fmt(s) for s in p.stars if s.category == "minor"]
            adj = [fmt(s) for s in p.stars if s.category == "adjective"]
            flags = ("【身宫】" if p.is_body else "") + ("【来因】" if p.is_laiyin else "")
            lines.append(f"- {p.name}[{p.ganzhi}]{flags} 大限{p.decadal_start}-{p.decadal_end}岁 "
                         f"主星: {'、'.join(major) or '无'}；辅星: {'、'.join(minor) or '无'}"
                         + (f"；小星: {'、'.join(adj)}" if detail == "full" and adj else "")
                         + f"；长生{p.changsheng} 岁前{p.suiqian} 将前{p.jiangqian} 博士{p.boshi}")
        lines.append("")
        lines.append("## 大限（干支/宫位/年份/大限四化）")
        for d in H.decadal_list(a):
            lines.append(f"- {d['ganzhi']} {d['palace_name']} {d['start_age']}-{d['end_age']}岁 "
                         f"{d['start_year']}-{d['end_year']}: " + "、".join(f"{h['star']}化{h['hua']}({h['palace_name']})" for h in d["hua"]))
        if person.notes:
            lines.append("")
            lines.append("## 备注")
            for n in person.notes[-10:]:
                lines.append(f"- [{n.ts[:10]}] {n.text}")
        return "\n".join(lines)

    def horoscope_text(self, pid: str, date: datetime) -> str:
        a = self.astrolabe(pid)
        d = H.by_date(a, date)
        lines = [f"# 运限 @ {d['solar']}（{d['lunar']}），虚岁 {d['age']}"]
        for lv in ("decadal", "yearly", "monthly", "daily", "hourly"):
            b = d.get(lv)
            if not b:
                continue
            hua = "、".join(f"{h['star']}化{h['hua']}→{h['palace_name']}" for h in b["hua"])
            extra = ""
            if lv == "decadal":
                extra = f" {b['start_age']}-{b['end_age']}岁"
            if lv == "yearly" and b.get("age_palace"):
                extra = f"；小限在{b['age_palace']['name']}({b['age_palace']['stem']}{b['age_palace']['branch']})"
            stars = "、".join(f"{s['name']}→{a.palaces[s['palace_index']].name}" for s in b.get("stars", []))
            lines.append(f"- {b['name']} {b['ganzhi']}{extra}：{b['name']}命宫在{b['palace_name']}({a.palaces[b['index']].ganzhi})；"
                         f"四化: {hua}" + (f"；流曜: {stars}" if stars else ""))
        return "\n".join(lines)

    def fly_text(self, pid: str, palace_name: str) -> str:
        a = self.astrolabe(pid)
        p = a.palace_by_name(palace_name)
        f = HUA.fly(a, p.index)
        parts = [f"{palace_name}[{p.ganzhi}] 宫干{p.stem}飞四化："]
        for t in f["targets"]:
            where = "本宫(自化)" if t.get("self") else ("对宫" if t.get("opposite") else "")
            parts.append(f"  化{t['hua']}: {t['star']} → {t['to_name'] or '不在盘中'} {where}")
        sf = HUA.sanfang(p.index)
        parts.append("三方四正: " + "、".join(a.palaces[i].name for i in sf["all"]))
        return "\n".join(parts)

    def bazi_text(self, pid: str) -> str:
        person = self.get(pid)
        c = self.bazi(pid)
        P = c["pillars"]
        lines = [f"# {person.display_name}（{pid}）八字（子平/测测口径）", c["birth"]["jieqi_note"],
                 f"四柱: {'｜'.join(p['ganzhi'] for p in P)}；日主 {c['day_master']}；日主强弱初判: {c['strength']['label']}（月令{c['strength']['month_status']}）",
                 "| 柱 | 干神 | 天干 | 地支 | 藏干/支神 | 纳音 | 空亡 | 地势 | 自坐 | 神煞 |", "|---|---|---|---|---|---|---|---|---|---|"]
        for p in P:
            hid = "、".join(f"{h['stem']}({h['shishen']})" for h in p["hidden"])
            lines.append(f"| {p['pos']} | {p['stem_shishen']} | {p['stem']} | {p['branch']} | {hid} | {p['nayin']} | {p['xunkong']} | {p['dishi']} | {p['zizuo']} | {'、'.join(p['shensha']) or '—'} |")
        lines.append("干支关系: " + "；".join(r["text"] for r in c["relations"]["stems"] + c["relations"]["branches"]))
        lines.append("五行状态: " + " ".join(f"{k}{v}" for k, v in c["wuxing_status"].items()))
        lines.append(f"胎元 {c['taiyuan']}，命宫 {c['minggong']}，身宫 {c['shengong']}")
        return "\n".join(lines)

    def bazi_timeline_text(self, pid: str, date: datetime) -> str:
        tl = self.bazi_timeline(pid, date)
        lines = [f"# 八字运限 @ {tl['date']}（虚岁 {tl['age']}，{'顺' if tl['forward'] else '逆'}排，{tl['start']['text']}，起运日 {tl['start']['date']}）",
                 "大运序列: " + " ".join(f"{d['ganzhi']}({d['start_age']}岁/{d['start_year']})" for d in tl["dayun_all"] if d["index"] >= 1)]
        for k, name in (("dayun", "大运"), ("liunian", "流年"), ("liuyue", "流月"), ("liuri", "流日"), ("liushi", "流时")):
            p = tl[k]
            if not p or not p.get("ganzhi"):
                continue
            hid = "、".join(f"{h['stem']}{h['shishen']}" for h in p["hidden"])
            lines.append(f"- {name} {p['ganzhi']}：干{p['stem_shishen']}；支藏 {hid}；地势{p['dishi']} 自坐{p['zizuo']}；空亡{p['xunkong']}；神煞 {'、'.join(p['shensha']) or '—'}")
        return "\n".join(lines)


person_service = PersonService()
