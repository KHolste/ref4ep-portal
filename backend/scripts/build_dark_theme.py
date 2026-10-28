"""Erzeugt ``web/theme-dark.css`` — den dunklen Modus des Portals.

    python scripts/build_dark_theme.py            # Datei schreiben
    python scripts/build_dark_theme.py --check    # nur prüfen (Exit 1, wenn veraltet)

(Aufruf aus dem Ordner ``backend``.)

Warum erzeugt statt von Hand geschrieben: ``style.css`` ist über viele
Ausbaustufen gewachsen und enthält Hunderte fest notierter heller
Farben. Diese Datei wird deshalb abgeleitet und nie von Hand geändert:

1. Dunkle Werte der ``--t-``-Tokens (das Einzige, was hier gestaltet ist).
2. Jede Farbangabe aus ``style.css``, in der Helligkeit gespiegelt.
3. Die Farbregeln aus ``theme.css`` noch einmal (unverändert, sie hängen
   an den Tokens) — damit sie wie im hellen Modus das letzte Wort haben.
4. Regeln für die fest im Zeitplan-SVG notierten Farben (``gantt.js``).

Alles steht unter ``:root[data-theme="dark"]``. Der Modus ist damit rein
additiv und greift nur, wenn jemand ihn einschaltet.

Nach Änderungen an ``style.css``, ``theme.css`` oder den Farben in
``gantt.js`` neu ausführen; ``tests/test_web_dark_theme.py`` schlägt an,
wenn das fehlt.
"""

from __future__ import annotations

import colorsys
import re
import sys
from pathlib import Path

WEB = Path(__file__).resolve().parents[1] / "src" / "ref4ep" / "web"
OUT = WEB / "theme-dark.css"
PREFIX = ':root[data-theme="dark"]'

DARK_TOKENS = """\
:root[data-theme="dark"] {
  color-scheme: dark;
  --t-bg: #0f141b;
  --t-surface: #171e28;
  --t-soft: #1b2330;
  --t-raised: #212b3a;
  --t-side: #121821;
  --t-line: #273244;
  --t-line-strong: #34415a;
  --t-divider: #1f2835;
  --t-fg: #e5eaf1;
  --t-strong: #f0f4f9;
  --t-muted: #a3afbf;
  --t-subtle: #97a3b4;
  --t-faint: #6f7c8e;
  --t-link: #8cc3ee;
  --t-accent: #5cc0d2;
  --t-accent-hover: #7fd0de;
  --t-accent-soft: #143239;
  --t-on-accent: #06232a;
  --t-amber: #e8b45a;
  --t-amber-soft: #382c14;
  --t-green: #7fd39b;
  --t-green-soft: #162f20;
  --t-red: #ff8f85;
  --t-red-soft: #3a1f1c;
  --t-ok-bg: #162f20;
  --t-ok-fg: #8fdba8;
  --t-warn-bg: #372c14;
  --t-warn-fg: #f0c36d;
  --t-err-bg: #3a1f1c;
  --t-err-fg: #ffa39a;
  --t-info-bg: #172a40;
  --t-info-fg: #9cc7f2;
  --t-neutral-bg: #232c3a;
  --t-neutral-fg: #c3ccd8;
  --t-shadow: 0 4px 14px rgba(0, 0, 0, .4);
}
"""

# Eigenschaften, deren Farbwerte umgerechnet werden.
COLOR_PROPS = re.compile(
    r"^(color|background|background-color|background-image|border"
    r"|border-(top|right|bottom|left)(-color)?|border-color|outline"
    r"|outline-color|fill|stroke|caret-color|accent-color|column-rule"
    r"|text-decoration-color|box-shadow)$"
)
NAMED = {
    "white": "#ffffff",
    "black": "#000000",
    "gray": "#808080",
    "grey": "#808080",
    "silver": "#c0c0c0",
    "red": "#ff0000",
}
# Flächen, die in beiden Modi gleich aussehen: die Kopfbänder mit Bild
# oder dunklem Verlauf tragen helle Schrift und bleiben, wie sie sind —
# samt allem, was darin sitzt (z. B. die Kennzahlen der Arbeitspakete).
# Die hellen Kopfbänder (Cockpit, Zeitplan) fehlen hier bewusst: sie
# werden umgerechnet und bekommen in theme.css Token-Farben.
KEEP_AS_IS = (
    "wp-overview-hero",
    "wp-overview-summary",
    "wp-stat",
    "library-hero",
    "contacts-hero",
    "campaigns-hero",
    "meetings-hero",
    "actions-hero",
    "comments-hero",
    "milestones-hero",
    "calendar-hero",
)
_COLOR_RE = re.compile(r"#[0-9a-fA-F]{3,8}\b|rgba?\([^)]*\)|\b(?:" + "|".join(NAMED) + r")\b")


# ── Farbumrechnung ──────────────────────────────────────────────


def _to_dark(r: float, g: float, b: float) -> tuple[int, int, int]:
    """Helligkeit spiegeln: Weiß wird zur dunklen Fläche, dunkler Text
    wird hell. Farbton bleibt; fast-graue Töne bekommen den bläulichen
    Stich der dunklen Palette, kräftige Töne etwas weniger Sättigung."""
    h, light, s = colorsys.rgb_to_hls(r, g, b)
    new_l = 0.92 - 0.80 * light
    if s < 0.12:
        h, s = 0.60, (0.22 if new_l < 0.35 else 0.12)
    else:
        s *= 0.75 if new_l < 0.35 else 0.9
    out = colorsys.hls_to_rgb(h, new_l, s)
    return tuple(round(max(0.0, min(1.0, c)) * 255) for c in out)  # type: ignore[return-value]


def convert_color(token: str) -> str:
    low = token.lower()
    if low in NAMED:
        token = low = NAMED[low]
    if low.startswith("#"):
        hexa = low[1:]
        if len(hexa) in (3, 4):
            hexa = "".join(c * 2 for c in hexa)
        if len(hexa) not in (6, 8):
            return token
        r, g, b = (int(hexa[i : i + 2], 16) / 255 for i in (0, 2, 4))
        dr, dg, db = _to_dark(r, g, b)
        return f"#{dr:02x}{dg:02x}{db:02x}{hexa[6:]}"
    inner = token[token.index("(") + 1 : -1]
    parts = [p.strip() for p in re.split(r"[,/\s]+", inner) if p.strip()]
    if len(parts) < 3 or any("%" in p for p in parts[:3]):
        return token
    try:
        r, g, b = (float(p) / 255 for p in parts[:3])
    except ValueError:
        return token
    alpha = parts[3] if len(parts) > 3 else None
    # Halbtransparente dunkle Töne (Schwarz, Marineblau) sind Schatten
    # oder Abdunkler hinter Dialogen — sie bleiben dunkel.
    if alpha is not None and colorsys.rgb_to_hls(r, g, b)[1] < 0.3:
        return token
    dr, dg, db = _to_dark(r, g, b)
    if alpha is not None:
        return f"rgba({dr}, {dg}, {db}, {alpha})"
    return f"rgb({dr}, {dg}, {db})"


def convert_value(prop: str, value: str) -> str | None:
    """Wert mit umgerechneten Farben — oder None, wenn nichts zu tun ist."""

    def _sub(m: re.Match[str]) -> str:
        tok = m.group(0)
        # Schatten: nur deckende Farben (Ring-Ersatz für Rahmen) anfassen.
        if prop == "box-shadow" and tok.lower().startswith("rgb"):
            return tok
        return convert_color(tok)

    # url(...) und var(...) dürfen nicht angefasst werden.
    pieces = re.split(r"(url\([^)]*\)|var\([^)]*\))", value)
    out = "".join(p if p.startswith(("url(", "var(")) else _COLOR_RE.sub(_sub, p) for p in pieces)
    return out if out != value else None


# ── Minimaler CSS-Leser ─────────────────────────────────────────


def strip_comments(css: str) -> str:
    return re.sub(r"/\*.*?\*/", "", css, flags=re.S)


def split_top(text: str, sep: str) -> list[str]:
    """An ``sep`` trennen, aber nicht in Klammern oder Anführungszeichen."""
    parts: list[str] = []
    cur: list[str] = []
    depth, quote = 0, ""
    for ch in text:
        if quote:
            cur.append(ch)
            if ch == quote:
                quote = ""
            continue
        if ch in "\"'":
            quote = ch
        elif ch in "([":
            depth += 1
        elif ch in ")]":
            depth -= 1
        if ch == sep and depth == 0:
            parts.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
    parts.append("".join(cur))
    return parts


def parse_blocks(css: str) -> list[tuple[str, str]]:
    """Folge von (Vorspann, Blockinhalt) der obersten Ebene."""
    out: list[tuple[str, str]] = []
    i, n = 0, len(css)
    while i < n:
        j = css.find("{", i)
        if j == -1:
            break
        prelude = css[i:j].strip()
        depth, k, quote = 1, j + 1, ""
        while k < n and depth:
            ch = css[k]
            if quote:
                if ch == quote:
                    quote = ""
            elif ch in "\"'":
                quote = ch
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
            k += 1
        out.append((prelude, css[j + 1 : k - 1]))
        i = k
    return out


def prefix_selector(selector: str) -> str | None:
    sel = " ".join(selector.split())
    if not sel or sel.startswith(":root"):
        return None  # Token-Blöcke stehen oben von Hand
    if sel == "html" or sel.startswith("html "):
        return PREFIX + sel[4:]
    return f"{PREFIX} {sel}"


def emit_rules(css: str, *, convert: bool, indent: str = "") -> list[str]:
    lines: list[str] = []
    for prelude, body in parse_blocks(css):
        if prelude.startswith("@"):
            # Gedruckt wird immer hell (app.js schaltet vor dem Drucken um).
            if prelude.startswith(("@media", "@supports")) and "print" not in prelude:
                inner = emit_rules(body, convert=convert, indent=indent + "  ")
                if inner:
                    lines += [f"{indent}{' '.join(prelude.split())} {{", *inner, f"{indent}}}"]
            continue  # @font-face, @keyframes … haben keine Farben
        selectors = [
            s
            for s in map(prefix_selector, split_top(prelude, ","))
            if s and not (convert and any(k in s for k in KEEP_AS_IS))
        ]
        if not selectors:
            continue
        decls = []
        for raw in split_top(body, ";"):
            if ":" not in raw:
                continue
            prop, value = raw.split(":", 1)
            prop, value = prop.strip().lower(), " ".join(value.split())
            if not COLOR_PROPS.match(prop):
                continue
            if convert:
                # Auch unveränderte Werte (``none``, ``transparent``,
                # ``var(...)``) mitnehmen: sonst gewönnen im dunklen Modus
                # spätere, schwächere Regeln, die im hellen Modus verlieren.
                new = convert_value(prop, value)
                decls.append(f"{prop}: {value if new is None else new}")
            elif prop != "box-shadow" or "var(" in value or value == "none":
                decls.append(f"{prop}: {value}")
        if decls:
            lines.append(f"{indent}{', '.join(selectors)} {{ " + "; ".join(decls) + "; }")
    return lines


# ── Farben im Zeitplan-SVG ──────────────────────────────────────

_HEX_IN_JS = re.compile(r"[\"'](#[0-9a-fA-F]{3}|#[0-9a-fA-F]{6})[\"']")


def svg_rules() -> list[str]:
    """``gantt.js`` setzt Farben als SVG-Attribute (``fill``/``stroke``).
    CSS schlägt Präsentationsattribute — Attribut-Selektoren reichen."""
    text = (WEB / "modules" / "gantt.js").read_text(encoding="utf-8")
    colors = sorted({c.lower() for c in _HEX_IN_JS.findall(text)})
    lines = []
    for color in colors:
        dark = convert_color(color)
        for attr in ("fill", "stroke"):
            lines.append(f'{PREFIX} .gantt-svg [{attr}="{color}" i] {{ {attr}: {dark}; }}')
    return lines


def build() -> str:
    style = strip_comments((WEB / "style.css").read_text(encoding="utf-8"))
    theme = strip_comments((WEB / "theme.css").read_text(encoding="utf-8"))
    parts = [
        "/* ERZEUGT von scripts/build_dark_theme.py — nicht von Hand ändern.",
        '   Dunkler Modus: greift nur unter :root[data-theme="dark"]. */',
        "",
        DARK_TOKENS,
        "/* ── 1. Farben aus style.css, in der Helligkeit gespiegelt ── */",
        *emit_rules(style, convert=True),
        "",
        "/* ── 2. Farbregeln aus theme.css (Tokens) behalten das letzte Wort ── */",
        *emit_rules(theme, convert=False),
        "",
        "/* ── 3. Fest im Zeitplan-SVG notierte Farben ── */",
        *svg_rules(),
        "",
    ]
    return "\n".join(parts)


def main() -> int:
    css = build()
    if "--check" in sys.argv:
        current = OUT.read_text(encoding="utf-8") if OUT.is_file() else ""
        if current.replace("\r\n", "\n") != css:
            print("theme-dark.css ist veraltet — python scripts/build_dark_theme.py ausführen.")
            return 1
        return 0
    OUT.write_text(css, encoding="utf-8", newline="\n")
    print(f"{OUT.name}: {css.count(chr(10))} Zeilen")
    return 0


if __name__ == "__main__":
    sys.exit(main())
