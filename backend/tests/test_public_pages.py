"""Öffentliche, serverseitig gerenderte Pages."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_home_renders_html_with_project_name(client: TestClient) -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "Ref4EP" in response.text


def test_imprint_renders(client: TestClient) -> None:
    response = client.get("/legal/imprint")
    assert response.status_code == 200
    assert "Impressum" in response.text


def test_privacy_renders(client: TestClient) -> None:
    response = client.get("/legal/privacy")
    assert response.status_code == 200
    assert "Datenschutz" in response.text


def test_static_style_css_is_served(client: TestClient) -> None:
    response = client.get("/static/style.css")
    assert response.status_code == 200
    assert "text/css" in response.headers["content-type"]
