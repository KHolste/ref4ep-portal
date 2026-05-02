"""FastAPI-Application-Factory.

Sprint-0-Umfang:
- Settings laden,
- SQLAlchemy-Engine anlegen und auf ``app.state`` ablegen,
- Jinja2-Templates für die Public-Zone bereitstellen,
- Routen ``/api/health`` und Public-Pages registrieren,
- statische Mounts ``/static`` und ``/portal`` einhängen.

Auth, Middleware und CORS sind Sprint 1 zugeordnet.
"""

from __future__ import annotations

import logging
from importlib import resources
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import create_engine

from ref4ep import __version__
from ref4ep.api.config import Settings, get_settings
from ref4ep.api.routes.health import router as health_router
from ref4ep.api.routes.public_pages import router as public_pages_router


def _resource_dir(name: str) -> Path:
    package_root = resources.files("ref4ep")
    return Path(str(package_root / name))


def _configure_logging(settings: Settings) -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    _configure_logging(settings)

    app = FastAPI(title="Ref4EP-Portal", version=__version__)

    engine = create_engine(settings.database_url, future=True)
    app.state.engine = engine
    app.state.settings = settings
    app.state.version = __version__

    templates_dir = _resource_dir("templates")
    app.state.templates = Jinja2Templates(directory=str(templates_dir))

    app.include_router(health_router)
    app.include_router(public_pages_router)

    static_dir = _resource_dir("static")
    web_dir = _resource_dir("web")
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
    app.mount(
        "/portal",
        StaticFiles(directory=str(web_dir), html=True),
        name="portal-shell",
    )

    return app


app = create_app()
