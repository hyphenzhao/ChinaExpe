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
from ..engine.ziwei.patterns import detect as detect_patterns
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
        self._save_hooks: list = []          # called after every successful save
        self._events_cache: dict[str, tuple[str, dict]] = {}

    def on_save(self, fn) -> None:
        """Register a callback run after a person is written (see export_service)."""
        self._save_hooks.append(fn)

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
        self._events_cache.pop(person.id, None)
        for fn in self._save_hooks:
            try:
                fn(person)
            except Exception:
                pass                          # an export failure must not block saving
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
        return self.ziwei_payload(self.astrolabe(pid), self.get(pid))

    @staticmethod
    def ziwei_payload(astro: Astrolabe, person: Person) -> dict:
        data = astro.as_dict()
        data["person"] = {"id": person.id, "display_name": person.display_name, "gender": person.gender,
                          "notes": [n.model_dump() for n in person.notes]}
        data["decadals"] = H.decadal_list(astro)
        data["fly"] = HUA.fly_all(astro)
        data["patterns"] = detect_patterns(astro)
        return data

    # ------------------------------------------------------------ analyses
    def life_events(self, pid: str, now_year: Optional[int] = None) -> dict:
        from ..engine.ziwei.events import life_events as _life
        person = self.get(pid)
        if not person:
            raise KeyError(pid)
        now_year = now_year or datetime.now().year
        key = self._cache_key(person) + f"|{now_year}"
        hit = self._events_cache.get(pid)
        if hit and hit[0] == key:
            return hit[1]
        res = _life(self.astrolabe(pid), self.bazi(pid), now_year=now_year)
        self._events_cache[pid] = (key, res)
        return res

    def analysis(self, pid: str) -> dict:
        """格局、子平分析、人生喜事一次给齐（对话欢迎区用）。"""
        return {"patterns": detect_patterns(self.astrolabe(pid)),
                "bazi": self.bazi(pid).get("analysis"),
                "life_events": self.life_events(pid)}

    def life_events_text(self, pid: str, event: Optional[str] = None) -> str:
        res = self.life_events(pid)
        person = self.get(pid)
        out = [f"# {person.display_name}（{pid}）人生喜事（代码计算，{res['version']}）",
               f"说明：{res['note']}。紫微为主，八字流年十神辅助（加减不超过三成）。"]
        for ev, b in res["events"].items():
            if event and ev != event:
                continue
            out.append(f"\n## {ev}（看{b['palace']}）")
            if not b["future_top"]:
                out.append("- 未来 20 年内已不在常见年龄段")
            for r in b["future_top"]:
                months = "、".join(f"农历{m['name']}" for m in r["months"])
                out.append(f"- {r['year']}年（{r['age']}岁）分 {r['score']}（紫微 {r['ziwei']}，八字 {r['bazi_adj']:+}）"
                           f"，月份倾向：{months}")
                if event:
                    for s in r["signals"]:
                        if s["delta"] or s["text"].startswith("叠宫"):
                            out.append(f"    · {s['layer']} {s['delta']:+.2f} {s['text']}")
            if b["past_strong"]:
                out.append("- 往年强年（可拿来核对）：" + "、".join(f"{r['year']}（{r['age']}岁）" for r in b["past_strong"]))
        return "\n".join(out)

    # ---------------------------------------------------- ad-hoc birth times
    def charts_for_birth(self, person: Person, birth: BirthInput) -> tuple[Astrolabe, dict]:
        """任意出生时间排盘（不落盘），沿用该人物的流派设置。"""
        astro = compute_astrolabe(birth, ZiweiSettings.from_dict(person.settings.ziwei))
        bazi = compute_bazi(birth, BaziSettings.from_dict(person.settings.bazi))
        return astro, bazi

    def variant_text(self, pid: str, days: int = 0, slots: int = 0) -> str:
        """相邻日期/时辰的紫微 + 八字文字版（反推时辰时给 AI 比对用）。"""
        from ..engine import timeshift as TS
        person = self.get(pid)
        if not person:
            raise KeyError(pid)
        birth = TS.shift(self.birth_input(person), days=days, slots=slots)
        astro, bazi = self.charts_for_birth(person, birth)
        lab = TS.describe(birth)
        head = (f"# 候选盘：{lab['label']}（真太阳时 {lab['true_solar']}，钟表 {lab['clock']}；"
                f"相对原盘 {days:+} 天 {slots:+} 个时辰位）")
        return "\n".join([head, self.ziwei_text(pid, astro=astro), "", self.bazi_text(pid, chart=bazi)])

    def preview(self, pid: str, days: int = 0, slots: int = 0) -> dict:
        """前后挪日期/时辰后的盘，用于「上下调」预览。"""
        from ..engine import timeshift as TS
        person = self.get(pid)
        if not person:
            raise KeyError(pid)
        birth = TS.shift(self.birth_input(person), days=days, slots=slots)
        astro, bazi = self.charts_for_birth(person, birth)
        return {"days": days, "slots": slots, "birth": birth.as_dict(), "label": TS.describe(birth),
                "original": TS.describe(self.birth_input(person)),
                "ziwei": self.ziwei_payload(astro, person), "bazi": bazi}

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
    def ziwei_text(self, pid: str, detail: str = "full", astro: Optional[Astrolabe] = None) -> str:
        """Compact but complete textual chart for the LLM (生年四化/自化 分开标注).

        `astro` 可传入候选时辰的盘（反推时辰、上下调预览用），默认用人物已保存的盘。
        """
        person = self.get(pid)
        a = astro or self.astrolabe(pid)
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
        lines.append(patterns_text(detect_patterns(a)))
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

    def bazi_text(self, pid: str, chart: Optional[dict] = None) -> str:
        person = self.get(pid)
        c = chart or self.bazi(pid)
        P = c["pillars"]
        st = (c.get("analysis") or {}).get("strength") or {}
        strength_txt = (f"{st['label']} {st['same_pct']}%{'（临界）' if st.get('border') else ''}"
                        f"{'，' + st['special'] if st.get('special') else ''}") if st else c['strength']['label']
        lines = [f"# {person.display_name}（{pid}）八字（子平/测测口径）", c["birth"]["jieqi_note"],
                 f"四柱: {'｜'.join(p['ganzhi'] for p in P)}；日主 {c['day_master']}；身强弱（代码计算）: {strength_txt}（月令{c['strength']['month_status']}）",
                 "| 柱 | 干神 | 天干 | 地支 | 藏干/支神 | 纳音 | 空亡 | 地势 | 自坐 | 神煞 |", "|---|---|---|---|---|---|---|---|---|---|"]
        for p in P:
            hid = "、".join(f"{h['stem']}({h['shishen']})" for h in p["hidden"])
            lines.append(f"| {p['pos']} | {p['stem_shishen']} | {p['stem']} | {p['branch']} | {hid} | {p['nayin']} | {p['xunkong']} | {p['dishi']} | {p['zizuo']} | {'、'.join(p['shensha']) or '—'} |")
        lines.append("干支关系: " + "；".join(r["text"] for r in c["relations"]["stems"] + c["relations"]["branches"]))
        lines.append("五行状态: " + " ".join(f"{k}{v}" for k, v in c["wuxing_status"].items()))
        lines.append(f"胎元 {c['taiyuan']}，命宫 {c['minggong']}，身宫 {c['shengong']}")
        lines.append(bazi_analysis_text(c.get("analysis")))
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


def patterns_text(r: Optional[dict]) -> str:
    """紫微格局的文字版：成格方向与事实，未判破格。"""
    if not r:
        return ""
    out = ["", f"## 格局（代码判定成格方向，未判破格，{r['version']}）"]
    if r["ming"]["borrowed"]:
        out.append(f"- 命宫无主星，借迁移宫主星：{'、'.join(r['ming']['borrowed_majors']) or '无'}")
    if not r["patterns"]:
        out.append("- 未见常见格局")
    for p in r["patterns"]:
        out.append(f"- [{p['kind']}] {p['name']}（{p['level']}宫）：{'；'.join(p['evidence'])}"
                   + (f"。注：{p['note']}" if p.get("note") else ""))
    c = r["context"]
    facts = [("煞", c["sha"]), ("空亡", c["kong"]), ("生年忌", c["ji"]), ("离心自化忌", c["self_ji"]), ("主星落陷", c["xian"])]
    out.append("- 命宫三方四正与夹宫的事实：" + "；".join(f"{k}：{'、'.join(v)}" for k, v in facts if v) if any(v for _, v in facts)
               else "- 命宫三方四正与夹宫未见煞忌空陷")
    return "\n".join(out)


def bazi_analysis_text(a: Optional[dict]) -> str:
    """子平量化分析的文字版（代码计算结果，给 AI 当事实用）。"""
    if not a:
        return ""
    st, sh, gj, ys = a["strength"], a["shishen"], a["geju"], a["yongshen"]
    flags = "、".join(n for n, on in (("得令", st["de_ling"]), ("得地", st["de_di"]), ("得势", st["de_shi"])) if on) or "三者皆无"
    out = ["", f"## 命局分析（代码计算，{a['version']}）",
           f"- 身强弱: {st['label']}，同类占比 {st['same_pct']}%{'（临界）' if st['border'] else ''}"
           f"{'，' + st['special'] if st['special'] else ''}；{flags}；月令系数来源 {st['coef_source']}",
           "- 五行力量: " + "、".join(f"{e}{p}%" for e, p in st["element_pct"].items()),
           "- 十神占比: " + "、".join(f"{g['group']}{g['pct']}%" for g in sh["groups"])
           + "（" + "、".join(f"{r['shishen']}{r['pct']}%" for r in sh["items"]) + "）"]
    if gj["primary"]:
        out.append(f"- 取格: {gj['primary']['name']}（{gj['primary']['basis']}"
                   f"{'；' + gj['primary']['note'] if gj['primary'].get('note') else ''}）")
    out.append("- 格局候选: " + "、".join(f"{c['name']} {c['pct']}%" for c in gj["candidates"]))
    if gj["special"]:
        out.append("- 特殊格候选: " + "、".join(f"{s['name']} {s['pct']}%" for s in gj["special"]))
    if gj["observations"]:
        out.append("- 与月令/透干相关的合冲（仅事实，未判破格）: " + "、".join(gj["observations"]))
    out.append("- 喜忌排序: " + "，".join(f"{r['role']}{r['element']}({r['score']:+})" for r in ys["ranking"])
               + f"；方法 {ys['method']}")
    return "\n".join(out)


person_service = PersonService()
