"""FastAPI main entry point for the Metaphysics Assistant (玄学助手)."""
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from .api.config_api import router as config_router
from .api.chat_api import router as chat_router
from .api.charts_api import router as charts_router
from .api.knowledge_api import router as knowledge_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan - ensure data directories exist."""
    data_dir = Path("/Volumes/Storage/Workspace/ChinaExpe/data")
    sessions_dir = data_dir / "sessions"
    data_dir.mkdir(parents=True, exist_ok=True)
    sessions_dir.mkdir(parents=True, exist_ok=True)
    yield


app = FastAPI(
    title="玄学助手",
    description="互动式玄学助手 — 紫微斗数 & 十神·子平命理解盘",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static files - mount specific directories
static_dir = Path(__file__).parent / "static"
static_dir.mkdir(parents=True, exist_ok=True)

for sub in ["css", "js", "img"]:
    sub_dir = static_dir / sub
    sub_dir.mkdir(parents=True, exist_ok=True)
    app.mount(f"/{sub}", StaticFiles(directory=str(sub_dir)), name=f"static_{sub}")


@app.get("/api/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok", "version": "1.0.0"}


# API routes
app.include_router(config_router)
app.include_router(chat_router)
app.include_router(charts_router)
app.include_router(knowledge_router)


# SPA catch-all: serve index.html for all non-API, non-static routes
@app.get("/{full_path:path}")
async def serve_spa(full_path: str):
    """Serve the SPA entry point for all frontend routes."""
    index_path = static_dir / "index.html"
    if full_path.startswith("api/"):
        return {"detail": "Not Found"}, 404
    return FileResponse(str(index_path))


@app.get("/")
async def root():
    """Serve the main page."""
    return FileResponse(str(static_dir / "index.html"))
