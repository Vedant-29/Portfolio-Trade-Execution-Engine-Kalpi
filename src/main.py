from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from src.adapters import load_all_adapters
from src.api.auth_routes import router as auth_router
from src.api.meta_routes import router as meta_router
from src.api.portfolio_routes import router as portfolio_router
from src.config import get_settings
from src.utils.logging import configure_logging, get_logger

_FRONTEND_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"

def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(
        title="Kalpi Builder Execution Engine",
        description="Portfolio Trade Execution Engine for Indian brokers.",
        version="0.1.0",
    )

    brokers_registered = load_all_adapters()

    app.include_router(meta_router)
    app.include_router(auth_router)
    app.include_router(portfolio_router)

    _mount_frontend(app)

    logger = get_logger(__name__)
    logger.info(
        "app_started",
        app_env=settings.app_env,
        brokers_configured=settings.configured_brokers(),
        brokers_registered=brokers_registered,
        frontend_bundled=_FRONTEND_DIST.is_dir(),
    )

    return app

def _mount_frontend(app: FastAPI) -> None:
    """Serve the built React app at / (Docker production mode).

    - /assets/*  → static JS/CSS via StaticFiles
    - anything else non-API  → index.html (SPA fallback so client-side
      routing and OAuth return URLs like /?broker=zerodha&session_id=...
      work without 404)

    If the dist/ directory is missing (dev mode — using `make dev-all`
    with Vite on :5173), we skip this entirely. The API routes keep
    working either way.
    """
    if not _FRONTEND_DIST.is_dir():
        return

    assets_dir = _FRONTEND_DIST / "assets"
    if assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    index_html = _FRONTEND_DIST / "index.html"

    _API_PREFIXES = ("auth/", "portfolio/", "holdings", "brokers", "events", "health")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str, request: Request) -> FileResponse:
        path = full_path.lstrip("/")
        if any(path.startswith(p) for p in _API_PREFIXES):
            raise HTTPException(status_code=404, detail="Not Found")

        candidate = _FRONTEND_DIST / path
        if path and candidate.is_file():
            return FileResponse(candidate)

        return FileResponse(index_html)

app = create_app()
