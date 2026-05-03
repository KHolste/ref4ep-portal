"""FastAPI-Application-Factory.

Sprint-1-Umfang:
- Settings, Engine, Jinja2-Templates,
- Routen ``/api/health``, Public-Pages, Auth-API, Stammdaten-API,
  Auth-Web (Login-Form),
- statischer Mount ``/static`` (Public-Assets),
- Catch-All-Handler ``/portal/{path}`` (SPA-Shell-Fallback,
  echte Dateien werden bevorzugt ausgeliefert).
"""

from __future__ import annotations

import logging
from importlib import resources
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import create_engine

from ref4ep import __version__
from ref4ep.api.config import Settings, get_settings
from ref4ep.api.routes.admin_partners import router as admin_partners_router
from ref4ep.api.routes.admin_persons import router as admin_persons_router
from ref4ep.api.routes.audit import router as audit_router
from ref4ep.api.routes.auth_api import router as auth_api_router
from ref4ep.api.routes.auth_pages import router as auth_pages_router
from ref4ep.api.routes.documents import router as documents_router
from ref4ep.api.routes.health import router as health_router
from ref4ep.api.routes.partners import router as partners_router
from ref4ep.api.routes.public_documents import router as public_documents_router
from ref4ep.api.routes.public_pages import router as public_pages_router
from ref4ep.api.routes.stammdaten import router as stammdaten_router
from ref4ep.storage.local import LocalFileStorage


def _resource_dir(name: str) -> Path:
    package_root = resources.files("ref4ep")
    return Path(str(package_root / name))


def _configure_logging(settings: Settings) -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


def _register_portal_spa(app: FastAPI, web_dir: Path) -> None:
    """Bedient /portal/{path}: existierende Asset-Datei oder index.html."""
    web_resolved = web_dir.resolve()
    index_path = web_resolved / "index.html"

    @app.get("/portal", include_in_schema=False)
    @app.get("/portal/", include_in_schema=False)
    def portal_root() -> FileResponse:
        return FileResponse(index_path, media_type="text/html")

    @app.get("/portal/{full_path:path}", include_in_schema=False)
    def portal_spa(full_path: str) -> FileResponse:
        # Asset oder Fallback-SPA-Shell.
        candidate = (web_resolved / full_path).resolve()
        try:
            candidate.relative_to(web_resolved)
        except ValueError as exc:
            raise HTTPException(status_code=404) from exc
        if candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(index_path, media_type="text/html")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    _configure_logging(settings)

    app = FastAPI(title="Ref4EP-Portal", version=__version__)

    engine = create_engine(settings.database_url, future=True)
    app.state.engine = engine
    app.state.settings = settings
    app.state.version = __version__
    app.state.storage = LocalFileStorage(settings.storage_dir)

    templates_dir = _resource_dir("templates")
    app.state.templates = Jinja2Templates(directory=str(templates_dir))

    # API
    app.include_router(health_router)
    app.include_router(auth_api_router)
    app.include_router(stammdaten_router)
    app.include_router(partners_router)
    app.include_router(documents_router)
    app.include_router(audit_router)
    app.include_router(admin_persons_router)
    app.include_router(admin_partners_router)
    app.include_router(public_documents_router)
    # Web (server-rendered)
    app.include_router(public_pages_router)
    app.include_router(auth_pages_router)

    # Statische Public-Assets
    static_dir = _resource_dir("static")
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    # SPA-Zone /portal — Catch-All mit Fallback auf index.html
    web_dir = _resource_dir("web")
    _register_portal_spa(app, web_dir)

    return app


app = create_app()
