"""AI-powered chart import service.

Takes raw chart text (e.g. from 文墨天机 export) and uses the LLM to
extract structured JSON matching the SCHEMA.json specification.
If one chart type already exists for the person, existing data is used
as context. Skills and LanceDB knowledge are injected to help the AI
derive missing information.
"""
import json
import re
from pathlib import Path
from typing import Optional

import httpx

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
SCHEMA_PATH = PROJECT_ROOT / "data" / "charts" / "SCHEMA.json"
EXAMPLES_PATH = PROJECT_ROOT / "data" / "charts"
SKILLS_PATH = PROJECT_ROOT / "skills"

_schema_text = ""
if SCHEMA_PATH.exists():
    _schema_text = SCHEMA_PATH.read_text(encoding="utf-8")


def _load_example(chart_type: str, person: str = "zhf") -> str:
    """Load an example chart JSON for few-shot prompting."""
    filename = "ziwei.json" if chart_type == "ziwei" else "shishen.json"
    path = EXAMPLES_PATH / person / filename
    if path.exists():
        return path.read_text(encoding="utf-8")
    return ""


def _load_skill_reference(skill_dir: str, ref_name: str) -> str:
    """Load a skill reference file, truncated for prompt size."""
    path = SKILLS_PATH / skill_dir / ref_name
    if path.exists():
        content = path.read_text(encoding="utf-8")
        return content[:1500]
    return ""


def _load_existing_chart(person: str, chart_type: str) -> Optional[str]:
    """Load the complementary chart type if it exists."""
    other = "shishen" if chart_type == "ziwei" else "ziwei"
    path = EXAMPLES_PATH / person / f"{other}.json"
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
        # Extract key info: four pillars, basic info — the parts that help derive
        summary = {
            "basic_info": data.get("basic_info", {}),
        }
        if "four_pillars" in data:
            summary["four_pillars"] = data["four_pillars"]
        return json.dumps(summary, ensure_ascii=False, indent=2)
    return None


async def _load_rag_context(raw_text: str, chart_type: str) -> str:
    """Query LanceDB for relevant knowledge to help with import."""
    try:
        from .knowledge_service import knowledge_service
        if knowledge_service.is_available():
            query = f"{'紫微斗数' if chart_type == 'ziwei' else '八字十神'} 排盘 安星 {' '.join(raw_text[:200].split()[:20])}"
            results = await knowledge_service.query(query, limit=3)
            if results:
                return knowledge_service.format_rag_context(results)
    except Exception:
        pass
    return ""


def _build_import_prompt(
    chart_type: str, display_name: str, person: str, raw_text: str,
    existing_chart: Optional[str] = None, rag_context: str = "",
) -> str:
    """Build the system prompt for AI chart import — lean to avoid context overflow."""
    example_json = _load_example(chart_type, "zhf")

    if chart_type == "ziwei":
        type_label = "紫微斗数"
        type_const = "ziwei_chart"
        format_hint = """提取规则：
1. basic_info: software, display_name, gender(阴男/阴女/阳男/阳女), bureau, true_solar_time, clock_time, lunar, ming_zhu, shen_zhu, zi_dou
2. four_pillars: jieqi[年,月,日,时] + non_jieqi[年,月,日,时]; transformations: [{star,transform,palace}]
3. palaces 固定12宫顺序，每宫: name/stem_branch/changsheng/major_limit/stars[{name,brightness,transform}]/liunian/xiaoxian/markers
4. brightness: 庙/旺/得/利/平/不/陷; transform: 禄/权/科/忌"""
    else:
        type_label = "十神·子平命理"
        type_const = "bazi_shishen"
        format_hint = """提取规则：
1. basic_info: jieqi_birth_note, four_pillars[年,月,日,时], day_master, gan_shen
2. heavenly_stems(4): pillar/stem/shishen; earthly_branches(4): pillar/branch
3. hidden_stems(4): pillar/stems[]; branch_shishen(4): pillar/shishen[]
4. summary: visible_shishen[], hidden_shishen[]
5. 如文本只含四柱，请推导十神/藏干/纳音；不全则留空"" """

    prompt = f"""你是一位专业命盘数据专家。请根据{type_label}原文提取JSON。

## SCHEMA
{_schema_text[:1500]}

## 示例
{example_json[:800]}

## {format_hint}

## 规则
- name="{person}", display_name="{display_name}", type="{type_const}", verified=false
- 按技能知识推导补全，无法推导的留空""，不编造
- 只输出纯JSON，不要任何解释

## 原文
{raw_text[:5000]}"""

    return prompt


async def import_chart_from_text(
    person: str,
    display_name: str,
    chart_type: str,
    raw_text: str,
    config: dict,
) -> dict:
    """Use the LLM to parse raw chart text into structured JSON.

    Returns:
        {"success": bool, "message": str, "json_content": str, "summary": str}
    """
    provider = config.get("provider", "ollama")
    model = config.get("default_model", "")
    ollama_host = config.get("ollama_host", "http://127.0.0.1")
    ollama_port = config.get("ollama_port", 11434)
    deepseek_key = config.get("deepseek_api_key", "")
    deepseek_url = config.get("deepseek_base_url", "https://api.deepseek.com")

    if not model:
        return {"success": False, "message": "请先在配置页面设置默认模型", "json_content": "", "summary": ""}

    # Load complementary data for better inference
    existing_chart = _load_existing_chart(person, chart_type)
    rag_context = await _load_rag_context(raw_text, chart_type)

    system_prompt = _build_import_prompt(
        chart_type, display_name, person, raw_text,
        existing_chart=existing_chart, rag_context=rag_context,
    )
    messages = [
        {"role": "system", "content": "你是一个专业的命盘数据格式化助手。你只输出纯JSON，不输出任何其他内容。"},
        {"role": "user", "content": system_prompt},
    ]

    full_response = ""
    try:
        if provider == "ollama":
            url = f"{ollama_host.rstrip('/')}:{ollama_port}/api/chat"
            payload = {"model": model, "messages": messages, "stream": False}
            async with httpx.AsyncClient(timeout=120.0) as client:
                resp = await client.post(url, json=payload)
                if resp.status_code == 200:
                    try:
                        data = resp.json()
                    except Exception:
                        body = await resp.aread()
                        return {"success": False, "message": f"Ollama 返回了非JSON响应: {body.decode()[:200]}", "json_content": "", "summary": ""}
                    full_response = data.get("message", {}).get("content", "")
                    if not full_response:
                        return {"success": False, "message": "Ollama 返回了空响应，请检查模型是否正常运行", "json_content": "", "summary": ""}
                else:
                    body = await resp.aread()
                    return {"success": False, "message": f"Ollama API 错误 {resp.status_code}: {body.decode()[:200]}", "json_content": "", "summary": ""}
        else:
            url = f"{deepseek_url.rstrip('/')}/v1/chat/completions"
            headers = {"Authorization": f"Bearer {deepseek_key}", "Content-Type": "application/json"}
            payload = {"model": model, "messages": messages, "stream": False}
            async with httpx.AsyncClient(timeout=120.0) as client:
                resp = await client.post(url, json=payload, headers=headers)
                if resp.status_code == 200:
                    try:
                        data = resp.json()
                    except Exception:
                        body = await resp.aread()
                        return {"success": False, "message": f"DeepSeek 返回了非JSON响应: {body.decode()[:200]}", "json_content": "", "summary": ""}
                    full_response = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                    if not full_response:
                        return {"success": False, "message": "DeepSeek 返回了空响应，请检查模型名称和API密钥", "json_content": "", "summary": ""}
                else:
                    body = await resp.aread()
                    return {"success": False, "message": f"DeepSeek API 错误 {resp.status_code}: {body.decode()[:200]}", "json_content": "", "summary": ""}
    except Exception as e:
        return {"success": False, "message": f"AI 请求失败: {str(e)}", "json_content": "", "summary": ""}

    # Sanity check: if response looks like an error page
    if full_response.startswith("Internal Server Error") or full_response.startswith("<!DOCTYPE") or full_response.startswith("<html"):
        return {"success": False, "message": f"AI 返回了错误页面而非命盘数据，请检查API配置", "json_content": "", "summary": ""}

    # Extract JSON from response (may be wrapped in markdown code blocks)
    json_str = _extract_json(full_response)
    if not json_str:
        return {"success": False, "message": "AI 返回的内容中未找到有效JSON，请重试或检查模型是否正常", "json_content": "", "summary": ""}

    # Validate the extracted JSON
    try:
        parsed = json.loads(json_str)
    except json.JSONDecodeError as e:
        return {"success": False, "message": f"AI 生成的JSON格式无效: {e}", "json_content": "", "summary": ""}

    # Basic validation
    if parsed.get("type") != (f"{chart_type}_chart" if chart_type == "ziwei" else "bazi_shishen"):
        return {"success": False, "message": "AI 生成的JSON type字段不正确", "json_content": "", "summary": ""}

    # Ensure name matches
    parsed["name"] = person
    if "basic_info" in parsed:
        parsed["basic_info"]["display_name"] = display_name

    final_json = json.dumps(parsed, ensure_ascii=False, indent=2)

    # Build summary
    summary = ""
    if chart_type == "ziwei":
        palaces = parsed.get("palaces", [])
        ming_palace = next((p for p in palaces if p.get("name") == "命宫"), None)
        if ming_palace:
            stars = [s.get("name", "") for s in ming_palace.get("stars", [])[:3]]
            summary = f"命宫{ming_palace.get('stem_branch','')}: {', '.join(stars)}"
    else:
        day_master = parsed.get("basic_info", {}).get("day_master", "")
        summary = f"日主: {day_master}"

    return {
        "success": True,
        "message": "命盘导入成功",
        "json_content": final_json,
        "summary": summary,
    }


def _extract_json(text: str) -> Optional[str]:
    """Extract JSON from LLM response, handling markdown code blocks."""
    # Try to find JSON in markdown code block
    md_match = re.search(r'```(?:json)?\s*\n(.*?)\n```', text, re.DOTALL)
    if md_match:
        return md_match.group(1).strip()

    # Try to find JSON between { and } (greedy)
    start = text.find('{')
    end = text.rfind('}')
    if start >= 0 and end > start:
        return text[start:end + 1]

    return None
