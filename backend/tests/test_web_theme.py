"""Erscheinungsbild: ``theme.css`` liegt über ``style.css``; der dunkle
Modus ``theme-dark.css`` wird erzeugt (``scripts/build_dark_theme.py``)
und greift nur unter ``data-theme="dark"``."""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

from fastapi.testclient import TestClient

BACKEND = Path(__file__).resolve().parents[1]
WEB = BACKEND / "src" / "ref4ep" / "web"


def _generator():
    spec = importlib.util.spec_from_file_location(
        "build_dark_theme", BACKEND / "scripts" / "build_dark_theme.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _read(name: str) -> str:
    return (WEB / name).read_text(encoding="utf-8")


# ---- Einbindung ------------------------------------------------------------


def test_theme_layers_load_after_style_css() -> None:
    html = _read("index.html")
    style = html.find('href="/portal/style.css?v=')
    theme = html.find('href="/portal/theme.css?v=')
    dark = html.find('href="/portal/theme-dark.css?v=')
    assert -1 < style < theme < dark


def test_theme_files_use_the_current_cache_buster() -> None:
    html = _read("index.html")
    version = re.search(r'ASSET_VERSION = "(\d+)"', _read("app.js")).group(1)
    assert f"/portal/theme.css?v={version}" in html
    assert f"/portal/theme-dark.css?v={version}" in html


def test_toggle_wired_and_choice_remembered() -> None:
    html = _read("index.html")
    js = _read("app.js")
    assert 'id="theme-toggle"' in html
    # Gemerkte Wahl wird gesetzt, bevor die Seite gezeichnet wird.
    head = html[: html.find("</head>")]
    assert "localStorage.getItem('ref4ep.theme')==='dark'" in head
    i = js.find("function attachThemeToggle(")
    body = js[i : i + 1600]
    assert 'getElementById("theme-toggle")' in body
    assert 'setAttribute("data-theme", "dark")' in body
    assert "localStorage.setItem(THEME_KEY" in body
    assert 'THEME_KEY = "ref4ep.theme"' in js
    # Gedruckt wird hell.
    assert '"beforeprint"' in body and '"afterprint"' in body
    assert "attachThemeToggle();" in js


def test_fonts_are_local_and_licensed() -> None:
    css = _read("theme.css")
    for url in re.findall(r'url\("(/portal/fonts/[^"]+)"\)', css):
        assert (WEB / url.removeprefix("/portal/")).is_file(), url
    assert (WEB / "fonts" / "LICENSE-IBM-Plex.txt").is_file()
    assert "fonts.googleapis" not in css


def test_every_nav_entry_has_an_icon() -> None:
    html = _read("index.html")
    css = _read("theme.css")
    routes = re.findall(r'data-route="([a-z_]+)"', html)
    assert routes
    for route in routes:
        assert f'a[data-route="{route}"]' in css, f"Symbol für {route!r} fehlt"


def test_theme_assets_are_served(client: TestClient) -> None:
    for path in ("/portal/theme.css", "/portal/theme-dark.css"):
        resp = client.get(path)
        assert resp.status_code == 200
        assert "text/css" in resp.headers["content-type"]
    font = client.get("/portal/fonts/ibm-plex-sans-latin-400-normal.woff2")
    assert font.status_code == 200
    assert font.content[:4] == b"wOF2"


# ---- Dunkler Modus ---------------------------------------------------------


def test_generated_file_is_up_to_date() -> None:
    """Nach Änderungen an style.css/theme.css muss der Generator laufen:
    ``python scripts/build_dark_theme.py`` (im Ordner backend)."""
    assert _read("theme-dark.css").replace("\r\n", "\n") == _generator().build()


def test_dark_rules_only_apply_when_switched_on() -> None:
    css = re.sub(r"/\*.*?\*/", "", _read("theme-dark.css"), flags=re.S)
    for line in css.splitlines():
        line = line.strip()
        if not line or line.startswith(("@", "}", "--", "color-scheme")):
            continue
        assert line.startswith(':root[data-theme="dark"]'), line[:80]


def test_colour_conversion_flips_lightness() -> None:
    gen = _generator()

    def lum(hex_colour: str) -> float:
        r, g, b = (int(hex_colour[i : i + 2], 16) for i in (1, 3, 5))
        return (0.299 * r + 0.587 * g + 0.114 * b) / 255

    assert lum(gen.convert_color("#ffffff")) < 0.2  # Fläche wird dunkel
    assert lum(gen.convert_color("#1c2c4c")) > 0.6  # Marineblau-Text wird hell
    assert lum(gen.convert_color("white")) < 0.2
    # Schatten und Abdunkler (halbtransparent, dunkel) bleiben, wie sie sind.
    assert gen.convert_color("rgba(0,0,0,.4)") == "rgba(0,0,0,.4)"
    assert gen.convert_color("rgba(13, 19, 33, 0.55)") == "rgba(13, 19, 33, 0.55)"
    # Transparenz heller Töne bleibt erhalten.
    assert gen.convert_color("rgba(255, 255, 255, .5)").endswith(", .5)")
    # url(...) und var(...) werden nie angefasst.
    value = 'var(--x) url("a#fff.png") #ffffff'
    out = gen.convert_value("background", value)
    assert out.startswith('var(--x) url("a#fff.png") #') and out != value


def test_theme_rules_keep_the_last_word() -> None:
    """Die Token-Regeln aus theme.css stehen hinter den umgerechneten aus
    style.css — sonst gewönnen dort alte Flächen- und Knopffarben."""
    css = _read("theme-dark.css")
    converted = css.find("1. Farben aus style.css")
    themed = css.find("2. Farbregeln aus theme.css")
    assert -1 < converted < themed
    assert ':root[data-theme="dark"] .app-sidebar { background: var(--t-side);' in css[themed:]


def test_image_heroes_are_not_converted() -> None:
    """Die Bild-Kopfbänder sind schon dunkel und bleiben unverändert."""
    css = _read("theme-dark.css")
    head = css[: css.find("2. Farbregeln aus theme.css")]
    assert "meetings-hero" not in head
    assert "wp-stat" not in head
    # Helle Kopfbänder ohne Bild werden dagegen umgerechnet.
    assert "gantt-hero" in head


def test_print_rules_are_not_part_of_dark_mode() -> None:
    assert "@media print" not in _read("theme-dark.css")


def test_dark_tokens_defined() -> None:
    css = _read("theme-dark.css")
    block = css[css.find(':root[data-theme="dark"] {') :]
    block = block[: block.find("}")]
    light = _read("theme.css")
    root = light[light.find(":root {") :]
    root = root[: root.find("}")]
    for token in re.findall(r"(--t-[a-z-]+):\s*#", root):
        assert token + ":" in block, token
    assert "color-scheme: dark" in block


def test_gantt_svg_colours_have_dark_rules() -> None:
    css = _read("theme-dark.css")
    js = (WEB / "modules" / "gantt.js").read_text(encoding="utf-8")
    for colour in ("#cdd5e0", "#eef2f7"):
        assert colour in js
        assert f'.gantt-svg [fill="{colour}" i]' in css


# ---- Öffentliche Zone ------------------------------------------------------

STATIC = BACKEND / "src" / "ref4ep" / "static"
TEMPLATES = BACKEND / "src" / "ref4ep" / "templates"


def test_public_zone_has_dark_tokens_for_every_light_token() -> None:
    css = (STATIC / "style.css").read_text(encoding="utf-8")
    light = css[css.index(":root {") :]
    light = light[: light.index("}")]
    dark = css[css.index(':root[data-theme="dark"] {') :]
    dark = dark[: dark.index("}")]
    for token in re.findall(r"(--pub-[a-z-]+):\s*#", light):
        assert token + ":" in dark, token
    # Außerhalb der Token-Blöcke keine fest notierten Farben — sonst
    # bliebe im dunklen Modus etwas hell.
    rest = re.sub(r":root[^{]*\{[^}]*\}", "", re.sub(r"/\*.*?\*/", "", css, flags=re.S))
    assert not re.findall(r"#[0-9a-fA-F]{3,8}\b|rgba?\(", rest)


def test_public_zone_shares_the_theme_choice_with_the_portal() -> None:
    base = (TEMPLATES / "_base.html").read_text(encoding="utf-8")
    head = base[: base.index("</head>")]
    assert "localStorage.getItem('ref4ep.theme')==='dark'" in head
    assert 'id="theme-toggle"' in base
    assert 'localStorage.setItem("ref4ep.theme"' in base
    assert "beforeprint" in base


def test_login_page_renders_theme_toggle(client: TestClient) -> None:
    html = client.get("/login").text
    assert 'id="theme-toggle"' in html
    assert 'href="/portal/" aria-current="page"' in html


# ---- Cockpit-Ampel und Verwaltungsseiten -------------------------------------


def test_cockpit_traffic_light_shows_only_attention_by_default() -> None:
    body = (WEB / "modules" / "cockpit.js").read_text(encoding="utf-8")
    i = body.index("function renderWorkpackageHealthCard(")
    card = body[i : body.index("function renderProjectKpisCard(")]
    # Offen stehen nur rot und gelb …
    assert 'e.traffic_light === "red" || e.traffic_light === "yellow"' in card
    # … der Rest klappt auf, die Zählung steht oben.
    assert '"details"' in card and "Arbeitspakete anzeigen" in card
    assert "cockpit-health-summary" in card
    for label in ("kritisch", "Aufmerksamkeit", "im Plan", "ohne Bewertung"):
        assert label in body


def test_admin_pages_use_german_terms() -> None:
    partners = (WEB / "modules" / "admin_partners.js").read_text(encoding="utf-8")
    assert '"Soft-Delete …"' not in partners and '"soft-deleted"' not in partners
    assert '"Entfernen …"' in partners
    audit = (WEB / "modules" / "audit.js").read_text(encoding="utf-8")
    for old in ('"Entity"', '"Akteur"', "entity_type (z. B.", "(keine Einträge)"):
        assert old not in audit, old
    assert 'h("legend", {}, "Protokoll filtern")' in audit
    account = (WEB / "modules" / "account.js").read_text(encoding="utf-8")
    assert '"Rolle im Portal"' in account and "Administration" in account
