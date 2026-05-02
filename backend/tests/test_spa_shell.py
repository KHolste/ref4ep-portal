"""SPA-Shell unter /portal/."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_portal_root_serves_index_html(client: TestClient) -> None:
    response = client.get("/portal/")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "Ref4EP-Portal" in response.text


def test_portal_app_js_is_served(client: TestClient) -> None:
    response = client.get("/portal/app.js")
    assert response.status_code == 200
    content_type = response.headers["content-type"].lower()
    assert "javascript" in content_type


def test_portal_style_css_is_served(client: TestClient) -> None:
    response = client.get("/portal/style.css")
    assert response.status_code == 200
    assert "text/css" in response.headers["content-type"].lower()
