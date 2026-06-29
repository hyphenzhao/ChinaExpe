"""Knowledge API routes - RAG queries."""
from fastapi import APIRouter
from pydantic import BaseModel

from ..services.knowledge_service import knowledge_service

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])


class KnowledgeQuery(BaseModel):
    query: str
    limit: int = 5
    chart_context: str = ""


class EmbedRequest(BaseModel):
    text: str


@router.post("/query")
async def query_knowledge(req: KnowledgeQuery):
    """Query the LanceDB knowledge base."""
    if not knowledge_service.is_available():
        return {"results": [], "available": False, "message": "知识库不可用"}
    results = await knowledge_service.query(
        req.query,
        limit=req.limit,
        chart_context=req.chart_context,
    )
    return {"results": results, "available": True}


@router.post("/embed")
async def embed_text(req: EmbedRequest):
    """Embed text using Ollama bge-m3."""
    vec = await knowledge_service.embed(req.text)
    if vec is None:
        return {"success": False, "message": "嵌入失败，请确认 Ollama 和 bge-m3 模型可用"}
    return {"success": True, "embedding_dim": len(vec)}


@router.get("/status")
async def knowledge_status():
    """Check knowledge base status."""
    return {"available": knowledge_service.is_available()}
