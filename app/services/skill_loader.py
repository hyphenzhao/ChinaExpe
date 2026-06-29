"""Load SKILL.md and reference files from the skills directory."""
import os
import re
import yaml
from pathlib import Path
from typing import Optional

SKILLS_PATH = Path("/Volumes/Storage/OpenClaw-Space/skills")

# Map chart types to skills and their references
SKILL_MAP = {
    "ziwei": {
        "dir": "ziwei-doushu",
        "display": "紫微斗数",
        "references": [
            "references/calculation.md",
            "references/stars.md",
            "references/sihua.md",
            "references/patterns.md",
        ],
    },
    "bazi": {
        "dir": "bazi-classical",
        "display": "八字经典",
        "references": [
            "references/wuxing-tables.md",
            "references/shichen-table.md",
            "references/dayun-rules.md",
        ],
    },
    "bazi_master": {
        "dir": "bazi-master",
        "display": "八字大师",
        "references": [
            "references/tiangan-dizhi.md",
        ],
    },
    "ziping": {
        "dir": "ziping-zhengliu",
        "display": "子平正解",
        "references": [
            "docs/yuanhai_ziping.md",
        ],
    },
}

# Cache for loaded skill content
_skill_cache: dict[str, dict] = {}


def parse_skill_md(filepath: Path) -> dict:
    """Parse a SKILL.md file, extracting YAML frontmatter and body."""
    content = filepath.read_text(encoding="utf-8")
    result = {"frontmatter": {}, "body": "", "name": "", "description": ""}

    # Extract YAML frontmatter
    fm_match = re.match(r'^---\s*\n(.*?)\n---\s*\n', content, re.DOTALL)
    if fm_match:
        try:
            fm = yaml.safe_load(fm_match.group(1))
            if fm:
                result["frontmatter"] = fm
                result["name"] = fm.get("name", "")
                result["description"] = fm.get("description", "")
        except yaml.YAMLError:
            pass
        result["body"] = content[fm_match.end():].strip()
    else:
        result["body"] = content

    return result


def load_skill(skill_key: str) -> dict:
    """Load a skill by key, returning {skill_md, references: {name: content}}."""
    if skill_key in _skill_cache:
        return _skill_cache[skill_key]

    info = SKILL_MAP.get(skill_key)
    if not info:
        return {"skill_md": {}, "references": {}}

    skill_dir = SKILLS_PATH / info["dir"]
    result = {"skill_md": {}, "references": {}}

    # Load SKILL.md
    skill_md_path = skill_dir / "SKILL.md"
    if skill_md_path.exists():
        result["skill_md"] = parse_skill_md(skill_md_path)

    # Load reference files
    for ref_path in info.get("references", []):
        full_path = skill_dir / ref_path
        if full_path.exists():
            ref_name = Path(ref_path).stem
            result["references"][ref_name] = full_path.read_text(encoding="utf-8")

    _skill_cache[skill_key] = result
    return result


def load_skills_for_chart_type(chart_type: str) -> dict:
    """Load all relevant skills for a given chart type.

    Args:
        chart_type: 'ziwei' or 'shishen'

    Returns:
        dict with skills and their combined content
    """
    if chart_type == "ziwei":
        keys = ["ziwei"]
    elif chart_type == "shishen":
        keys = ["bazi_master", "ziping", "bazi"]
    else:
        keys = []

    skills = {}
    for key in keys:
        skills[key] = load_skill(key)
    return skills


def _extract_critical_sections(body: str) -> tuple[str, str, str]:
    """Extract 解释边界, 核心规则 and 回应风格 sections from body text.

    These sections contain the critical tone/boundary guidance that must
    never be truncated. Returns (boundaries, rules, style) — each is the
    full section text (heading + content), or "" if not found.
    """
    boundaries = ""
    rules = ""
    style = ""

    # Match ##/### headed sections — stop at next same-or-higher-level heading
    for section_name, target in [
        ("解释边界", "boundaries"),
        ("核心规则", "rules"),
        ("回应风格", "style"),
    ]:
        pattern = (
            r'(?:^|\n)(#{2,3}\s*' + re.escape(section_name) + r'\s*\n'
            r'.*?)(?=\n#{2,3}\s[^#]|\n#\s[^#]|\Z)'
        )
        match = re.search(pattern, body, re.DOTALL)
        if match:
            value = match.group(1).strip()
            if target == "boundaries":
                boundaries = value
            elif target == "rules":
                rules = value
            else:
                style = value

    return boundaries, rules, style


def get_skill_context_for_prompt(chart_type: str) -> str:
    """Assemble skill context as a string for the system prompt.

    Critical tone/boundary sections (解释边界, 核心规则, 回应风格) are
    extracted and placed first so they are never truncated, regardless of
    body length. Total kept under ~20K chars.

    Args:
        chart_type: 'ziwei', 'shishen', or 'theory'

    Returns:
        Formatted string with skill instructions and key reference content
    """
    TONE_GUIDANCE = (
        "## 回答风格与边界（最高优先级）\n"
        "- **客观平衡**：吉凶都要如实解读，不要只说好听的话，也不要刻意吓人，要客观中立\n"
        "- **凶象转译**：凶象要转译为风险、课题、代价、需要注意之处，而非恐吓式、宿命式表述\n"
        "- **解释边界**：命盘展示的是倾向、结构与课题，不是不可改变的命令；不说“注定如此”“无法改变”\n"
        "- **结论依据**：每个判断都要有推演过程支撑，先排盘/分析再下结论\n"
        "- **专业清晰**：术语第一次出现时用现代汉语解释，不堆砌古诀，不空泛玄谈\n"
    )

    if chart_type == "theory":
        return (
            "你是一位精通紫微斗数、子平命理（八字十神）的专业玄学助手。\n\n"
            + TONE_GUIDANCE +
            "\n## 回答格式要求\n"
            "- 涉及星曜、宫位、五行、十神等结构化信息时，**默认使用 Markdown 表格**呈现，表格比纯文字更清晰直观\n"
            "- 如用户明确要求不用表格，则尊重用户偏好\n"
            "- 表格示例：\n"
            "| 宫位 | 干支 | 主星 | 亮度 | 四化 | 要点 |\n"
            "|------|------|------|------|------|------|\n"
            "| 命宫 | 癸未 | 天府 | 庙 | — | 稳重厚实 |\n"
            "- 对比分析、分类列举时优先用表格，文字描述作为补充\n"
            "- 请以专业且易于理解的方式回答用户的问题。回答时引用经典理论和实际技法。\n"
            "\n"
            "> 温馨提示：命理属于中华传统文化系统，解读用于提供自我观察与人生规划的参考视角。"
            "命盘呈现的是结构与倾向，不是不可改变的命令；后天选择与持续行动同样重要。"
            "重大决策仍需结合现实条件，理性判断。"
        )

    skills = load_skills_for_chart_type(chart_type)
    parts = []
    total_len = 0
    MAX_TOTAL = 20000

    # Always put tone guidance first
    parts.append(TONE_GUIDANCE)
    total_len += len(TONE_GUIDANCE)

    for key, skill_data in skills.items():
        info = SKILL_MAP.get(key, {})
        display = info.get("display", key)
        skill_md = skill_data.get("skill_md", {})

        header = f"\n## 技能: {display}\n"
        parts.append(header)
        total_len += len(header)

        # Description
        desc = skill_md.get("description", "")
        if desc and total_len < MAX_TOTAL:
            desc_text = f"**说明**: {desc}\n"
            parts.append(desc_text)
            total_len += len(desc_text)

        # SKILL.md body — extract critical sections first, then the rest
        body = skill_md.get("body", "")
        if body and total_len < MAX_TOTAL:
            boundaries, rules, style = _extract_critical_sections(body)

            # Place critical sections first (never truncated)
            critical_parts = []
            for section in [boundaries, rules, style]:
                if section:
                    critical_parts.append(section)
            if critical_parts:
                critical_text = "\n\n".join(critical_parts)
                parts.append(critical_text)
                total_len += len(critical_text)

            # Then the rest of the body (truncated if needed)
            remaining = MAX_TOTAL - total_len
            if remaining > 1000:
                # Remove the critical sections from body to avoid duplication
                rest_body = body
                for section in [boundaries, rules, style]:
                    if section:
                        rest_body = rest_body.replace(section, "")
                # Clean up multiple blank lines
                rest_body = re.sub(r'\n{3,}', '\n\n', rest_body).strip()
                body_limit = min(len(rest_body), max(6000, remaining))
                if rest_body:
                    body_text = rest_body[:body_limit]
                    if len(rest_body) > body_limit:
                        body_text += "\n\n...（后续内容已截断，核心约束已完整保留）"
                    parts.append("\n" + body_text)
                    total_len += len(body_text)

        # References — include more of them with higher limits
        essential_refs = {
            "ziwei": ["stars", "sihua", "patterns", "calculation"],
            "shishen": ["wuxing-tables", "tiangan-dizhi", "dayun-rules"],
        }.get(chart_type, [])

        for ref_name, ref_content in skill_data.get("references", {}).items():
            if ref_name not in essential_refs:
                continue
            remaining = MAX_TOTAL - total_len
            if remaining <= 500:
                break
            ref_limit = min(len(ref_content), max(3000, remaining))
            ref_text = f"\n### 参考: {ref_name}\n{ref_content[:ref_limit]}"
            if len(ref_content) > ref_limit:
                ref_text += "\n..."
            parts.append(ref_text)
            total_len += len(ref_text)

    return "\n".join(parts)


def clear_cache():
    """Clear the skill content cache."""
    _skill_cache.clear()


def list_available_skills() -> list[dict]:
    """List all available skills with their display names."""
    result = []
    for key, info in SKILL_MAP.items():
        skill_dir = SKILLS_PATH / info["dir"]
        exists = skill_dir.exists()
        result.append({
            "key": key,
            "display": info["display"],
            "directory": info["dir"],
            "available": exists,
            "reference_count": len(info.get("references", [])),
        })
    return result
