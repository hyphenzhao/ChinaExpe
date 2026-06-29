"""Chart service - parse, validate, and transform chart data for frontend."""
import json
from pathlib import Path
from typing import Optional

CHART_BASE = Path(__file__).resolve().parent.parent.parent / "data" / "charts"

# Standard Ziwei Doushu grid layout:
# The 12 earthly branches have fixed positions in a 4x4 grid.
# Map: branch -> (row, col)
# Layout:
#   巳(3)  午(4)  未(5)  申(6)    row 0
#   辰(2)  [空]   [空]  酉(7)    row 1
#   卯(1)  [空]   [空]  戌(8)    row 2
#   寅(0)  丑(11) 子(10) 亥(9)   row 3

BRANCH_GRID = {
    "巳": (0, 0), "午": (0, 1), "未": (0, 2), "申": (0, 3),
    "辰": (1, 0),                        "酉": (1, 3),
    "卯": (2, 0),                        "戌": (2, 3),
    "寅": (3, 0), "丑": (3, 1), "子": (3, 2), "亥": (3, 3),
}

# Standard palace order (matches the schema)
PALACE_ORDER = [
    "命宫", "父母宫", "福德宫", "田宅宫",
    "官禄宫", "交友宫", "迁移宫", "疾厄宫",
    "财帛宫", "子女宫", "夫妻宫", "兄弟宫",
]

# Empty positions in the 4x4 grid
EMPTY_POSITIONS = {(1, 1), (1, 2), (2, 1), (2, 2)}


def _get_grid_position(stem_branch: str) -> tuple[int, int]:
    """Get (row, col) grid position from a stem-branch string like '癸未'."""
    branch = stem_branch[-1]  # Last character is the earthly branch
    return BRANCH_GRID.get(branch, (0, 0))


def list_people() -> list[dict]:
    """List all people with charts in the 命盘 directory."""
    if not CHART_BASE.exists():
        return []

    people = []
    for folder in sorted(CHART_BASE.iterdir()):
        if not folder.is_dir():
            continue
        name = folder.name
        ziwei_json = folder / "ziwei.json"
        shishen_json = folder / "shishen.json"
        has_ziwei = ziwei_json.exists()
        has_shishen = shishen_json.exists()

        display_name = name
        if has_ziwei:
            try:
                data = json.loads(ziwei_json.read_text(encoding="utf-8"))
                display_name = data.get("basic_info", {}).get("display_name", name)
            except Exception:
                pass

        people.append({
            "name": name,
            "has_ziwei": has_ziwei,
            "has_shishen": has_shishen,
            "display_name": display_name,
        })

    return people


def get_person_meta(person: str) -> Optional[dict]:
    """Get metadata about a person's available charts."""
    folder = CHART_BASE / person
    if not folder.is_dir():
        return None

    ziwei_json = folder / "ziwei.json"
    shishen_json = folder / "shishen.json"

    return {
        "name": person,
        "has_ziwei": ziwei_json.exists(),
        "has_shishen": shishen_json.exists(),
        "ziwei_txt": (folder / "ziwei.txt").exists(),
        "shishen_txt": (folder / "shishen.txt").exists(),
    }


def get_ziwei_grid(person: str) -> Optional[dict]:
    """Read ziwei.json and transform into frontend-friendly grid data."""
    filepath = CHART_BASE / person / "ziwei.json"
    if not filepath.exists():
        return None

    data = json.loads(filepath.read_text(encoding="utf-8"))

    # Build palace grid
    palaces = []
    # Create a placeholder grid first
    grid = {}
    for row in range(4):
        for col in range(4):
            pos = (row, col)
            if pos in EMPTY_POSITIONS:
                grid[pos] = {
                    "name": "",
                    "stem_branch": "",
                    "grid_row": row,
                    "grid_col": col,
                    "is_empty": True,
                    "stars": [],
                }
            else:
                grid[pos] = None  # to be filled

    # Fill in palaces from data
    raw_palaces = data.get("palaces", [])
    shen_gong = data.get("basic_info", {}).get("shen_gong", "")
    lai_yin_gong = ""

    # Handle transformations (could be dict with natal/self_transform keys)
    transforms = data.get("transformations", [])
    flat_transforms = []
    if isinstance(transforms, dict):
        for category, items in transforms.items():
            if isinstance(items, list):
                for item in items:
                    if isinstance(item, dict):
                        item = dict(item)
                        item["_category"] = category
                        flat_transforms.append(item)
    elif isinstance(transforms, list):
        flat_transforms = [t for t in transforms if isinstance(t, dict)]

    for palace in raw_palaces:
        sb = palace.get("stem_branch", "")
        pos = _get_grid_position(sb)

        stars = []
        for s in palace.get("stars", []):
            stars.append({
                "name": s.get("name", ""),
                "brightness": s.get("brightness"),
                "transform": s.get("transform"),
            })

        markers = palace.get("markers", []) or []
        shen_here = palace.get("shen_gong_here", False)
        lai_yin_here = palace.get("lai_yin_here", False)

        palace_data = {
            "name": palace.get("name", ""),
            "stem_branch": sb,
            "grid_row": pos[0],
            "grid_col": pos[1],
            "is_empty": False,
            "stars": stars,
            "changsheng": palace.get("changsheng"),
            "major_limit": palace.get("major_limit"),
            "markers": markers,
            "shen_gong_here": shen_here,
            "lai_yin_here": lai_yin_here,
        }
        grid[pos] = palace_data

    # Collect non-None grid cells in row-major order
    for row in range(4):
        for col in range(4):
            cell = grid.get((row, col))
            if cell is not None:
                palaces.append(cell)

    # Fix: add missing empty cells
    existing = {(p["grid_row"], p["grid_col"]) for p in palaces}
    for row in range(4):
        for col in range(4):
            if (row, col) not in existing and (row, col) not in EMPTY_POSITIONS:
                pass  # shouldn't happen if data is complete

    # Re-add empties
    for row in range(4):
        for col in range(4):
            if (row, col) in EMPTY_POSITIONS:
                if (row, col) not in {(p["grid_row"], p["grid_col"]) for p in palaces}:
                    palaces.append({
                        "name": "",
                        "stem_branch": "",
                        "grid_row": row,
                        "grid_col": col,
                        "is_empty": True,
                        "stars": [],
                    })

    result = {
        "person": person,
        "display_name": data.get("basic_info", {}).get("display_name", person),
        "gender": data.get("basic_info", {}).get("gender"),
        "bureau": data.get("basic_info", {}).get("bureau"),
        "ming_zhu": data.get("basic_info", {}).get("ming_zhu"),
        "shen_zhu": data.get("basic_info", {}).get("shen_zhu"),
        "four_pillars": data.get("four_pillars"),
        "shen_gong": shen_gong,
        "palaces": palaces,
        "transformations": flat_transforms,
        "major_limits": data.get("major_limits", []),
    }

    return result


def get_shishen_data(person: str) -> Optional[dict]:
    """Read shishen.json and transform into frontend-friendly data."""
    filepath = CHART_BASE / person / "shishen.json"
    if not filepath.exists():
        return None

    data = json.loads(filepath.read_text(encoding="utf-8"))

    # Build pillars
    pillars = []
    he_stems = data.get("heavenly_stems", [])
    ea_branches = data.get("earthly_branches", [])
    hi_stems = data.get("hidden_stems", [])
    br_shishen = data.get("branch_shishen", [])

    for i in range(4):
        hs = he_stems[i] if i < len(he_stems) else {}
        eb = ea_branches[i] if i < len(ea_branches) else {}
        hi = hi_stems[i] if i < len(hi_stems) else {}
        bs = br_shishen[i] if i < len(br_shishen) else {}

        # Hidden stems with their shishen
        hidden_list = []
        raw_stems = hi.get("stems", [])
        raw_shishen = bs.get("shishen", [])
        if isinstance(raw_stems, str):
            raw_stems = list(raw_stems)
        for j, stem in enumerate(raw_stems):
            shishen_val = raw_shishen[j] if j < len(raw_shishen) else None
            hidden_list.append({"stem": stem, "shishen": shishen_val})

        pillars.append({
            "pillar": hs.get("pillar", ["年柱", "月柱", "日柱", "时柱"][i]),
            "heavenly_stem": {
                "stem": hs.get("stem", ""),
                "shishen": hs.get("shishen"),
            },
            "earthly_branch": {
                "branch": eb.get("branch", ""),
            },
            "hidden_stems": hidden_list,
            "nayin": data.get("nayin", [None]*4)[i] if isinstance(data.get("nayin"), list) else None,
            "kongwang": data.get("kongwang", [None]*4)[i] if isinstance(data.get("kongwang"), list) else None,
            "dishi": data.get("dishi", [None]*4)[i] if isinstance(data.get("dishi"), list) else None,
        })

    result = {
        "person": person,
        "display_name": data.get("basic_info", {}).get("display_name", person),
        "day_master": data.get("basic_info", {}).get("day_master"),
        "pillars": pillars,
        "summary": data.get("summary"),
        "shensha": data.get("shensha"),
        "five_elements_status": data.get("five_elements_status"),
    }

    return result


def validate_chart_json(content: str, chart_type: str) -> tuple[bool, str, Optional[dict]]:
    """Validate chart JSON against the schema requirements.

    Args:
        content: Raw JSON string
        chart_type: 'ziwei' or 'shishen'

    Returns:
        (valid, error_message, parsed_data)
    """
    try:
        data = json.loads(content)
    except json.JSONDecodeError as e:
        return False, f"JSON 格式错误: {e}", None

    if chart_type == "ziwei":
        if data.get("type") != "ziwei_chart":
            return False, "type 字段必须是 'ziwei_chart'", None
        if "palaces" not in data:
            return False, "缺少 'palaces' 字段", None
        if len(data.get("palaces", [])) != 12:
            return False, f"palaces 必须有12个宫位，当前有 {len(data['palaces'])} 个", None
        required_fields = ["name", "type", "basic_info", "four_pillars", "palaces"]
        for field in required_fields:
            if field not in data:
                return False, f"缺少必要字段: {field}", None

    elif chart_type == "shishen":
        if data.get("type") != "bazi_shishen":
            return False, "type 字段必须是 'bazi_shishen'", None
        required_fields = [
            "name", "type", "basic_info", "heavenly_stems",
            "earthly_branches", "hidden_stems", "branch_shishen", "summary"
        ]
        for field in required_fields:
            if field not in data:
                return False, f"缺少必要字段: {field}", None
        for arr_name in ["heavenly_stems", "earthly_branches", "hidden_stems", "branch_shishen"]:
            if len(data.get(arr_name, [])) != 4:
                return False, f"{arr_name} 必须有4个元素", None

    return True, "", data


def save_chart(person: str, chart_type: str, json_content: str, raw_text: str = "") -> tuple[bool, str]:
    """Save a chart to the 命盘 directory following the schema rules.

    Args:
        person: Person identifier (folder name)
        chart_type: 'ziwei' or 'shishen'
        json_content: Validated JSON content string
        raw_text: Original import text to archive alongside the chart

    Returns:
        (success, message)
    """
    # Validate first
    valid, msg, data = validate_chart_json(json_content, chart_type)
    if not valid:
        return False, msg

    # Ensure data.name matches person
    data["name"] = person
    json_content = json.dumps(data, ensure_ascii=False, indent=2)

    folder = CHART_BASE / person
    folder.mkdir(parents=True, exist_ok=True)

    if chart_type == "ziwei":
        json_path = folder / "ziwei.json"
        txt_path = folder / "ziwei.txt"
    else:
        json_path = folder / "shishen.json"
        txt_path = folder / "shishen.txt"

    # Write JSON
    json_path.write_text(json_content, encoding="utf-8")

    # Generate and write TXT (human-readable)
    txt_content = _generate_txt(data, chart_type)
    txt_path.write_text(txt_content, encoding="utf-8")

    # Archive raw import text if provided
    if raw_text:
        raw_path = folder / f"{chart_type}_raw.txt"
        raw_path.write_text(raw_text, encoding="utf-8")

    return True, f"命盘已保存至 {folder}"


def _generate_txt(data: dict, chart_type: str) -> str:
    """Generate human-readable TXT from chart JSON."""
    lines = []
    info = data.get("basic_info", {})

    if chart_type == "ziwei":
        lines.append(f"紫微斗数命盘 - {data.get('name', '')}")
        if info.get("display_name"):
            lines.append(f"姓名: {info['display_name']}")
        lines.append(f"性别: {info.get('gender', '')}")
        lines.append(f"局数: {info.get('bureau', '')}")
        lines.append(f"命主: {info.get('ming_zhu', '')}  身主: {info.get('shen_zhu', '')}")
        lines.append("")

        # Four pillars
        pillars = data.get("four_pillars", {})
        for key in ["jieqi", "non_jieqi"]:
            arr = pillars.get(key, [])
            if arr:
                lines.append(f"{key}: {'  '.join(arr)}")
        lines.append("")

        # Palaces
        for p in data.get("palaces", []):
            stars_str = ", ".join(
                f"{s.get('name', '')}({s.get('brightness', '')})" +
                (f"[{s.get('transform', '')}]" if s.get("transform") else "")
                for s in p.get("stars", [])
            )
            lines.append(f"{p.get('name', '')} ({p.get('stem_branch', '')}): {stars_str}")

    else:
        lines.append(f"十神·子平命理 - {data.get('name', '')}")
        if info.get("display_name"):
            lines.append(f"姓名: {info['display_name']}")
        lines.append(f"日主: {info.get('day_master', '')}")
        lines.append("")

        # Four pillars
        for i, hs in enumerate(data.get("heavenly_stems", [])):
            pillar = hs.get("pillar", "")
            stem = hs.get("stem", "")
            shishen = hs.get("shishen", "")
            lines.append(f"{pillar}: {stem}({shishen})")

    return "\n".join(lines)


def delete_person(person: str) -> tuple[bool, str]:
    """Delete a person's entire folder and all chart files."""
    import shutil
    folder = CHART_BASE / person
    if not folder.is_dir():
        return False, f"人物 '{person}' 不存在"
    try:
        shutil.rmtree(folder)
        return True, f"已删除人物 '{person}' 及其所有命盘"
    except Exception as e:
        return False, f"删除失败: {e}"


def delete_chart(person: str, chart_type: str) -> tuple[bool, str]:
    """Delete a single chart type for a person."""
    folder = CHART_BASE / person
    if not folder.is_dir():
        return False, f"人物 '{person}' 不存在"
    json_file = folder / f"{chart_type}.json"
    txt_file = folder / f"{chart_type}.txt"
    deleted = []
    for f in [json_file, txt_file]:
        if f.exists():
            f.unlink()
            deleted.append(f.name)
    if not deleted:
        return False, f"'{person}' 没有 {chart_type} 命盘"
    return True, f"已删除 {', '.join(deleted)}"


def update_person_meta(person: str, display_name: str) -> tuple[bool, str]:
    """Update display name in a person's chart JSON files.
    If the person has no charts yet, just create the folder silently.
    """
    folder = CHART_BASE / person
    folder.mkdir(parents=True, exist_ok=True)
    updated = []
    for chart_type in ["ziwei", "shishen"]:
        json_file = folder / f"{chart_type}.json"
        if json_file.exists():
            data = json.loads(json_file.read_text(encoding="utf-8"))
            if "basic_info" not in data:
                data["basic_info"] = {}
            data["basic_info"]["display_name"] = display_name
            json_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            txt_content = _generate_txt(data, chart_type)
            (folder / f"{chart_type}.txt").write_text(txt_content, encoding="utf-8")
            updated.append(chart_type)
    if not updated:
        return True, f"已为 '{person}' 创建人物文件夹"
    return True, f"已更新 '{person}' 的显示名称为 '{display_name}'"
