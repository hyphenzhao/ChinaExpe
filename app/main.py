"""FastAPI main entry point for the Metaphysics Assistant (玄学助手)."""
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from .version import VERSION

from .api.config_api import router as config_router
from .api.chat_api import router as chat_router
from .api.people_api import router as people_router
from .api.knowledge_api import router as knowledge_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan - ensure data directories exist."""
    data_dir = Path(__file__).resolve().parent.parent / "data"
    sessions_dir = data_dir / "sessions"
    people_dir = data_dir / "people"
    data_dir.mkdir(parents=True, exist_ok=True)
    sessions_dir.mkdir(parents=True, exist_ok=True)
    people_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "exports").mkdir(parents=True, exist_ok=True)
    try:
        # refresh the AI-readable chart bundles so 运限 matches today's date
        from .services import export_service
        export_service.write_all()
    except Exception:
        pass
    try:
        # bring up the 跳板 tunnel if the user left it enabled
        from .services import config_store, proxy_service
        proxy_service.ensure(config_store.load())
    except Exception:
        pass
    yield
    try:
        from .services import config_store, proxy_service
        proxy_service.stop(config_store.load())
    except Exception:
        pass


app = FastAPI(
    title="玄学助手",
    description="互动式玄学助手 — 紫微斗数 & 十神·子平命理解盘",
    version=VERSION,
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
    return {"status": "ok", "version": VERSION}


# API routes
app.include_router(config_router)
app.include_router(chat_router)
app.include_router(people_router)
app.include_router(knowledge_router)


def _index_page():
    """index.html with the version stamp injected (cache busting for js/css)."""
    from fastapi.responses import HTMLResponse
    page = (static_dir / "index.html").read_text(encoding="utf-8").replace("__V__", VERSION)
    return HTMLResponse(page, headers={"Cache-Control": "no-cache"})


@app.get("/v2")
async def serve_v2():
    return _index_page()


@app.get("/manifest.webmanifest")
async def manifest():
    return FileResponse(str(static_dir / "manifest.webmanifest"), media_type="application/manifest+json")


# SPA catch-all: serve index.html for all non-API, non-static routes
@app.get("/{full_path:path}")
async def serve_spa(full_path: str):
    """Serve the SPA entry point for all frontend routes."""
    if full_path.startswith("api/"):
        from fastapi.responses import JSONResponse
        return JSONResponse({"detail": "Not Found"}, status_code=404)
    return _index_page()


@app.get("/")
async def root():
    return _index_page()
