"""ASGI-Entrypoint für Production-Server (uvicorn/gunicorn).

Trennt das Modul-Import vom App-Bau: ``ref4ep.api.app`` ist eine reine
Factory; erst durch das Importieren *dieses* Moduls wird über
``create_app()`` eine FastAPI-Instanz instanziiert. Damit erzeugt das
Importieren von ``ref4ep.api.app`` keine Engine mehr und keine
Implicit-Connection auf eine Default-DB-URL — ein häufiger
Stolperstein bei Tests, CLI und ad-hoc Imports.

Aufruf:
    uvicorn ref4ep.api.asgi:app
"""

from __future__ import annotations

from ref4ep.api.app import create_app

app = create_app()
