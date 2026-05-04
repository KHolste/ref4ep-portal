"""UI-nahe Assertions: statische Web-Assets enthalten/erwähnen die richtigen Stellen.

Wir verzichten bewusst auf einen Browser-Test: das Portal hat
keine Build-Kette. Stattdessen prüfen wir das ausgelieferte
JavaScript/HTML als Text — das fängt die wichtigsten Regressionen
(z. B. ``general_email`` taucht doch wieder auf) zuverlässig ab.
"""

from __future__ import annotations

from pathlib import Path

import pytest

WEB_DIR = Path(__file__).resolve().parent.parent / "src" / "ref4ep" / "web"
MODULES_DIR = WEB_DIR / "modules"


@pytest.fixture
def all_web_text() -> str:
    parts: list[str] = []
    for path in [WEB_DIR / "app.js", WEB_DIR / "common.js", WEB_DIR / "index.html"]:
        parts.append(path.read_text(encoding="utf-8"))
    for js in sorted(MODULES_DIR.glob("*.js")):
        parts.append(js.read_text(encoding="utf-8"))
    return "\n".join(parts)


def test_general_email_is_gone_from_frontend(all_web_text: str) -> None:
    """0007: keine UI-Reste der entfernten Allgemein-E-Mail."""
    assert "general_email" not in all_web_text
    # Auch keine deutsche Schreibweise als Label übrig.
    assert "Allgemeine E-Mail" not in all_web_text


def test_legacy_person_fields_are_gone_from_partner_stamm_ui() -> None:
    """0008: alte personenbezogene Partner-Felder dürfen nicht mehr in
    partner_detail.js / admin_partners.js auftauchen — weder als
    Schlüssel noch als Label.
    """
    paths = (
        MODULES_DIR / "partner_detail.js",
        MODULES_DIR / "admin_partners.js",
    )
    for path in paths:
        body = path.read_text(encoding="utf-8")
        for legacy_key in (
            "primary_contact_name",
            "contact_email",
            "contact_phone",
            "project_role_note",
        ):
            assert legacy_key not in body, f"{path.name} enthält noch {legacy_key!r}"
        for legacy_label in (
            "Projektkontakt",
            "Kontakt-E-Mail",
            "Rolle / Aufgabe im Projekt",
        ):
            assert legacy_label not in body, f"{path.name} enthält noch Label {legacy_label!r}"
    # Telefon ist im Kontaktpersonen-Block legitim — daher prüfen wir dort
    # nur, dass das Stamm-Edit keine eigene Telefon-Sektion mehr enthält:
    detail = (MODULES_DIR / "partner_detail.js").read_text(encoding="utf-8")
    assert "Allgemeiner Projektkontakt" not in detail


def test_partner_detail_uses_new_organization_terms() -> None:
    body = (MODULES_DIR / "partner_detail.js").read_text(encoding="utf-8")
    for term in (
        "Organisation",
        "Bearbeitende Einheit",
        "Adresse der Organisation",
        "Adresse der bearbeitenden Einheit",
        "Kontaktpersonen",
    ):
        assert term in body, f"partner_detail.js sollte {term!r} enthalten"
    # Toggle / Checkbox für identische Adresse vorhanden.
    assert "unit_address_same_as_organization" in body
    assert "identisch" in body


def test_partner_detail_renders_contacts_section() -> None:
    body = (MODULES_DIR / "partner_detail.js").read_text(encoding="utf-8")
    assert "Kontaktpersonen" in body
    assert "Kontakt anlegen" in body or "Kontakt anlegen …" in body
    assert "/api/partners/${partner.id}/contacts" in body or "/contacts" in body
    assert "/api/partner-contacts/" in body


def test_admin_partners_uses_name_as_link_and_no_duplicate_edit() -> None:
    body = (MODULES_DIR / "admin_partners.js").read_text(encoding="utf-8")
    # Name → Link auf Detailseite.
    assert "/portal/partners/${partner.id}" in body
    # Kein doppelter Bearbeiten-Button mehr in der Listenzeile (Edit lebt im Detail).
    assert "Bearbeiten …" not in body
    # Optional: bearbeitende Einheit ist eine eigene Spalte in der Liste.
    assert "Bearbeitende Einheit" in body


def test_account_password_form_is_collapsible() -> None:
    body = (MODULES_DIR / "account.js").read_text(encoding="utf-8")
    # Verwendet das <details>-Element für die einklappbare Sektion.
    assert "details" in body
    assert "collapsible" in body
    # Default ist eingeklappt — d. h. open wird nur bei must_change_password gesetzt.
    assert "must_change_password" in body


def test_form_actions_has_visible_spacing() -> None:
    css = (WEB_DIR / "style.css").read_text(encoding="utf-8")
    # Die neue Klasse für Speichern/Abbrechen-Reihen ist im Stylesheet vorhanden
    # und enthält sichtbare Abstände (gap + margin-top).
    assert ".form-actions" in css
    assert "gap" in css
    # In den Modulen wird sie tatsächlich verwendet.
    for name in ("partner_detail.js", "admin_partners.js", "account.js"):
        body = (MODULES_DIR / name).read_text(encoding="utf-8")
        assert "form-actions" in body, f"{name} sollte form-actions verwenden"


def _broken_string_lines(src: str) -> list[tuple[int, str, str]]:
    """Findet einzeilige String-Literale ('…' oder \"…\"), die über
    einen Zeilenumbruch hinausgehen — typisch für versehentlich
    gesetzte ASCII-Anführungszeichen (U+0022) als deutsches
    Schließzeichen statt U+201C („…").

    Liefert eine Liste ``(start_line, quote, source_line)``.
    """
    issues: list[tuple[int, str, str]] = []
    i = 0
    line = 1
    in_str: str | None = None
    str_start_line = 0
    in_line_comment = False
    in_block_comment = False
    while i < len(src):
        c = src[i]
        nxt = src[i + 1] if i + 1 < len(src) else ""
        if c == "\n":
            if in_str in ('"', "'"):
                issues.append((str_start_line, in_str, src.splitlines()[str_start_line - 1]))
                in_str = None
            line += 1
            in_line_comment = False
            i += 1
            continue
        if in_line_comment:
            i += 1
            continue
        if in_block_comment:
            if c == "*" and nxt == "/":
                in_block_comment = False
                i += 2
                continue
            i += 1
            continue
        if in_str:
            if c == "\\":
                i += 2
                continue
            if c == in_str:
                in_str = None
            i += 1
            continue
        if c == "/" and nxt == "/":
            in_line_comment = True
            i += 2
            continue
        if c == "/" and nxt == "*":
            in_block_comment = True
            i += 2
            continue
        if c in ('"', "'", "`"):
            in_str = c
            str_start_line = line
        i += 1
    return issues


def test_no_javascript_string_spans_a_newline() -> None:
    """Regressionstest für ‚missing ) after argument list'.

    Konkreter Auslöser: ein deutscher Schließtyp ‚"' (U+0022, ASCII)
    statt ‚"' (U+201C) beendete ein Stringliteral mitten im Text.
    Backtick-Templates sind erlaubt mehrzeilig — die werden hier
    bewusst nicht moniert.
    """
    failures: list[str] = []
    targets = list(sorted(MODULES_DIR.glob("*.js"))) + [WEB_DIR / "app.js", WEB_DIR / "common.js"]
    for path in targets:
        for ln, quote, src_line in _broken_string_lines(path.read_text(encoding="utf-8")):
            failures.append(f"{path.name}:{ln} String {quote!r} unterminiert: {src_line!r}")
    assert not failures, "\n".join(failures)
