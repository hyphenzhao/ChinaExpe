"""Chart API routes - read, list, save, and AI-import chart data."""
import json
from pathlib import Path
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..services.chart_service import (
    list_people, get_person_meta, get_ziwei_grid,
    get_shishen_data, save_chart, validate_chart_json,
    delete_person, delete_chart, update_person_meta,
)
from ..services.chart_import_service import import_chart_from_text

router = APIRouter(prefix="/api/charts", tags=["charts"])


class SaveChartRequest(BaseModel):
    chart_type: str
    json_content: str


class ValidateChartRequest(BaseModel):
    chart_type: str
    json_content: str


class ImportChartRequest(BaseModel):
    """AI import: user provides raw chart text, AI extracts structured JSON."""
    person: str           # person identifier
    display_name: str     # full name
    chart_type: str       # 'ziwei' or 'shishen'
    raw_text: str         # raw chart description text


@router.get("")
async def charts_list():
    return list_people()


@router.get("/{person}")
async def person_meta(person: str):
    meta = get_person_meta(person)
    if not meta:
        raise HTTPException(status_code=404, detail="人物未找到")
    return meta


@router.get("/{person}/ziwei")
async def person_ziwei(person: str):
    data = get_ziwei_grid(person)
    if not data:
        raise HTTPException(status_code=404, detail=f"{person} 的紫微斗数命盘未找到")
    return data


@router.get("/{person}/shishen")
async def person_shishen(person: str):
    data = get_shishen_data(person)
    if not data:
        raise HTTPException(status_code=404, detail=f"{person} 的十神命盘未找到")
    return data


@router.put("/{person}/ziwei")
async def save_ziwei(person: str, req: SaveChartRequest):
    if req.chart_type != "ziwei":
        raise HTTPException(status_code=400, detail="chart_type 必须是 'ziwei'")
    success, message = save_chart(person, "ziwei", req.json_content)
    if not success:
        raise HTTPException(status_code=400, detail=message)
    return {"success": True, "message": message}


@router.put("/{person}/shishen")
async def save_shishen(person: str, req: SaveChartRequest):
    if req.chart_type != "shishen":
        raise HTTPException(status_code=400, detail="chart_type 必须是 'shishen'")
    success, message = save_chart(person, "shishen", req.json_content)
    if not success:
        raise HTTPException(status_code=400, detail=message)
    return {"success": True, "message": message}


@router.post("/validate")
async def validate_chart(req: ValidateChartRequest):
    valid, message, data = validate_chart_json(req.json_content, req.chart_type)
    return {"valid": valid, "message": message, "has_data": data is not None}


@router.post("/import")
async def import_chart(req: ImportChartRequest):
    """AI-powered chart import: auto-detect type and parse raw text into structured JSON."""
    if req.chart_type not in ("ziwei", "shishen", "auto"):
        raise HTTPException(status_code=400, detail="chart_type 必须是 'ziwei'、'shishen' 或 'auto'")

    # Load config for LLM settings
    config_path = Path(__file__).resolve().parent.parent.parent / "data" / "config.json"
    config = {}
    if config_path.exists():
        try:
            config = json.loads(config_path.read_text(encoding="utf-8"))
        except Exception:
            pass

    # Step 1: Auto-detect chart type if needed
    detected_type = req.chart_type
    if req.chart_type == "auto":
        detected_type = await _detect_chart_type(req.raw_text, config)
        if not detected_type:
            raise HTTPException(status_code=400, detail="无法自动识别命盘类型，请确认内容是否为紫微斗数或八字十神命盘")

    # Step 2: Import with detected type
    result = await import_chart_from_text(
        person=req.person,
        display_name=req.display_name,
        chart_type=detected_type,
        raw_text=req.raw_text,
        config=config,
    )

    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])

    # Step 3: Save both chart types (ziwei always generates shishen placeholder, and vice versa)
    json_content = result["json_content"]
    success, message = save_chart(req.person, detected_type, json_content, raw_text=req.raw_text)
    if not success:
        raise HTTPException(status_code=400, detail=message)

    return {
        "success": True,
        "message": message,
        "chart_type": detected_type,
        "extracted_summary": result.get("summary", ""),
    }


async def _detect_chart_type(raw_text: str, config: dict) -> str:
    """Use a quick LLM call to detect whether the raw text is Ziwei or Bazi."""
    model = config.get("default_model", "")
    if not model:
        return ""

    provider = config.get("provider", "ollama")
    ollama_host = config.get("ollama_host", "http://127.0.0.1")
    ollama_port = config.get("ollama_port", 11434)
    deepseek_key = config.get("deepseek_api_key", "")
    deepseek_url = config.get("deepseek_base_url", "https://api.deepseek.com")

    prompt = f"""请判断以下命盘文本属于哪种类型。只回答一个词："ziwei"（紫微斗数）或 "shishen"（八字十神/子平命理）。

判断依据：紫微斗数包含12宫（命宫/父母宫/福德宫等）、星曜（紫微/天府/天机等）、四化（禄权科忌）；八字十神包含四柱（年柱/月柱/日柱/时柱）、天干地支、十神（正官/七杀/正印等）。

命盘内容：
{raw_text[:2000]}"""

    messages = [{"role": "user", "content": prompt}]

    try:
        import httpx
        if provider == "ollama":
            url = f"{ollama_host.rstrip('/')}:{ollama_port}/api/chat"
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(url, json={"model": model, "messages": messages, "stream": False})
                if resp.status_code == 200:
                    answer = resp.json().get("message", {}).get("content", "").strip().lower()
                    if "ziwei" in answer: return "ziwei"
                    if "shishen" in answer or "bazi" in answer or "八字" in answer: return "shishen"
        else:
            url = f"{deepseek_url.rstrip('/')}/v1/chat/completions"
            headers = {"Authorization": f"Bearer {deepseek_key}", "Content-Type": "application/json"}
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(url, json={"model": model, "messages": messages, "stream": False}, headers=headers)
                if resp.status_code == 200:
                    answer = resp.json().get("choices", [{}])[0].get("message", {}).get("content", "").strip().lower()
                    if "ziwei" in answer: return "ziwei"
                    if "shishen" in answer or "bazi" in answer or "八字" in answer: return "shishen"
    except Exception:
        pass

    # Fallback: keyword matching
    ziwei_keywords = ["命宫", "父母宫", "福德宫", "田宅宫", "官禄宫", "紫微", "天府", "天机", "四化", "文墨天机", "身宫"]
    shishen_keywords = ["十神", "正官", "七杀", "正印", "偏印", "正财", "偏财", "食神", "伤官", "比肩", "劫财", "日主", "藏干", "纳音", "子平"]

    ziwei_score = sum(1 for kw in ziwei_keywords if kw in raw_text)
    shishen_score = sum(1 for kw in shishen_keywords if kw in raw_text)

    if ziwei_score > shishen_score:
        return "ziwei"
    elif shishen_score > ziwei_score:
        return "shishen"

    return ""


class UpdateMetaRequest(BaseModel):
    display_name: str


@router.delete("/{person}")
async def delete_person_endpoint(person: str):
    """Delete a person and all their charts."""
    success, message = delete_person(person)
    if not success:
        raise HTTPException(status_code=404, detail=message)
    return {"success": True, "message": message}


@router.delete("/{person}/{chart_type}")
async def delete_chart_endpoint(person: str, chart_type: str):
    """Delete a single chart type for a person."""
    if chart_type not in ("ziwei", "shishen"):
        raise HTTPException(status_code=400, detail="chart_type 必须是 'ziwei' 或 'shishen'")
    success, message = delete_chart(person, chart_type)
    if not success:
        raise HTTPException(status_code=404, detail=message)
    return {"success": True, "message": message}


@router.put("/{person}/meta")
async def update_meta_endpoint(person: str, req: UpdateMetaRequest):
    """Update display name for a person."""
    success, message = update_person_meta(person, req.display_name)
    if not success:
        raise HTTPException(status_code=404, detail=message)
    return {"success": True, "message": message}
