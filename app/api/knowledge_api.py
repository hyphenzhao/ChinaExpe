"""Knowledge API - hybrid search, literature import, index/vector builds."""
from fastapi import APIRouter
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel

from ..services.knowledge_service import knowledge_service
from ..services.local_knowledge import local_knowledge
from ..services.literature_importer import import_literature, literature_stats

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])


class KnowledgeQuery(BaseModel):
    query: str
    limit: int = 5
    scope: str = "all"


@router.post("/query")
async def query_knowledge(req: KnowledgeQuery):
    local, keywords = ([], [])
    if local_knowledge.is_available():
        local, keywords = local_knowledge.search(req.query, limit=req.limit, scope=req.scope)
    vector = await knowledge_service.query(req.query, limit=req.limit, scope=req.scope) if knowledge_service.is_available() else []
    return {"keywords": keywords, "local": local, "vector": vector}


@router.get("/status")
async def knowledge_status():
    return {
        "lancedb_available": knowledge_service.is_available(),
        "lancedb": knowledge_service.status(),
        "local_available": local_knowledge.is_available(),
        "index_exists": local_knowledge.index_exists(),
        "index_info": local_knowledge.index_info(),
        "literature": literature_stats(),
    }


@router.post("/build-index")
async def build_index():
    return await run_in_threadpool(local_knowledge.build_index)


@router.post("/import-literature")
async def import_lit():
    result = await run_in_threadpool(import_literature)
    if result.get("success"):
        idx = await run_in_threadpool(local_knowledge.build_index)
        result["message"] += "；" + idx.get("message", "")
    return result


@router.post("/build-vectors")
async def build_vectors():
    return await knowledge_service.build_literature_vectors()


@router.get("/index-info")
async def get_index_info():
    return local_knowledge.index_info()
