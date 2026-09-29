"""Person (人物档案) models — birth data is the single source of truth."""
from __future__ import annotations

import re
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator

_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")


class BirthData(BaseModel):
    solar: str                         # "2000-01-01 12:00" (clock time, UTC+8)
    longitude: float = 120.0
    place: str = ""
    use_true_solar_time: bool = True
    hour_override: Optional[int] = None  # 0..12, manual 时辰
    time_source: str = "clock"           # clock | true_solar (how the user entered it)

    @field_validator("solar")
    @classmethod
    def _check_solar(cls, v: str) -> str:
        for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M:%S"):
            try:
                datetime.strptime(v, fmt)
                return v[:16].replace("T", " ")
            except ValueError:
                continue
        raise ValueError("出生时间格式应为 YYYY-MM-DD HH:MM")


class PersonSettings(BaseModel):
    ziwei: dict = Field(default_factory=dict)
    bazi: dict = Field(default_factory=dict)


class Note(BaseModel):
    ts: str = Field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    text: str
    author: str = "user"   # user | ai


class Person(BaseModel):
    id: str
    display_name: str
    gender: str = "男"
    birth: BirthData
    settings: PersonSettings = Field(default_factory=PersonSettings)
    notes: list[Note] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    life_facts: dict = Field(default_factory=dict)   # 反推时辰问卷的答案（结婚年、子女、父母、离家等）
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    updated_at: str = Field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))

    @field_validator("id")
    @classmethod
    def _check_id(cls, v: str) -> str:
        if not _ID_RE.match(v):
            raise ValueError("人物标识只能用小写字母/数字/-/_，1-32 位")
        return v

    @field_validator("gender")
    @classmethod
    def _check_gender(cls, v: str) -> str:
        if v in ("男", "male", "M", "m"):
            return "男"
        if v in ("女", "female", "F", "f"):
            return "女"
        raise ValueError("性别应为 男/女")


class PersonCreate(BaseModel):
    id: Optional[str] = None
    display_name: str
    gender: str = "男"
    birth: BirthData
    settings: Optional[PersonSettings] = None
    tags: list[str] = Field(default_factory=list)


class PersonUpdate(BaseModel):
    display_name: Optional[str] = None
    gender: Optional[str] = None
    birth: Optional[BirthData] = None
    settings: Optional[PersonSettings] = None
    tags: Optional[list[str]] = None
    life_facts: Optional[dict] = None


class PersonSummary(BaseModel):
    id: str
    display_name: str
    gender: str
    birth_solar: str
    yinyang_gender: str = ""
    bureau: str = ""
    lunar: str = ""
    updated_at: str = ""
    note_count: int = 0
