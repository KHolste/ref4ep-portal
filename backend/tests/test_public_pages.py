"""Öffentliche, serverseitig gerenderte Pages."""

from __future__ import annotations

from fastapi.testclient import TestClient

from ref4ep.api.app import create_app
from tests.conftest import make_test_settings


def test_home_redirects_to_project_site(client: TestClient) -> None:
    """Block 0055: ``/`` leitet auf die öffentliche Projektseite um,
    statt eine zweite Projektbeschreibung zu pflegen."""
    response = client.get("/", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "https://www.ref4ep.de"


def test_home_renders_fallback_when_project_site_is_unset(tmp_path) -> None:
    """Ohne konfigurierte Projektseite (lokale Entwicklung) erscheint die
    eingebaute Einstiegsseite — ohne Sprint-0-Platzhaltertext."""
    settings = make_test_settings(
        database_url=f"sqlite:///{tmp_path / 'fallback.db'}",
        storage_dir=str(tmp_path),
        project_site_url="",
    )
    with TestClient(create_app(settings=settings)) as client:
        response = client.get("/", follow_redirects=False)
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/html")
        assert "Ref4EP-Portal" in response.text
        assert "Zum Projektportal" in response.text
        # Der alte Platzhaltertext ist verschwunden.
        assert "Sprint-0-Platzhalter" not in response.text


def test_imprint_redirects_to_project_site_imprint(client: TestClient) -> None:
    """Block 0079: Das Impressum der Projektseite gilt auch fürs Portal."""
    response = client.get("/legal/imprint", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "https://www.ref4ep.de/impressum.html"


def test_imprint_renders_when_project_site_is_unset(tmp_path) -> None:
    settings = make_test_settings(
        database_url=f"sqlite:///{tmp_path / 'imprint.db'}",
        storage_dir=str(tmp_path),
        project_site_url="",
    )
    with TestClient(create_app(settings=settings)) as client:
        response = client.get("/legal/imprint", follow_redirects=False)
        assert response.status_code == 200
        assert "Impressum" in response.text


def test_privacy_redirects_to_project_site_portal_section(client: TestClient) -> None:
    """Block 0079: Die Datenschutzerklärung der Projektseite hat einen
    Abschnitt zum Portal; dorthin wird weitergeleitet."""
    response = client.get("/legal/privacy", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "https://www.ref4ep.de/datenschutz.html#projektportal"


def test_privacy_renders_when_project_site_is_unset(tmp_path) -> None:
    settings = make_test_settings(
        database_url=f"sqlite:///{tmp_path / 'privacy.db'}",
        storage_dir=str(tmp_path),
        project_site_url="",
    )
    with TestClient(create_app(settings=settings)) as client:
        response = client.get("/legal/privacy", follow_redirects=False)
        assert response.status_code == 200
        assert "Datenschutz" in response.text


def test_public_header_links_to_project_site(client: TestClient) -> None:
    """Die Kopfnavigation der Public-Zone verweist auf die Projektseite
    und macht die öffentlichen Downloads erreichbar."""
    response = client.get("/downloads")
    assert 'href="https://www.ref4ep.de"' in response.text
    assert 'href="/downloads"' in response.text
    assert 'href="/portal/"' in response.text


def test_static_style_css_is_served(client: TestClient) -> None:
    response = client.get("/static/style.css")
    assert response.status_code == 200
    assert "text/css" in response.headers["content-type"]


def test_public_style_matches_portal_identity() -> None:
    """Block 0055: Die Public-Zone nutzt dieselbe Identität wie das
    Portal — Marineblau, Petrol, serifenlose Schrift — statt des alten
    Georgia-Layouts."""
    from pathlib import Path

    css = (
        Path(__file__).resolve().parent.parent / "src" / "ref4ep" / "static" / "style.css"
    ).read_text(encoding="utf-8")
    assert "--pub-navy: #1c2c4c" in css
    assert "--pub-teal: #1f7a8c" in css
    assert "system-ui" in css
    # Die alte Serifen-Grundschrift ist weg.
    assert "Georgia" not in css
    # Mindestklickfläche und sichtbarer Fokusring wie im Portal.
    assert "--pub-control-min: 2.25rem" in css
    assert "outline: 3px solid" in css
