"""Knowledge API routes - RAG queries and index management."""
from fastapi import APIRouter
from pydantic import BaseModel

from ..services.knowledge_service import knowledge_service
from ..services.local_knowledge import local_knowledge

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
    return {
        "lancedb_available": knowledge_service.is_available(),
        "local_available": local_knowledge.is_available(),
        "index_exists": local_knowledge.index_exists(),
        "index_info": local_knowledge.index_info(),
    }


@router.post("/build-index")
async def build_index():
    """Rebuild the local knowledge base search index."""
    result = local_knowledge.build_index()
    return result


@router.get("/index-info")
async def get_index_info():
    """Get info about the current local knowledge index."""
    return local_knowledge.index_info()
