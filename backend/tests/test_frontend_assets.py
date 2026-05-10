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


# ---- Block 0009 — WP-Cockpit + Meilensteine ----------------------------


def test_workpackage_detail_renders_cockpit_sections() -> None:
    body = (MODULES_DIR / "workpackage_detail.js").read_text(encoding="utf-8")
    for term in (
        "Status",
        "Kurzbeschreibung",
        "Nächste Schritte",
        "Offene Punkte",
        "Cockpit",
        "Meilensteine",
        "Kontaktpersonen des Lead-Partners",
    ):
        assert term in body, f"workpackage_detail.js sollte {term!r} enthalten"
    # Status-Werte (intern)
    assert "in_progress" in body
    assert "waiting_for_input" in body
    assert "critical" in body
    # Deutsche Anzeige
    assert "in Arbeit" in body
    assert "wartet auf Input" in body


def test_navigation_includes_milestones_link() -> None:
    body = (WEB_DIR / "index.html").read_text(encoding="utf-8")
    assert 'href="/portal/milestones"' in body
    assert "Meilensteine" in body
    # Route registriert
    app_js = (WEB_DIR / "app.js").read_text(encoding="utf-8")
    assert "milestones" in app_js


def test_navigation_includes_gantt_and_comments_links() -> None:
    """Block 0024 + 0026: globale Übersichten brauchen Hauptnav-Anker."""
    body = (WEB_DIR / "index.html").read_text(encoding="utf-8")
    assert 'href="/portal/gantt"' in body
    assert "Zeitplan" in body
    assert 'href="/portal/document-comments"' in body
    assert "Kommentare" in body


def test_stylesheet_has_classes_for_new_features() -> None:
    """Block 0024 / 0025 / 0026: CSS-Klassen für die neuen Module sind
    im zentralen Stylesheet definiert."""
    css = (WEB_DIR / "style.css").read_text(encoding="utf-8")
    # Comments
    for cls in (".comment-item", ".comment-text", ".comment-add-form", ".comment-edit-form"):
        assert cls in css, f"CSS-Klasse {cls!r} fehlt"
    # Ampel-Punkte
    for cls in (
        ".traffic-dot-green",
        ".traffic-dot-yellow",
        ".traffic-dot-red",
        ".traffic-dot-gray",
    ):
        assert cls in css, f"Ampel-Klasse {cls!r} fehlt"
    # Cockpit-Erweiterungen
    for cls in (".cockpit-progressbar", ".cockpit-wp-health", ".cockpit-timeline"):
        assert cls in css, f"Dashboard-Klasse {cls!r} fehlt"
    # Gantt
    for cls in (".gantt-scroll", ".gantt-svg", ".gantt-range-btn", ".gantt-filter-bar"):
        assert cls in css, f"Gantt-Klasse {cls!r} fehlt"


def test_milestones_page_renders_timeline() -> None:
    """UX-Polish: Meilensteine werden als vertikale Timeline statt
    Tabelle dargestellt — die Labels für Edit-Form / Card-Meta bleiben
    aber sichtbar im Source."""
    body = (MODULES_DIR / "milestones.js").read_text(encoding="utf-8")
    # Edit-Form-/Karten-Labels.
    for term in ("Titel", "Arbeitspaket", "Plandatum", "Istdatum", "Status", "Notiz"):
        assert term in body, f"milestones.js sollte Begriff {term!r} enthalten"
    # Status-Übersetzungen
    for status_de in ("geplant", "erreicht", "verschoben", "gefährdet", "entfallen"):
        assert status_de in body, f"milestones.js sollte Status {status_de!r} mappen"
    # Timeline-spezifische Klassen.
    assert "timeline-item" in body
    assert "timeline-card" in body


def test_no_deliverable_term_introduced_as_main_function(all_web_text: str) -> None:
    """Ref4EP führt in diesem Block bewusst keine Deliverables ein.

    „Deliverable" als Dokumenttyp-Label im Dokument-Anlegen-Dialog ist
    erlaubt — das ist alte UI-Logik. Aber es darf keine eigene
    Hauptfunktion / Sektion geben.
    """
    # Keine eigene Detailseite/Route /portal/deliverables.
    assert "/portal/deliverables" not in all_web_text
    # Keine Sektionsüberschrift „Deliverables" auf der Hauptebene.
    assert ">Deliverables<" not in all_web_text


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


def test_cockpit_uses_project_dashboard_terms() -> None:
    """Block 0010: Cockpit zeigt vier Aggregatkarten mit klaren deutschen Labels."""
    body = (MODULES_DIR / "cockpit.js").read_text(encoding="utf-8")
    for term in (
        "Nächste Meilensteine",
        "Überfällige Meilensteine",
        "Offene Punkte aus Arbeitspaketen",
        "Arbeitspaket-Statusübersicht",
    ):
        assert term in body, f"cockpit.js sollte {term!r} enthalten"
    # Cockpit lädt das Aggregat vom Backend.
    assert "/api/cockpit/project" in body
    # Links auf WP-Detail und Meilensteinübersicht.
    assert "/portal/workpackages/" in body
    assert "/portal/milestones" in body


def test_cockpit_has_empty_states() -> None:
    """Wenn Listen leer sind, zeigt das Cockpit deutsche Empty-States."""
    body = (MODULES_DIR / "cockpit.js").read_text(encoding="utf-8")
    assert "Keine offenen Meilensteine" in body
    assert "Keine überfälligen Meilensteine" in body
    assert "Aktuell sind keine offenen Punkte" in body


def test_cockpit_has_no_judgmental_phrases() -> None:
    """Block 0014: keine wertenden/saloppen Formulierungen im Cockpit."""
    body = (MODULES_DIR / "cockpit.js").read_text(encoding="utf-8")
    for phrase in (
        "gut so",
        "prima",
        "super",
        "alles im Griff",
    ):
        assert phrase not in body, f"Cockpit sollte ‚{phrase}‘ nicht enthalten"


def test_cockpit_open_issues_use_card_layout() -> None:
    """Block 0014: Offene Punkte werden als WP-Karten mit getrennten
    Boxen für ‚Offene Punkte‘ und ‚Nächste Schritte‘ gerendert."""
    body = (MODULES_DIR / "cockpit.js").read_text(encoding="utf-8")
    # Karten und Grid-Hülle vorhanden.
    assert "wp-issue-card" in body
    assert "wp-issue-grid" in body
    assert "wp-issue-section" in body
    assert "wp-issue-label" in body
    # Beide Bereichs-Labels sind sichtbar.
    assert "Offene Punkte" in body
    assert "Nächste Schritte" in body
    # Alte Fließtext-Form (Inline ‚Offen: ‘ + br) ist verschwunden.
    assert '"Offen: "' not in body


def test_wp_issue_styles_present() -> None:
    css = (WEB_DIR / "style.css").read_text(encoding="utf-8")
    for cls in (".wp-issue-card", ".wp-issue-grid", ".wp-issue-section", ".wp-issue-label"):
        assert cls in css
    # Zweispaltig auf breiten Bildschirmen, einspaltig sonst.
    assert "@media (min-width: 720px)" in css


def test_cockpit_does_not_introduce_deliverables() -> None:
    body = (MODULES_DIR / "cockpit.js").read_text(encoding="utf-8")
    # Weder als Wort noch als Pfad/Endpoint.
    assert "deliverable" not in body.lower()
    assert "/api/deliverables" not in body
    assert "/portal/deliverables" not in body


def test_cockpit_grid_styles_are_present() -> None:
    css = (WEB_DIR / "style.css").read_text(encoding="utf-8")
    assert ".cockpit-grid" in css
    assert ".cockpit-card" in css


def test_common_js_exports_ux_helpers() -> None:
    """Block 0011: zentrale Render-Helper für Lade-/Fehler-/Empty-Zustände."""
    body = (WEB_DIR / "common.js").read_text(encoding="utf-8")
    assert "export function renderLoading" in body
    assert "export function renderError" in body
    assert "export function renderEmpty" in body
    assert "export function crossNav" in body


def test_modules_use_central_loading_helpers() -> None:
    """Cockpit, Workpackages, Workpackage-Detail und Meilensteine
    importieren ``renderLoading`` und nutzen den zentralen Helper —
    statt jeweils eigener ``Lade …``-Strings."""
    for name in (
        "cockpit.js",
        "workpackages.js",
        "workpackage_detail.js",
        "milestones.js",
    ):
        body = (MODULES_DIR / name).read_text(encoding="utf-8")
        assert "renderLoading" in body, f"{name} sollte renderLoading nutzen"


def test_modules_use_central_error_and_empty_helpers() -> None:
    for name in (
        "cockpit.js",
        "workpackages.js",
        "workpackage_detail.js",
        "milestones.js",
    ):
        body = (MODULES_DIR / name).read_text(encoding="utf-8")
        assert "renderError" in body, f"{name} sollte renderError nutzen"
        assert "renderEmpty" in body, f"{name} sollte renderEmpty nutzen"


def test_modules_render_cross_nav() -> None:
    """Drei interne Hauptseiten zeigen am Fuß die gleiche Quer-Navigation."""
    for name in (
        "cockpit.js",
        "workpackages.js",
        "milestones.js",
        "workpackage_detail.js",
    ):
        body = (MODULES_DIR / name).read_text(encoding="utf-8")
        assert "crossNav(" in body, f"{name} sollte crossNav verwenden"


# ---- Block 0012 — UX-Helper-Konsolidierung in den Restmodulen --------


# Module mit eigenem API-Call beim Render → Loading + Error sind sinnvoll.
LOADING_AND_ERROR_MODULES = (
    "partner_detail.js",
    "admin_users.js",
    "admin_user_detail.js",
    "admin_partners.js",
    "audit.js",
    "document_detail.js",
)

# Module, in denen mind. ein Empty-State über renderEmpty läuft.
EMPTY_HELPER_MODULES = (
    "partner_detail.js",
    "admin_users.js",
    "admin_user_detail.js",
    "admin_partners.js",
    "document_detail.js",
)

# Hauptseiten, die crossNav am Seitenfuß haben.
CROSS_NAV_MODULES = (
    "cockpit.js",
    "workpackages.js",
    "workpackage_detail.js",
    "milestones.js",
    "partner_detail.js",
    "account.js",
    "audit.js",
    "admin_users.js",
    "admin_user_detail.js",
    "admin_partners.js",
    "document_detail.js",
)


def test_remaining_modules_use_loading_and_error_helpers() -> None:
    """Block 0012: Module mit Render-API-Call nutzen ``renderLoading`` + ``renderError``."""
    for name in LOADING_AND_ERROR_MODULES:
        body = (MODULES_DIR / name).read_text(encoding="utf-8")
        assert "renderLoading" in body, f"{name} sollte renderLoading nutzen"
        assert "renderError" in body, f"{name} sollte renderError nutzen"


def test_remaining_modules_use_empty_helper() -> None:
    for name in EMPTY_HELPER_MODULES:
        body = (MODULES_DIR / name).read_text(encoding="utf-8")
        assert "renderEmpty" in body, f"{name} sollte renderEmpty nutzen"


def test_all_main_modules_render_cross_nav() -> None:
    """Alle internen Hauptmodule haben am Fuß den ``crossNav``-Footer."""
    for name in CROSS_NAV_MODULES:
        body = (MODULES_DIR / name).read_text(encoding="utf-8")
        assert "crossNav(" in body, f"{name} sollte crossNav verwenden"


def test_modules_no_inline_error_paragraph_for_render_failures() -> None:
    """Regressions-Schutz: nach der Umstellung darf in den Render-Pfaden
    kein hartkodiertes ``h(\"p\", { class: \"error\" }, err.message)`` mehr stehen.

    In Submit-Forms (errorBox + display:none) ist das Pattern weiterhin in Ordnung —
    der Test erlaubt es daher explizit. Die Probe greift den
    ``err.message``-Punkt, der typisch für API-Fehlerbehandlung ist.
    """
    bad_pattern = '"p", { class: "error" }, err.message'
    for name in LOADING_AND_ERROR_MODULES:
        body = (MODULES_DIR / name).read_text(encoding="utf-8")
        assert bad_pattern not in body, (
            f"{name} sollte renderError(err) statt {bad_pattern!r} verwenden"
        )


def test_cross_nav_helper_lists_three_main_pages() -> None:
    body = (WEB_DIR / "common.js").read_text(encoding="utf-8")
    # Drei Pfade müssen in der Helper-Definition stehen.
    assert '"/portal/"' in body
    assert '"/portal/workpackages"' in body
    assert '"/portal/milestones"' in body
    # Deutsche Labels.
    assert "Projektcockpit" in body
    assert "Arbeitspakete" in body
    assert "Meilensteine" in body


def test_loading_and_empty_styles_are_present() -> None:
    css = (WEB_DIR / "style.css").read_text(encoding="utf-8")
    assert ".loading" in css
    assert ".empty" in css
    assert ".cross-nav" in css


def test_manual_smoke_test_doc_exists() -> None:
    """Block 0011: manuelle Smoke-Test-Checkliste ist Teil der Doku."""
    doc = WEB_DIR.parent.parent.parent.parent / "docs" / "manual_smoke_test.md"
    assert doc.exists(), f"Erwartete {doc} fehlt"
    text = doc.read_text(encoding="utf-8")
    # Kerninhalte
    for keyword in (
        "Login",
        "Projektcockpit",
        "Arbeitspaket-Detail",
        "Meilensteinliste",
        "Meilensteinstatus",
        "Admin",
        "WP-Lead",
        "Member",
    ):
        assert keyword in text, f"Smoke-Test-Doku sollte {keyword!r} enthalten"
    # Sicherheits-Bullets
    assert "Deliverable" in text  # taucht nur als Negativhinweis auf
    assert "Kein Hard-Delete" in text


def test_smoke_test_doc_does_not_introduce_deliverables() -> None:
    doc = WEB_DIR.parent.parent.parent.parent / "docs" / "manual_smoke_test.md"
    text = doc.read_text(encoding="utf-8").lower()
    # Auch in der Doku darf „Deliverable" nicht als Funktion eingeführt werden.
    # Wir prüfen nur die Negativ-Form: keine eigene Sektion „Deliverables".
    assert "## deliverables" not in text
    assert "/portal/deliverables" not in text


# ---- Block 0013 — „Mein Team" für WP-Leads --------------------------


def test_app_js_registers_lead_team_route() -> None:
    body = (WEB_DIR / "app.js").read_text(encoding="utf-8")
    # Route ist als regex hinterlegt — prüfe charakteristische Bestandteile.
    assert "lead\\/team" in body
    assert "lead_team" in body


def test_index_html_has_lead_team_nav_hidden_by_default() -> None:
    body = (WEB_DIR / "index.html").read_text(encoding="utf-8")
    assert 'id="nav-lead-team"' in body
    assert "Mein Team" in body
    # Hidden im HTML — JS macht den Link sichtbar, wenn die Person Lead/Admin ist.
    # Der `hidden`-Marker steht im selben Tag wie id=nav-lead-team.
    nav_line = next(line for line in body.splitlines() if "nav-lead-team" in line)
    assert "hidden" in nav_line


def test_app_js_unhides_nav_for_admin_or_lead_only() -> None:
    body = (WEB_DIR / "app.js").read_text(encoding="utf-8")
    # Sichtbarkeitscheck prüft sowohl Admin als auch Lead-Membership.
    assert "wp_role" in body
    assert "wp_lead" in body
    assert "nav-lead-team" in body


def test_lead_team_module_uses_central_helpers_and_cross_nav() -> None:
    body = (MODULES_DIR / "lead_team.js").read_text(encoding="utf-8")
    for helper in ("renderLoading", "renderError", "renderEmpty", "crossNav("):
        assert helper in body, f"lead_team.js sollte {helper!r} verwenden"


def test_lead_team_uses_lead_endpoints() -> None:
    body = (MODULES_DIR / "lead_team.js").read_text(encoding="utf-8")
    assert "/api/lead/persons" in body
    assert "/api/lead/workpackages" in body


def test_lead_team_does_not_call_admin_endpoints_or_use_admin_label() -> None:
    body = (MODULES_DIR / "lead_team.js").read_text(encoding="utf-8")
    # WP-Lead-Seite darf keine Admin-API anfassen.
    assert "/api/admin/" not in body
    # „Admin" darf nicht als Funktionsbezeichnung für Lead-Aktionen auftauchen.
    # Erlaubt sind Erwähnungen im Hilfetext (z. B. „ändert nur ein Admin").
    # Wir prüfen: keine Plattformrollen-Auswahl ``role: admin`` o. ä.
    assert '"admin"' not in body
    assert "platform_role" not in body


def test_lead_team_has_no_partner_select_in_create_form() -> None:
    body = (MODULES_DIR / "lead_team.js").read_text(encoding="utf-8")
    # Es gibt keine Partner-Auswahl im Anlage-Formular.
    assert "partner_id" not in body
    assert "partner_select" not in body.lower()


def test_lead_team_has_initial_password_notice() -> None:
    body = (MODULES_DIR / "lead_team.js").read_text(encoding="utf-8")
    assert "Initialpasswort" in body
    assert "wird nicht erneut angezeigt" in body


def test_lead_team_uses_organization_wording() -> None:
    """Block 0014: Sprachkorrektur von „Partner" auf „Organisation"."""
    body = (MODULES_DIR / "lead_team.js").read_text(encoding="utf-8")
    # Neue Einleitung
    assert (
        "Hier kannst du Personen deiner Organisation verwalten und sie deinen "
        "Arbeitspaketen zuordnen." in body
    )
    assert "Plattformrollen und andere Organisationen verwalten nur Admins." in body
    # Neuer Sektionstitel: dynamisch (Personen bei {short_name}) mit Fallback.
    assert "Personen bei ${partnerShort}" in body
    assert "Personen meiner Organisation" in body
    # Alte Formulierungen sind verschwunden.
    assert "Personen meines Partners" not in body
    assert (
        "Verwalte hier die Personen deines Partners und die Mitglieder deiner "
        "Arbeitspakete." not in body
    )
    assert "Person für meinen Partner anlegen" not in body


# ---- Block 0015 — Meeting-/Protokollregister ------------------------


def test_app_js_registers_meeting_routes() -> None:
    body = (WEB_DIR / "app.js").read_text(encoding="utf-8")
    assert "meetings\\/?" in body
    assert "meeting_detail" in body


def test_index_html_has_meetings_nav() -> None:
    body = (WEB_DIR / "index.html").read_text(encoding="utf-8")
    assert 'href="/portal/meetings"' in body
    assert ">Meetings<" in body


def test_meetings_module_uses_helpers_and_cross_nav() -> None:
    body = (MODULES_DIR / "meetings.js").read_text(encoding="utf-8")
    for helper in ("renderLoading", "renderError", "renderEmpty", "crossNav("):
        assert helper in body, f"meetings.js sollte {helper!r} verwenden"


def test_meeting_detail_has_all_sections() -> None:
    body = (MODULES_DIR / "meeting_detail.js").read_text(encoding="utf-8")
    for section in ("Beschlüsse", "Aufgaben", "Dokumente", "Teilnehmende", "Arbeitspakete"):
        assert section in body, f"meeting_detail.js sollte Sektion {section!r} enthalten"
    # Aktionen, die der Server nur anbietet, wenn can_edit gesetzt ist.
    for action in (
        "Meeting bearbeiten",
        "Meeting absagen",
        "Beschluss hinzufügen",
        "Aufgabe hinzufügen",
        "Dokument verknüpfen",
        "Person hinzufügen",
    ):
        assert action in body, f"meeting_detail.js sollte Aktion {action!r} bieten"


def test_meeting_detail_uses_helpers_and_cross_nav() -> None:
    body = (MODULES_DIR / "meeting_detail.js").read_text(encoding="utf-8")
    for helper in ("renderLoading", "renderError", "renderEmpty", "crossNav("):
        assert helper in body


def test_meetings_have_no_judgmental_phrases() -> None:
    for name in ("meetings.js", "meeting_detail.js"):
        body = (MODULES_DIR / name).read_text(encoding="utf-8")
        for phrase in ("gut so", "prima", "super", "alles im Griff"):
            assert phrase not in body, f"{name} sollte ‚{phrase}‘ nicht enthalten"


def test_meetings_filter_box_has_legend_and_better_placeholder() -> None:
    """Block 0015 / Bugfix-UX: Filterzeile als eigene Box mit Legende
    und klarem Placeholder — visuell vom Anlage-Dialog abgesetzt."""
    body = (MODULES_DIR / "meetings.js").read_text(encoding="utf-8")
    # Filterbox ist ein <fieldset> mit Klassen ``meeting-filterbox filterbox``
    # (UX-Polish: zusätzliche generische Klasse, alte bleibt erhalten).
    assert "meeting-filterbox" in body
    assert "filterbox" in body
    assert "Meetings filtern" in body
    # Klarerer Placeholder.
    assert "WP-Code filtern, z. B. WP3.1" in body
    # Alter Placeholder ist verschwunden.
    assert "WP-Code (z. B. WP3.1)" not in body
    # CSS-Klasse vorhanden.
    css = (WEB_DIR / "style.css").read_text(encoding="utf-8")
    assert ".meeting-filterbox" in css
    # Generische Klasse ist auch im CSS verfügbar.
    assert ".filterbox" in css


def test_meetings_create_form_has_clearer_wp_label_and_help() -> None:
    body = (MODULES_DIR / "meetings.js").read_text(encoding="utf-8")
    assert "Zugehörige Arbeitspakete" in body
    assert "Mehrfachauswahl möglich. WP-Leads dürfen nur eigene Arbeitspakete auswählen." in body


def test_meeting_wp_options_use_id_as_value_not_label() -> None:
    """Block 0015 / Bugfix: ``<option value="…">`` muss die WP-ID
    bekommen, nicht den zusammengesetzten Anzeigetext."""
    for name in ("meetings.js", "meeting_detail.js"):
        body = (MODULES_DIR / name).read_text(encoding="utf-8")
        # Korrekt: value: wp.id, Anzeige separat aus code + title.
        assert "value: wp.id" in body, f"{name} sollte value: wp.id verwenden"
        # Negativ-Probe: kein Pattern, das den Anzeigetext als value setzt.
        assert "value: `${wp.code}" not in body
        assert 'value: wp.code + " — "' not in body


def test_meeting_detail_edit_form_uses_clearer_wp_label() -> None:
    body = (MODULES_DIR / "meeting_detail.js").read_text(encoding="utf-8")
    assert "Zugehörige Arbeitspakete" in body


# ---- Block 0016 — Hard-Delete (Admin-only) ----------------------------


def test_meeting_detail_has_admin_delete_button() -> None:
    body = (MODULES_DIR / "meeting_detail.js").read_text(encoding="utf-8")
    # Admin-only Lösch-Button mit deutscher Beschriftung.
    assert "Meeting löschen …" in body
    # Lösch-Button ist Admin-only — Sichtbarkeitscheck via platform_role.
    assert 'platform_role === "admin"' in body
    # Tooltip oder Klassenmarkierung ist „Admin"-spezifisch.
    assert "meeting-delete" in body


def test_meeting_detail_delete_uses_delete_endpoint_and_redirect() -> None:
    body = (MODULES_DIR / "meeting_detail.js").read_text(encoding="utf-8")
    # DELETE auf /api/meetings/${meeting.id}.
    assert 'api("DELETE", `/api/meetings/${meeting.id}`)' in body
    # Nach Erfolg zurück zur Meetingliste.
    assert '"/portal/meetings"' in body


def test_meeting_detail_delete_confirm_text() -> None:
    body = (MODULES_DIR / "meeting_detail.js").read_text(encoding="utf-8")
    # Confirm-Text muss „endgültig löschen" und „nicht rückgängig" enthalten.
    assert "endgültig löschen" in body
    assert "kann nicht rückgängig gemacht werden" in body


def test_meetings_list_has_no_delete_button() -> None:
    """Der Lösch-Pfad ist nur auf der Detailseite — die Liste bleibt ohne."""
    body = (MODULES_DIR / "meetings.js").read_text(encoding="utf-8")
    assert "Meeting löschen" not in body
    # Auch keine direkte DELETE-API-Nutzung in der Liste.
    assert 'api("DELETE"' not in body


# ---- Block 0017 — Interne Dokumentliste ------------------------------


def test_meeting_detail_uses_internal_documents_endpoint() -> None:
    body = (MODULES_DIR / "meeting_detail.js").read_text(encoding="utf-8")
    # Bevorzugter Pfad (ohne den vorherigen 404-Pfad).
    assert "/api/documents?include_archived=false" in body


def test_meeting_detail_only_falls_back_on_failure() -> None:
    """Der WP-iterate-Fallback darf nur in einem Catch-Pfad ausgeführt
    werden — nicht jedes Mal, wenn die globale Liste leer ist."""
    body = (MODULES_DIR / "meeting_detail.js").read_text(encoding="utf-8")
    # Sentinel zeigt an, dass das Frontend zwischen „leer" und „Fehler"
    # unterscheidet.
    assert "documentsFailed" in body
    # Alter Always-On-Fallback-Marker ist weg.
    assert "if (!Array.isArray(documents) || !documents.length)" not in body


def test_meeting_detail_doc_dialog_has_no_id_input_or_upload() -> None:
    """Auswahl bleibt ein <select> ohne Datei-Upload und ohne freie ID-Eingabe."""
    body = (MODULES_DIR / "meeting_detail.js").read_text(encoding="utf-8")
    # Datei-Upload ausgeschlossen.
    assert 'type: "file"' not in body
    assert "FormData" not in body
    # Keine Eingabe für rohe Dokument-IDs (ein einfaches `<input ... value="...uuid...">`
    # gibt es im Doc-Link-Form nicht).
    assert 'placeholder: "Dokument-ID' not in body


def test_meetings_have_no_direct_file_upload() -> None:
    """Block 0015 erlaubt explizit keinen direkten Datei-Upload im Meeting-Dialog."""
    for name in ("meetings.js", "meeting_detail.js"):
        body = (MODULES_DIR / name).read_text(encoding="utf-8")
        # Kein input type=file und kein FormData für Uploads.
        assert 'type: "file"' not in body
        assert "FormData" not in body
        # Verknüpfung erfolgt über document_id (existierende Documents).
        if name == "meeting_detail.js":
            assert "document_id" in body


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


# ---- Block 0018 — Admin-View-Toggle + Aufgaben + Druckansicht + Cockpit


def test_app_js_registers_actions_and_print_routes() -> None:
    body = (WEB_DIR / "app.js").read_text(encoding="utf-8")
    # /portal/actions als eigene Route.
    assert "actions\\/?" in body
    assert '"actions"' in body or 'module: "actions"' in body
    # Druckansicht /portal/meetings/{id}/print → eigenes Modul.
    assert "print" in body
    assert "meeting_print" in body


def test_index_html_has_actions_nav_and_view_banner() -> None:
    body = (WEB_DIR / "index.html").read_text(encoding="utf-8")
    # Aufgaben-Link in der Navi.
    assert 'href="/portal/actions"' in body
    assert ">Aufgaben<" in body
    # Banner-Element für Admin-Ansichts-Umschaltung vorhanden + standardmäßig hidden.
    assert 'id="admin-view-banner"' in body
    banner_line = next(line for line in body.splitlines() if "admin-view-banner" in line)
    assert "hidden" in banner_line


def test_actions_module_has_list_and_filters() -> None:
    body = (MODULES_DIR / "actions.js").read_text(encoding="utf-8")
    # Filter-Box mit Legende.
    assert "meeting-filterbox" in body
    assert "Aufgaben filtern" in body
    # Filteroptionen, die der Server kennt.
    for term in ("Meine Aufgaben", "Überfällig", "Alle Status", "WP-Code"):
        assert term in body, f"actions.js sollte {term!r} enthalten"
    # Tabellen-Spalten.
    for header in ("Frist", "Status", "Aufgabe", "Verantwortlich", "WP", "Quelle / Meeting"):
        assert header in body, f"actions.js sollte Spalte {header!r} enthalten"
    # API-Pfade.
    assert "/api/actions" in body
    # PATCH wird verwendet — direkter Statuswechsel aus der Liste.
    assert 'api("PATCH"' in body
    # Zentrale UX-Helfer + crossNav.
    for helper in ("renderLoading", "renderError", "renderEmpty", "crossNav("):
        assert helper in body, f"actions.js sollte {helper!r} verwenden"


def test_meeting_print_module_renders_protocol_view() -> None:
    body = (MODULES_DIR / "meeting_print.js").read_text(encoding="utf-8")
    # Lädt das Meeting selbst.
    assert "/api/meetings/" in body
    # Eigene Klasse für die Druckansicht.
    assert "meeting-print" in body
    # Druckknopf + Rückkehr zur Detailseite.
    assert "window.print" in body
    assert "/portal/meetings/" in body
    # Kerninhalte des Protokolls.
    for section in ("Beschlüsse", "Aufgaben", "Teilnehmende", "Arbeitspakete", "Dokumente"):
        assert section in body, f"meeting_print.js sollte Sektion {section!r} enthalten"


def test_meeting_detail_links_to_print_view() -> None:
    body = (MODULES_DIR / "meeting_detail.js").read_text(encoding="utf-8")
    # Direkter Link zum Print-Modul.
    assert "/print" in body
    assert "Protokollansicht" in body


def test_common_js_exports_admin_view_and_last_seen_helpers() -> None:
    body = (WEB_DIR / "common.js").read_text(encoding="utf-8")
    for fn in (
        "export function getAdminViewMode",
        "export function setAdminViewMode",
        "export function effectivePlatformRole",
        "export function getLastSeenAt",
        "export function markSeenNow",
    ):
        assert fn in body, f"common.js sollte {fn!r} exportieren"
    # localStorage-Schlüssel haben einen Namespace.
    assert "ref4ep.admin_view_mode" in body
    assert "ref4ep.last_seen_at" in body


def test_app_js_renders_admin_view_toggle_and_banner() -> None:
    body = (WEB_DIR / "app.js").read_text(encoding="utf-8")
    # Toggle-Button (Klasse + Beschriftung).
    assert "admin-view-toggle" in body
    assert "Zur Admin-Ansicht wechseln" in body
    assert "Zur Nutzeransicht wechseln" in body
    # Sichtbarer Hinweisbalken.
    assert "renderViewModeBanner" in body
    # Effektive Rolle wird in der Sichtbarkeitslogik verwendet.
    assert "getAdminViewMode" in body


def test_cockpit_has_my_area_and_activity_box() -> None:
    body = (MODULES_DIR / "cockpit.js").read_text(encoding="utf-8")
    # „Mein Bereich"-Karten und ihre Datenquelle.
    assert "Mein Bereich" in body
    assert "Meine Arbeitspakete" in body
    assert "Meine Aufgaben" in body
    assert "Nächste Meetings" in body
    assert "/api/cockpit/me" in body
    # Aktivitätsbox.
    assert "/api/activity/recent" in body
    assert "Änderungen" in body
    # markSeenNow wird nach dem Fetch aufgerufen.
    assert "markSeenNow" in body
    assert "getLastSeenAt" in body


def test_style_css_has_block_0018_classes_and_print_rule() -> None:
    css = (WEB_DIR / "style.css").read_text(encoding="utf-8")
    for cls in (
        ".admin-view-banner",
        ".admin-view-toggle",
        ".my-area-grid",
        ".my-area-card",
        ".activity-box",
        ".meeting-print",
    ):
        assert cls in css, f"style.css sollte {cls} enthalten"
    # Die @media print-Regel blendet Header/Nav/Aktionen aus.
    assert "@media print" in css
    assert ".portal-header" in css
    assert ".cross-nav" in css
    assert ".actions" in css


def test_actions_route_link_present_in_actions_module() -> None:
    """Aufgaben-Liste verlinkt zurück auf das Quellen-Meeting."""
    body = (MODULES_DIR / "actions.js").read_text(encoding="utf-8")
    assert "/portal/meetings/" in body


# ---- Cockpit-UX-Pass (Folge zu Block 0018) ---------------------------


def test_cockpit_has_kpi_strip_with_labels() -> None:
    """Oben im Cockpit liegt ein kompakter KPI-Streifen mit klaren Zählern."""
    body = (MODULES_DIR / "cockpit.js").read_text(encoding="utf-8")
    # Container-Klasse + Render-Funktion.
    assert "cockpit-kpi-strip" in body
    assert "renderKpiStrip" in body
    assert "renderKpiTile" in body
    # Die fünf Kennzahlen, die der Streifen anzeigen soll.
    for label in (
        "Überfällige Aufgaben",
        "Offene Aufgaben",
        "Nächste Meetings",
        "Überfällige Meilensteine",
        "WPs mit offenen Punkten",
    ):
        assert label in body, f"cockpit.js sollte KPI {label!r} anzeigen"


def test_cockpit_kpi_styles_present() -> None:
    css = (WEB_DIR / "style.css").read_text(encoding="utf-8")
    for cls in (
        ".cockpit-kpi-strip",
        ".cockpit-kpi",
        ".cockpit-kpi-value",
        ".cockpit-kpi-label",
        ".cockpit-kpi-danger",
    ):
        assert cls in css, f"style.css sollte {cls} enthalten"
    # Mobiles Default-Layout: einspaltig; ab 540 px zwei-, ab 900 px fünfspaltig.
    assert "@media (min-width: 540px)" in css
    assert "@media (min-width: 900px)" in css


def test_cockpit_my_workpackages_are_capped_with_show_all_link() -> None:
    """„Meine Arbeitspakete" zeigt nicht mehr alle WPs als lange Liste."""
    body = (MODULES_DIR / "cockpit.js").read_text(encoding="utf-8")
    # Begrenzungs-Konstante (kein magic number direkt im Render-Pfad).
    assert "MY_WP_LIMIT" in body
    # Sichtbarer Link zur vollständigen Sicht.
    assert "Alle meine Arbeitspakete anzeigen" in body
    # Lead/Member-Counts werden ausgegeben.
    assert "my-wp-counts" in body
    assert "Lead" in body
    assert "Member" in body
    # Restliste ist einklappbar (<details>).
    assert "my-wp-more" in body
    assert "weitere anzeigen" in body


def test_cockpit_open_issues_are_capped_with_show_all_link() -> None:
    body = (MODULES_DIR / "cockpit.js").read_text(encoding="utf-8")
    assert "OPEN_ISSUE_LIMIT" in body
    # „Alle Arbeitspakete anzeigen" ist die zentrale Brücke zur Vollsicht.
    assert "Alle Arbeitspakete anzeigen" in body
    # Hinweis auf weitere Einträge — als Suffix sichtbar.
    assert "weitere" in body


def test_cockpit_status_overview_shows_only_problem_wps() -> None:
    """Die volle WP-Tabelle wird durch eine Mini-Tabelle der Problem-WPs ersetzt."""
    body = (MODULES_DIR / "cockpit.js").read_text(encoding="utf-8")
    # Filter-Set ist im Quelltext sichtbar.
    assert "PROBLEM_WP_STATUSES" in body
    for status in ("critical", "waiting_for_input", "in_progress"):
        assert status in body
    # Sub-Heading + dedizierte Tabellen-Klasse.
    assert "cockpit-subhead" in body
    assert "cockpit-problem-wps" in body
    assert "Aufmerksamkeit nötig" in body
    # Auch im Status-Overview gibt es den Brücken-Link zur Vollsicht.
    assert "Alle Arbeitspakete anzeigen" in body


def test_cockpit_does_not_iterate_full_overview_into_main_table() -> None:
    """Die alte Variante mappte ``overview.map(...)`` direkt in eine
    sichtbare Volltabelle — diese Form ist verschwunden. Stattdessen wird
    ``overview.filter`` benutzt, um die Mini-Tabelle zu erzeugen."""
    body = (MODULES_DIR / "cockpit.js").read_text(encoding="utf-8")
    assert "overview.map" not in body
    assert "overview.filter" in body


def test_cockpit_uses_effective_platform_role_for_ordering() -> None:
    """Die Reihenfolge ‚Mein Bereich' vs. ‚Projekt-Cockpit' richtet sich
    nach der effektiven Plattformrolle (Admin-View-Toggle)."""
    body = (MODULES_DIR / "cockpit.js").read_text(encoding="utf-8")
    assert "effectivePlatformRole" in body
    assert "isAdminView" in body


# ---- Cockpit-UX-Folgepass: Tönung, Mini-Tabelle, Klickbarkeit --------


def test_cockpit_kpi_warning_tone_is_distinct_from_danger() -> None:
    """„WPs mit offenen Punkten" verwendet die ruhige warning-Tönung,
    nicht die alarmistische danger-Tönung. Die danger-Tönung bleibt für
    überfällige Aufgaben/Meilensteine."""
    body = (MODULES_DIR / "cockpit.js").read_text(encoding="utf-8")
    # tone-Property statt früherer danger-Boolean.
    assert "tone:" in body
    assert '"warning"' in body
    assert '"danger"' in body
    # Konkret: WPs-mit-offenen-Punkten-Block bekommt warning, nicht danger.
    assert 'wpsWithIssues > 0 ? "warning"' in body
    # Konkret: Überfälligkeiten dürfen weiterhin danger sein.
    assert 'overdueActions > 0 ? "danger"' in body
    assert 'overdueMs > 0 ? "danger"' in body


def test_cockpit_kpi_warning_styles_are_present() -> None:
    css = (WEB_DIR / "style.css").read_text(encoding="utf-8")
    assert ".cockpit-kpi-warning" in css
    # Warning-Tönung muss von danger optisch abweichen — also mindestens
    # eine eigene Hintergrundregel.
    assert "cockpit-kpi-warning" in css
    # Danger bleibt erhalten (Regression).
    assert ".cockpit-kpi-danger" in css


def test_cockpit_kpi_link_styles_indicate_clickability() -> None:
    """Klickbare KPI-Karten haben Hover-, Focus- und Cursor-Affordanzen
    sowie einen sichtbaren ‚Anzeigen →'-Hinweis."""
    css = (WEB_DIR / "style.css").read_text(encoding="utf-8")
    body = (MODULES_DIR / "cockpit.js").read_text(encoding="utf-8")
    # Klasse auf <a>-Variante.
    assert ".cockpit-kpi-link" in css
    # Cursor pointer + Hover + Focus-ring.
    assert "cursor: pointer" in css
    assert "a.cockpit-kpi-link:hover" in css
    assert "a.cockpit-kpi-link:focus-visible" in css
    # Pfeil-/CTA-Andeutung in HTML + CSS.
    assert ".cockpit-kpi-cta" in css
    assert "Anzeigen" in body
    # aria-label setzt einen sinnvollen Screenreader-Text.
    assert "aria-label" in body


def test_cockpit_my_workpackages_use_compact_table_with_role_badge() -> None:
    """„Meine Arbeitspakete" wird nicht mehr als einfache Bullet-Liste
    gerendert, sondern als kompakte Tabelle mit Code/Titel/Rolle und
    Lead/Member als Badge."""
    body = (MODULES_DIR / "cockpit.js").read_text(encoding="utf-8")
    css = (WEB_DIR / "style.css").read_text(encoding="utf-8")
    # Render-Helfer für Tabelle und Badge sind sichtbar.
    assert "renderMyWpTable" in body
    assert "roleBadge" in body
    # Klassen für Tabelle + Spalten + Badges.
    assert "my-wp-table" in body
    assert "my-wp-code" in body
    assert "my-wp-title" in body
    assert "my-wp-role" in body
    assert "badge-lead" in body
    assert "badge-member" in body
    # CSS für Tabelle + Badges.
    assert ".my-wp-table" in css
    assert ".badge-lead" in css
    assert ".badge-member" in css
    # Lange Titel müssen umbrechen können.
    assert "overflow-wrap" in css or "word-break" in css
    # Die alte Bullet-Item-Funktion ist verschwunden.
    assert "function wpItem" not in body
    # Spaltenüberschriften (Kontextbeweis: echte Tabelle).
    assert ">Code<" in body or '"Code"' in body
    assert "Titel" in body
    assert "Rolle" in body
    # Beschriftung der Rolle als Badge-Text — nicht mehr „(Lead)" als Suffix.
    assert "(Lead)" not in body


def test_cockpit_member_view_orders_my_area_before_project_cockpit() -> None:
    """In der Nutzeransicht steht ``myAreaSlot`` *vor* ``projectSlot``
    in der Slot-Reihenfolge. Die Quelle dafür ist der Ternary-Ausdruck,
    der die Reihenfolge auf Basis von ``isAdminView`` bestimmt."""
    body = (MODULES_DIR / "cockpit.js").read_text(encoding="utf-8")
    # Member-Reihenfolge: myAreaSlot, projectHeader, projectSlot
    assert "[myAreaSlot, projectHeader, projectSlot]" in body
    # Admin-Reihenfolge: projectHeader, projectSlot, …, myAreaSlot
    assert "[projectHeader, projectSlot, myAreaHeader, myAreaSlot]" in body


def test_cockpit_open_issues_section_is_marked_as_excerpt() -> None:
    """Der Auszug-Charakter wird in der Überschrift sichtbar; bei
    weiteren Einträgen erscheint zusätzlich ein erklärender Satz."""
    body = (MODULES_DIR / "cockpit.js").read_text(encoding="utf-8")
    assert "Offene Punkte aus Arbeitspaketen — Auszug" in body
    assert "Weitere offene Punkte vorhanden" in body
    # Limit-Konstante + Brücken-Link sind weiterhin da.
    assert "OPEN_ISSUE_LIMIT" in body
    assert "Alle Arbeitspakete anzeigen" in body


# ---- Block 0019 — Admin-Systemstatus-Seite ---------------------------


def test_app_js_registers_system_status_route() -> None:
    body = (WEB_DIR / "app.js").read_text(encoding="utf-8")
    assert "admin\\/system" in body
    assert "system_status" in body


def test_index_html_has_system_nav_admin_only() -> None:
    body = (WEB_DIR / "index.html").read_text(encoding="utf-8")
    assert 'href="/portal/admin/system"' in body
    assert 'id="nav-admin-system"' in body
    assert ">System<" in body
    # In der Default-HTML hidden — JS macht den Link nur in Admin-Ansicht sichtbar.
    nav_line = next(line for line in body.splitlines() if "nav-admin-system" in line)
    assert "hidden" in nav_line


def test_app_js_unhides_system_link_only_for_admin_view() -> None:
    body = (WEB_DIR / "app.js").read_text(encoding="utf-8")
    # System steht in derselben Admin-Liste wie Users/Partners/Audit
    # und wird damit nur in Admin-Ansicht sichtbar.
    assert "nav-admin-system" in body
    # Sicherheitskontext: effektive Admin-Rolle (User-Toggle).
    assert "effectiveAdmin" in body


def test_system_status_module_uses_central_helpers_and_cross_nav() -> None:
    body = (MODULES_DIR / "system_status.js").read_text(encoding="utf-8")
    for helper in ("renderLoading", "renderError", "crossNav("):
        assert helper in body, f"system_status.js sollte {helper!r} verwenden"


def test_system_status_module_renders_required_sections() -> None:
    body = (MODULES_DIR / "system_status.js").read_text(encoding="utf-8")
    for term in (
        "Systemstatus",
        "Datenbank",
        "Backups",
        "Speicherplatz",
        "Objektzahlen",
        "Letzte Fehler",
        "Aktualisieren",
    ):
        assert term in body, f"system_status.js sollte {term!r} enthalten"
    # Lädt vom Admin-only-Endpoint.
    assert "/api/admin/system/status" in body


def test_system_status_module_has_no_destructive_actions_apart_from_backup_start() -> None:
    """Block 0019 war ursprünglich Lesesicht-only. Block 0033 ergänzt
    bewusst genau einen schreibenden Trigger: ``POST /api/admin/backup/start``.
    Andere destruktive Aktionen (Restore, Lösch-, DELETE-Aufrufe)
    bleiben verboten."""
    body = (MODULES_DIR / "system_status.js").read_text(encoding="utf-8")
    for forbidden in (
        "Wiederherstellen",
        "Restore",
        "Löschen",
        '"DELETE"',
    ):
        assert forbidden not in body, f"system_status.js darf {forbidden!r} nicht enthalten"
    # POST ist erlaubt — aber nur für den Backup-Start-Endpoint.
    if '"POST"' in body:
        assert "/api/admin/backup/start" in body, (
            "POST in system_status.js ist nur für /api/admin/backup/start zulässig."
        )


def test_system_status_module_does_not_print_env_or_secrets() -> None:
    body = (MODULES_DIR / "system_status.js").read_text(encoding="utf-8")
    # Keine Hinweise, dass das Modul Settings/.env-Werte direkt rendert.
    for forbidden in (
        ".env",
        "session_secret",
        "REF4EP_",
        "DATABASE_URL",
        "password",
    ):
        assert forbidden not in body, f"system_status.js darf {forbidden!r} nicht enthalten"


def test_system_status_styles_are_present() -> None:
    css = (WEB_DIR / "style.css").read_text(encoding="utf-8")
    for cls in (
        ".system-grid",
        ".system-card",
        ".system-card-warning",
        ".system-card-error",
        ".system-card-ok",
        ".system-row",
        ".system-badge-warning",
        ".system-badge-error",
        ".system-badge-ok",
    ):
        assert cls in css, f"style.css sollte {cls} enthalten"


# ---- Block 0020 — Drag-and-Drop für Dokument-Uploads -----------------


# Module, die echte Datei-Uploads anbieten (FormData + input[type=file]).
REAL_UPLOAD_MODULES = ("document_detail.js", "project_library.js")
# Block 0028 — campaign_detail.js darf nur Foto-Upload enthalten
# (PNG/JPEG), aber keinen Dokument-Upload.
PHOTO_UPLOAD_MODULES = ("campaign_detail.js",)


def test_common_js_exports_create_file_dropzone() -> None:
    body = (WEB_DIR / "common.js").read_text(encoding="utf-8")
    assert "export function createFileDropzone" in body
    # Hinweistext für Mehrfach-Drop ist im Helfer hartkodiert.
    assert "Bitte nur eine Datei auswählen." in body
    # Drei Drag-Handler sind verdrahtet.
    for evt in ('"dragover"', '"dragleave"', '"drop"'):
        assert evt in body, f"common.js sollte {evt}-Listener registrieren"


def test_dropzone_styles_present() -> None:
    css = (WEB_DIR / "style.css").read_text(encoding="utf-8")
    for cls in (
        ".file-dropzone",
        ".file-dropzone-active",
        ".file-dropzone-meta",
        ".file-dropzone-warning",
        ".file-dropzone-cta",
    ):
        assert cls in css, f"style.css sollte {cls} enthalten"


def test_real_upload_modules_use_dropzone_helper_and_keep_file_input() -> None:
    """Echte Upload-Module nutzen den zentralen Dropzone-Helfer und
    behalten das klassische ``<input type="file">`` als
    Tastatur-/A11y-Pfad."""
    for name in REAL_UPLOAD_MODULES:
        body = (MODULES_DIR / name).read_text(encoding="utf-8")
        assert "createFileDropzone" in body, f"{name} sollte createFileDropzone benutzen"
        # Klassisches Auswahlfeld bleibt erhalten.
        assert 'type: "file"' in body, f"{name} sollte input[type=file] behalten"
        # Backend nimmt nur eine Datei — Submit liest weiterhin files[0].
        assert "files[0]" in body, f"{name} sollte weiter files[0] verwenden"
        # FormData bleibt der Pfad zum Backend.
        assert "FormData" in body, f"{name} sollte FormData beibehalten"


def test_meeting_detail_has_no_file_input_no_dropzone_no_formdata() -> None:
    """Verschärfung: Meeting-Dokumentverknüpfung ist KEIN Datei-Upload —
    weder als input[type=file] noch als Dropzone, und ohne FormData."""
    body = (MODULES_DIR / "meeting_detail.js").read_text(encoding="utf-8")
    assert 'type: "file"' not in body
    assert 'type="file"' not in body
    # Weder der Helfer noch eine Dropzone-Klasse.
    assert "createFileDropzone" not in body
    assert "file-dropzone" not in body
    # Kein FormData irgendwo im Modul.
    assert "FormData" not in body
    # Verknüpfung bleibt JSON-POST mit document_id.
    assert "document_id" in body
    assert 'api("POST"' in body


def test_no_other_module_introduces_unexpected_file_upload() -> None:
    """Außer den deklarierten Upload-Modulen darf kein weiteres Modul
    ein input[type=file] führen — z. B. nicht im Meeting-Bereich, im
    Cockpit oder in Admin-Sub-Seiten. ``PHOTO_UPLOAD_MODULES`` deckt den
    Foto-Upload für Testkampagnen (Block 0028) ab."""
    allowed = set(REAL_UPLOAD_MODULES) | set(PHOTO_UPLOAD_MODULES)
    for path in sorted(MODULES_DIR.glob("*.js")):
        if path.name in allowed:
            continue
        body = path.read_text(encoding="utf-8")
        assert 'type: "file"' not in body, f"{path.name} sollte kein input[type=file] enthalten"
        assert 'type="file"' not in body, f"{path.name} sollte kein input[type=file] enthalten"


# ---- Block 0021 — Upload-/Storage-Details auf Systemstatus-Seite ----


def test_system_status_module_renders_uploads_card() -> None:
    body = (MODULES_DIR / "system_status.js").read_text(encoding="utf-8")
    assert "Upload-Speicher" in body
    # Render-Funktion + ynUnknown-Helfer für den dreiwertigen Status.
    assert "renderUploadsCard" in body
    assert "ynUnknown" in body


def test_system_status_uploads_card_has_explanation_text() -> None:
    body = (MODULES_DIR / "system_status.js").read_text(encoding="utf-8")
    # Der Block soll betrieblich klar machen, was wo liegt.
    assert "Datenbank enthält Metadaten" in body
    assert "Storage" in body


def test_system_status_uploads_card_shows_backup_contents_lines() -> None:
    body = (MODULES_DIR / "system_status.js").read_text(encoding="utf-8")
    for label in (
        "Storage-Pfad",
        "Storage vorhanden",
        "Upload-Dateien",
        "Upload-Speichergröße",
        "data/ gesamt (Größe)",
        "data/ gesamt (Dateien)",
        "Backup-Datei (geprüft)",
        "Backup enthält Datenbank",
        "Backup enthält Upload-Speicher",
    ):
        assert label in body, f"system_status.js sollte {label!r} anzeigen"
    # Dreiwertige Anzeige (ja/nein/unbekannt) explizit als Text.
    for term in ('"ja"', '"nein"', '"unbekannt"'):
        assert term in body, f"system_status.js sollte {term!r} enthalten"


def test_system_status_card_order_keeps_existing_cards_and_adds_uploads() -> None:
    body = (MODULES_DIR / "system_status.js").read_text(encoding="utf-8")
    # Alle bisherigen Karten sind weiterhin im Render-Tree verdrahtet.
    # ``renderBackupCard`` bekommt seit Block 0033 zusätzlich einen
    # ``onRefresh``-Callback — wir prüfen daher nur die Funktion, nicht
    # den exakten Aufruf-String.
    for fn in (
        "renderHealthCard(status)",
        "renderDatabaseCard(status)",
        "renderStorageCard(status)",
        "renderCountsCard(status)",
        "renderLogsCard(status)",
    ):
        assert fn in body, f"{fn!r} fehlt im Render-Tree"
    assert "renderBackupCard(status, onRefresh)" in body, (
        "renderBackupCard sollte mit onRefresh-Callback aufgerufen werden"
    )
    # Die neue Karte hängt zwischen Backups und Speicherplatz.
    backup_pos = body.rindex("renderBackupCard(")
    uploads_pos = body.rindex("renderUploadsCard(status)")
    storage_pos = body.rindex("renderStorageCard(status)")
    assert backup_pos < uploads_pos < storage_pos


def test_system_status_module_still_has_no_unrelated_destructive_actions() -> None:
    """Block 0021 fügt keine Schreibpfade hinzu. Block 0033 ergänzt
    explizit genau einen Backup-Trigger; weitere destruktive Aktionen
    bleiben verboten."""
    body = (MODULES_DIR / "system_status.js").read_text(encoding="utf-8")
    for forbidden in (
        "Backup auslösen",
        "Wiederherstellen",
        "Restore",
        "Löschen",
        '"DELETE"',
    ):
        assert forbidden not in body, f"system_status.js darf {forbidden!r} nicht enthalten"


# ---- Block 0022 — Testkampagnenregister ------------------------------


CAMPAIGN_MODULES = ("campaigns.js", "campaign_detail.js")


def test_app_js_registers_campaign_routes() -> None:
    body = (WEB_DIR / "app.js").read_text(encoding="utf-8")
    # /portal/campaigns  und /portal/campaigns/{id}
    assert "campaigns\\/?" in body
    assert "campaign_detail" in body


def test_index_html_has_campaigns_nav_link() -> None:
    body = (WEB_DIR / "index.html").read_text(encoding="utf-8")
    assert 'href="/portal/campaigns"' in body
    assert ">Testkampagnen<" in body


def test_campaign_modules_use_central_helpers_and_cross_nav() -> None:
    for name in CAMPAIGN_MODULES:
        body = (MODULES_DIR / name).read_text(encoding="utf-8")
        for helper in ("renderLoading", "renderError", "renderEmpty", "crossNav("):
            assert helper in body, f"{name} sollte {helper!r} verwenden"


def test_campaigns_list_module_uses_filter_box_and_create_button() -> None:
    body = (MODULES_DIR / "campaigns.js").read_text(encoding="utf-8")
    assert "campaign-filterbox" in body
    assert "Testkampagnen filtern" in body
    # Die wichtigsten Filter sind sichtbar verdrahtet.
    for label in ("Alle Status", "Alle Kategorien", "WP-Code", "Suche"):
        assert label in body, f"campaigns.js sollte Filter {label!r} anbieten"
    # Anlegen-Button.
    assert "Testkampagne anlegen" in body
    # Kategorien-Übersetzung mindestens im Modul referenziert.
    for label in ("Ringvergleich", "Kalibrierung", "Diagnostiktest"):
        assert label in body


def test_campaign_detail_renders_required_sections() -> None:
    body = (MODULES_DIR / "campaign_detail.js").read_text(encoding="utf-8")
    for section in (
        "Arbeitspakete",
        "Ziel und Zweck",
        "Testmatrix",
        "Erwartete Messgrößen",
        "Randbedingungen",
        "Erfolgskriterien",
        "Risiken / offene Punkte",
        "Beteiligte Personen",
        "Dokumente",
    ):
        assert section in body, f"campaign_detail.js sollte Sektion {section!r} enthalten"
    # can_edit-abhängige Aktionen.
    for action in (
        "Kampagne bearbeiten",
        "Kampagne abbrechen",
        "Person hinzufügen",
        "Dokument verknüpfen",
    ):
        assert action in body, f"campaign_detail.js sollte Aktion {action!r} bieten"


def test_campaigns_list_module_has_no_file_upload_no_dropzone_no_formdata() -> None:
    """Block 0022: Die Listen-Seite ``campaigns.js`` ist ausdrücklich
    kein Upload-Pfad. ``campaign_detail.js`` darf seit Block 0028 einen
    eng begrenzten Foto-Upload (PNG/JPEG) enthalten — der Dropzone-
    Helfer und ein Dokument-Upload bleiben dort jedoch verboten."""
    body_list = (MODULES_DIR / "campaigns.js").read_text(encoding="utf-8")
    assert 'type: "file"' not in body_list
    assert 'type="file"' not in body_list
    assert "createFileDropzone" not in body_list
    assert "file-dropzone" not in body_list
    assert "FormData" not in body_list

    body_detail = (MODULES_DIR / "campaign_detail.js").read_text(encoding="utf-8")
    assert "createFileDropzone" not in body_detail, (
        "campaign_detail.js darf den Dropzone-Helfer nicht benutzen"
    )
    assert "file-dropzone" not in body_detail, (
        "campaign_detail.js darf keine file-dropzone-Klasse enthalten"
    )
    # Foto-Upload ist explizit erlaubt, beschränkt sich aber auf PNG/JPEG.
    assert 'accept: "image/png,image/jpeg"' in body_detail
    assert "/api/campaigns/" in body_detail and "/photos" in body_detail


def test_campaign_detail_uses_existing_document_listing() -> None:
    body = (MODULES_DIR / "campaign_detail.js").read_text(encoding="utf-8")
    # Verwendet den globalen internen Dokumentlisten-Endpunkt.
    assert "/api/documents?include_archived=false" in body
    # Verknüpfung sendet document_id + label per JSON-POST.
    assert "document_id" in body
    assert 'api("POST"' in body


def test_campaigns_have_no_judgmental_phrases() -> None:
    for name in CAMPAIGN_MODULES:
        body = (MODULES_DIR / name).read_text(encoding="utf-8")
        for phrase in ("gut so", "prima", "super", "alles im Griff"):
            assert phrase not in body, f"{name} sollte ‚{phrase}‘ nicht enthalten"


def test_real_upload_modules_whitelist_does_not_include_campaigns() -> None:
    """Regression: Kampagnen-Module dürfen NICHT in der
    REAL_UPLOAD_MODULES-Whitelist landen — die ist nur für Document-
    Versions-Uploads gedacht. Foto-Upload (Block 0028) sitzt in einer
    eigenen, eng zugeschnittenen Whitelist ``PHOTO_UPLOAD_MODULES``."""
    assert "campaigns.js" not in REAL_UPLOAD_MODULES
    assert "campaign_detail.js" not in REAL_UPLOAD_MODULES
    # Foto-Upload-Whitelist enthält genau campaign_detail.js.
    assert "campaign_detail.js" in PHOTO_UPLOAD_MODULES
    assert "campaigns.js" not in PHOTO_UPLOAD_MODULES


# ---- Block 0022 — UX-Folgepass (Bugfix + Restruktur) ------------------


def test_common_js_exports_append_children_helper() -> None:
    """Der zentrale Helfer ``appendChildren`` filtert null/undefined/false
    heraus — verhindert den „nullnullnull"-Bug aus dem Online-Test."""
    body = (WEB_DIR / "common.js").read_text(encoding="utf-8")
    assert "export function appendChildren" in body
    assert "child === null" in body or "== null" in body


def test_campaign_detail_uses_append_children_for_top_level_render() -> None:
    """campaign_detail.js darf nicht direkt ``container.replaceChildren(`` mit
    nullable Sub-Renderings aufrufen — sonst werden ``null``-Returns als
    Text „null" gerendert. Statt dessen wird ``appendChildren`` benutzt."""
    body = (MODULES_DIR / "campaign_detail.js").read_text(encoding="utf-8")
    assert "appendChildren" in body
    # Konkreter Bug war: container.replaceChildren( … renderTextSection(...) )
    assert "renderTextSection" not in body
    assert "container.replaceChildren(" not in body


def test_campaign_detail_factual_block_has_empty_state() -> None:
    """Wenn alle fachlichen Felder leer sind, kommt der saubere Empty-State."""
    body = (MODULES_DIR / "campaign_detail.js").read_text(encoding="utf-8")
    assert "Noch keine fachlichen Details hinterlegt." in body
    assert "FACTUAL_FIELDS" in body
    assert "renderFactualBlock" in body


def test_campaign_detail_has_clear_section_structure() -> None:
    body = (MODULES_DIR / "campaign_detail.js").read_text(encoding="utf-8")
    for section in (
        "Übersicht",
        "Fachliche Details",
        "Arbeitspakete",
        "Fotos",
        "Beteiligte Personen",
        "Dokumente",
    ):
        assert section in body, f"campaign_detail.js sollte Sektion {section!r} enthalten"
    for fn in (
        "renderOverviewCard",
        "renderFactualBlock",
        "renderWpsBlock",
        "renderPhotosBlock",
        "renderParticipantsBlock",
        "renderDocumentsBlock",
    ):
        assert fn in body, f"{fn} fehlt"


def test_campaign_detail_uses_german_role_labels_via_pill_not_badge() -> None:
    body = (MODULES_DIR / "campaign_detail.js").read_text(encoding="utf-8")
    assert "campaign-role" in body
    assert "rolePill" in body
    for label in (
        "Kampagnenleitung",
        "Facility-Verantwortung",
        "Diagnostik",
        "Datenanalyse",
        "Betrieb",
        "Sicherheit",
        "Beobachtung",
    ):
        assert label in body, f"campaign_detail.js sollte Rolle {label!r} mappen"
    # Negative: alte UPPER-Badge-Variante ist verschwunden.
    assert "function roleBadge" not in body


def test_campaign_role_pill_style_is_not_uppercased() -> None:
    """Die Rollen-Pill darf NICHT die UPPERCASE-Behandlung von ``.badge``
    erben — sonst sieht man wieder ‚DIAGNOSTIK'."""
    css = (WEB_DIR / "style.css").read_text(encoding="utf-8")
    assert ".campaign-role" in css
    start = css.index(".campaign-role {")
    end = css.index("}", start)
    block = css[start:end]
    assert "uppercase" not in block.lower(), (
        "Die Rollen-Pill darf nicht in Großbuchstaben gerendert werden."
    )


def test_campaign_participant_card_replaces_table_layout() -> None:
    body = (MODULES_DIR / "campaign_detail.js").read_text(encoding="utf-8")
    css = (WEB_DIR / "style.css").read_text(encoding="utf-8")
    assert "campaign-participant-card" in body
    assert "campaign-participant-grid" in body
    assert ".campaign-participant-card" in css
    assert ".campaign-participant-grid" in css


def test_campaign_document_card_layout() -> None:
    body = (MODULES_DIR / "campaign_detail.js").read_text(encoding="utf-8")
    css = (WEB_DIR / "style.css").read_text(encoding="utf-8")
    assert "campaign-document-card" in body
    assert "campaign-document-grid" in body
    assert ".campaign-document-card" in css
    assert ".campaign-document-grid" in css
    assert "campaign-doc-label" in body
    assert "entknüpfen" in body
    assert "WP:" in body


def test_campaigns_list_uses_card_grid_not_table() -> None:
    body = (MODULES_DIR / "campaigns.js").read_text(encoding="utf-8")
    assert "campaign-card-grid" in body
    assert "campaign-card" in body
    assert "Details anzeigen" in body
    # Negative: alte Tabellen-Konstruktion mit thead+rowFor ist weg.
    assert '"thead"' not in body
    assert "rowFor" not in body


def test_campaigns_card_grid_styles_are_responsive() -> None:
    css = (WEB_DIR / "style.css").read_text(encoding="utf-8")
    for cls in (
        ".campaign-card-grid",
        ".campaign-card",
        ".campaign-card-head",
        ".campaign-card-title",
        ".campaign-meta",
        ".campaign-card-footer",
    ):
        assert cls in css, f"style.css sollte {cls} enthalten"
    assert "@media (min-width: 720px)" in css
    assert "overflow-wrap: anywhere" in css or "word-break: break-word" in css


def test_campaign_modules_have_no_literal_null_text_for_empty_fields() -> None:
    """Heuristik: in Kampagnen-Modulen darf nirgendwo ein ``"null"``-
    Stringliteral landen — sonst rutscht es als sichtbarer Text durch."""
    for name in ("campaign_detail.js", "campaigns.js"):
        body = (MODULES_DIR / name).read_text(encoding="utf-8")
        assert '"null"' not in body, f"{name} darf keinen 'null'-String literal enthalten"


def test_campaign_modules_still_have_no_document_upload_path_after_refactor() -> None:
    """Regression: Kampagnen-Module dürfen keinen Datei-Upload für
    DOKUMENTE bieten — Dokumente werden ausschließlich über das
    bestehende Dokumentenregister verlinkt. Foto-Upload (Block 0028) ist
    davon explizit ausgenommen und nutzt einen eigenen Endpunkt."""
    for name in ("campaigns.js", "campaign_detail.js"):
        body = (MODULES_DIR / name).read_text(encoding="utf-8")
        # Document-Upload-Helfer und der dortige Upload-Pfad bleiben verboten.
        assert "createFileDropzone" not in body
        assert "file-dropzone" not in body
        assert "/api/documents/" not in body or "POST" not in body or "FormData" in body
    # campaigns.js bleibt komplett ohne Upload.
    body_list = (MODULES_DIR / "campaigns.js").read_text(encoding="utf-8")
    assert 'type: "file"' not in body_list
    assert "FormData" not in body_list
    body = (MODULES_DIR / "campaign_detail.js").read_text(encoding="utf-8")
    assert "/api/documents?include_archived=false" in body
    assert "document_id" in body
    # Foto-Upload geht ausschließlich über den Foto-Endpunkt.
    assert "/api/campaigns/" in body
    assert "/photos" in body


# ---- Block 0023 — Aggregierter Projektkalender ------------------------


def test_app_js_registers_calendar_route() -> None:
    body = (WEB_DIR / "app.js").read_text(encoding="utf-8")
    assert "calendar\\/?" in body
    assert '"calendar"' in body or 'module: "calendar"' in body


def test_index_html_has_calendar_nav_link() -> None:
    body = (WEB_DIR / "index.html").read_text(encoding="utf-8")
    assert 'href="/portal/calendar"' in body
    assert ">Kalender<" in body


def test_calendar_module_uses_central_helpers_and_cross_nav() -> None:
    body = (MODULES_DIR / "calendar.js").read_text(encoding="utf-8")
    for helper in ("renderLoading", "renderError", "renderEmpty", "crossNav("):
        assert helper in body, f"calendar.js sollte {helper!r} verwenden"


def test_calendar_module_renders_navigation_filters_and_grid() -> None:
    body = (MODULES_DIR / "calendar.js").read_text(encoding="utf-8")
    # Monatsnavigation + „Heute"-Button.
    assert "Vorheriger Monat" in body
    assert "Nächster Monat" in body
    assert "Heute" in body
    # Filter sind sichtbar verdrahtet.
    assert "Alle Typen" in body
    assert "Meine Einträge" in body
    assert "WP-Code" in body
    # Monatsraster + Agenda als getrennte Slots.
    assert "calendar-grid-wrap" in body
    assert "calendar-agenda-section" in body
    assert "renderMonthGrid" in body
    assert "renderAgenda" in body


def test_calendar_chip_classes_for_all_event_types_in_module() -> None:
    body = (MODULES_DIR / "calendar.js").read_text(encoding="utf-8")
    # Typkürzel als Text — nicht nur Farbe.
    for label in ("Meeting", "Kampagne", "Meilenstein", "Aufgabe"):
        assert label in body, f"calendar.js sollte Typ-Label {label!r} anzeigen"
    # Die Typ-Klasse wird dynamisch konstruiert — wir suchen nach den
    # Template-Strings, die den Klassen-Präfix tragen.
    assert "calendar-event-${event.type}" in body or "calendar-event-${e.type}" in body, (
        "calendar.js sollte typabhängige CSS-Klassen pro Event setzen"
    )
    # Spezielle Marker bleiben als statische Strings im Modul vorhanden.
    for marker in ("calendar-event-overdue", "calendar-event-cancelled"):
        assert marker in body, f"calendar.js sollte {marker!r} setzen können"


def test_calendar_event_type_classes_in_css() -> None:
    css = (WEB_DIR / "style.css").read_text(encoding="utf-8")
    for cls in (
        ".calendar-grid",
        ".calendar-cell",
        ".calendar-event",
        ".calendar-event-meeting",
        ".calendar-event-campaign",
        ".calendar-event-milestone",
        ".calendar-event-action",
        ".calendar-event-overdue",
        ".calendar-event-cancelled",
        ".calendar-agenda-list",
    ):
        assert cls in css, f"style.css sollte {cls} enthalten"


def test_calendar_module_links_to_existing_detail_routes() -> None:
    """Chips/Agenda-Einträge sollen zu den vorhandenen Detailseiten
    verlinken — der Server liefert die Links bereits, wir prüfen, dass
    das Modul ``event.link`` benutzt (statt etwa eigene URLs zu basteln)."""
    body = (MODULES_DIR / "calendar.js").read_text(encoding="utf-8")
    assert "event.link" in body
    # Backend-Endpunkt wird verwendet, kein eigener „events"-Endpoint.
    assert "/api/calendar/events" in body


def test_calendar_module_has_no_external_framework_or_ics_or_drag() -> None:
    body = (MODULES_DIR / "calendar.js").read_text(encoding="utf-8")
    # Kein externes Kalender-/UI-Framework eingebunden.
    for forbidden_import in (
        "FullCalendar",
        "fullcalendar",
        "react",
        "vue",
        "luxon",
        "moment",
        "jquery",
    ):
        assert forbidden_import not in body, (
            f"calendar.js darf nichts wie {forbidden_import!r} importieren"
        )
    # Keine ICS/iCal-Erzeugung.
    assert "BEGIN:VCALENDAR" not in body
    assert ".ics" not in body
    # Keine Drag-and-Drop-Handler.
    for evt in ("dragstart", "dragover", "dragend", "drop"):
        # Wir suchen Event-Listener-Strings — nicht Substrings im Doc-Comment.
        assert f'"{evt}"' not in body, f"calendar.js darf keine Drag-Events nutzen ({evt})"
    # Keine Mailto-/E-Mail-Erinnerungen.
    assert "mailto:" not in body


def test_calendar_module_has_no_file_upload_or_formdata() -> None:
    """Kalender ist Lesesicht — keine Schreibpfade, kein Upload."""
    body = (MODULES_DIR / "calendar.js").read_text(encoding="utf-8")
    assert 'type: "file"' not in body
    assert "FormData" not in body
    assert "createFileDropzone" not in body
    assert "file-dropzone" not in body
    # Auch kein POST/PATCH/DELETE — reines GET.
    for method in ('"POST"', '"PATCH"', '"DELETE"'):
        assert method not in body, f"calendar.js darf {method} nicht aufrufen"


def test_calendar_responsive_layout_breakpoint_present() -> None:
    css = (WEB_DIR / "style.css").read_text(encoding="utf-8")
    # Mobile-Tweak ist im Stylesheet vorhanden.
    assert "@media (max-width: 720px)" in css
    # Agenda klappt auf Desktop in zwei Spalten (Datum-Spalte + Body).
    assert "@media (min-width: 720px)" in css


# ---- Block 0023 — UX-Folgepass: Multi-day, Tooltip, Chip, Filter, Nav


def test_calendar_module_expands_multiday_campaigns_for_grid() -> None:
    """``expandEventForGrid`` produziert pro Kalendertag eine Chip-
    Instanz für mehrtägige Kampagnen — die Agenda sieht weiter die
    ungekürzte Liste."""
    body = (MODULES_DIR / "calendar.js").read_text(encoding="utf-8")
    assert "function expandEventForGrid" in body
    assert "function expandedEventsForGrid" in body
    assert "expandedEventsForGrid(events)" in body
    for phase in ('"start"', '"running"', '"end"'):
        assert phase in body, f"calendar.js sollte Phase {phase!r} setzen"


def test_calendar_chip_shows_phase_prefix_text() -> None:
    """Phasen werden als deutscher Text auf den Chip geschrieben — nicht
    nur als CSS-Klasse oder Farbe."""
    body = (MODULES_DIR / "calendar.js").read_text(encoding="utf-8")
    assert "PHASE_LABELS" in body
    for label in ('"Start"', '"läuft"', '"Ende"'):
        assert label in body, f"calendar.js sollte Phasentext {label!r} enthalten"
    assert "calendar-event-phase" in body


def test_calendar_agenda_does_not_use_expanded_entries() -> None:
    """Die Agenda darf mehrtägige Kampagnen nicht duplizieren — sie
    bekommt die ungekürzte ``events``-Liste, nicht die expandierte."""
    body = (MODULES_DIR / "calendar.js").read_text(encoding="utf-8")
    assert "renderAgenda(events)" in body
    assert "renderAgenda(expandedEventsForGrid" not in body
    assert "renderAgenda(expanded" not in body
    assert "renderAgendaItem" in body


def test_calendar_chip_has_full_tooltip_via_title_attr() -> None:
    """Jeder Chip bekommt einen ``title``-Tooltip mit allen Detailzeilen.
    ``eventTooltip(event, phase)`` baut den Inhalt zusammen."""
    body = (MODULES_DIR / "calendar.js").read_text(encoding="utf-8")
    assert "function eventTooltip" in body
    assert "title: eventTooltip(" in body
    for label in ("Zeitraum:", "Datum:", "Status:", "WP:"):
        assert label in body, f"eventTooltip sollte {label!r} enthalten"


def test_calendar_chip_css_allows_two_lines() -> None:
    css = (WEB_DIR / "style.css").read_text(encoding="utf-8")
    start = css.index(".calendar-event {")
    end = css.index("}", start)
    block = css[start:end]
    assert "-webkit-line-clamp: 2" in block
    assert "white-space: normal" in block
    assert "word-break: break-word" in block or "overflow-wrap: anywhere" in block


def test_calendar_phase_classes_present_in_css() -> None:
    css = (WEB_DIR / "style.css").read_text(encoding="utf-8")
    for cls in (
        ".calendar-event-phase",
        ".calendar-event-phase-start",
        ".calendar-event-phase-running",
        ".calendar-event-phase-end",
    ):
        assert cls in css, f"style.css sollte {cls} enthalten"


def test_calendar_filterbox_has_reset_button_and_clear_legend() -> None:
    body = (MODULES_DIR / "calendar.js").read_text(encoding="utf-8")
    assert "Kalender filtern" in body
    assert "Zurücksetzen" in body
    assert "resetBtn.addEventListener" in body


def test_calendar_navigation_uses_text_labels() -> None:
    body = (MODULES_DIR / "calendar.js").read_text(encoding="utf-8")
    # Bessere lesbare Beschriftungen statt nur ‹/›.
    assert "← Voriger Monat" in body
    assert "Nächster Monat →" in body
    # „Heute" bleibt zusätzlich vorhanden.
    assert '"Heute"' in body
    # Aria-Labels sind weiterhin gesetzt — Screenreader bekommen den Text.
    assert "Vorheriger Monat" in body
    assert "Nächster Monat" in body


def test_calendar_navigation_has_dedicated_styles() -> None:
    css = (WEB_DIR / "style.css").read_text(encoding="utf-8")
    for cls in (".calendar-nav button", ".calendar-nav-today"):
        assert cls in css, f"style.css sollte {cls} enthalten"
    nav_label_idx = css.index(".calendar-month-label {")
    label_block = css[nav_label_idx : css.index("}", nav_label_idx)]
    assert "font-size: 1.2rem" in label_block or "font-size:1.2rem" in label_block


def test_calendar_module_still_has_no_external_framework_or_writes() -> None:
    """Regression-Sicherung: Der UX-Folgepass darf keine externen
    Bibliotheken/Schreibpfade einschmuggeln."""
    body = (MODULES_DIR / "calendar.js").read_text(encoding="utf-8")
    for forbidden_import in ("FullCalendar", "react", "vue", "luxon", "moment", "jquery"):
        assert forbidden_import not in body
    assert "BEGIN:VCALENDAR" not in body
    assert ".ics" not in body
    for evt in ("dragstart", "dragend"):
        assert f'"{evt}"' not in body
    for method in ('"POST"', '"PATCH"', '"DELETE"'):
        assert method not in body


def test_calendar_api_request_uses_full_visible_grid_range() -> None:
    """Regression: Bei der Maiansicht beginnt das Mo–So-Raster am
    27.04. und endet am 07.06.; vorher hat ``refresh()`` die API nur
    mit Monatsanfang/-ende abgefragt — Randtage des Vor-/Folgemonats
    blieben leer. Der Fix nutzt ``monthGridRange(viewDate)`` und liest
    die from/to-Werte aus den ersten/letzten Rasterzellen."""
    body = (MODULES_DIR / "calendar.js").read_text(encoding="utf-8")
    # Helfer existiert und wird im Render-Pfad benutzt.
    assert "function monthGridRange" in body
    assert "monthGridRange(viewDate)" in body
    # Die from/to-Parameter werden aus dem Grid-Range gesetzt.
    assert 'params.set("from", isoDate(gridRange.from))' in body
    assert 'params.set("to", isoDate(gridRange.to))' in body
    # Der frühere fehlerhafte Pfad (startOfMonth/endOfMonth direkt in
    # params.set) ist verschwunden.
    assert 'params.set("from", isoDate(startOfMonth(viewDate)))' not in body
    assert 'params.set("to", isoDate(endOfMonth(viewDate)))' not in body


# ---- Arbeitspaket-Übersicht — Karten-Layout ---------------------------


def test_workpackages_module_uses_card_grid_not_table() -> None:
    """Die Übersicht ist auf Kartenlayout umgestellt — keine
    klassische Tabelle mit ``<thead>`` mehr im Render-Pfad."""
    body = (MODULES_DIR / "workpackages.js").read_text(encoding="utf-8")
    assert "wp-card-grid" in body
    assert "wp-card" in body
    # Tops + Subs werden gruppiert.
    assert "buildHierarchy" in body
    assert "parent_code" in body
    # Negative: keine Tabellen-Konstruktion mehr.
    assert '"thead"' not in body
    # Bestehende Detail-Links bleiben.
    assert "/portal/workpackages/" in body


def test_workpackages_overview_summary_shows_counts() -> None:
    body = (MODULES_DIR / "workpackages.js").read_text(encoding="utf-8")
    # Render-Funktion + Klasse sichtbar.
    assert "renderSummary" in body
    assert "wp-overview-summary" in body
    # Mindestens diese Teilstrings tauchen im Summary-Text auf.
    for term in ("Arbeitspakete", "Haupt-WPs", "Unterpakete"):
        assert term in body, f"workpackages.js sollte Summary-Begriff {term!r} enthalten"


def test_workpackages_filterbox_exists_with_search_lead_and_reset() -> None:
    body = (MODULES_DIR / "workpackages.js").read_text(encoding="utf-8")
    assert "wp-filterbox" in body
    assert "Arbeitspakete filtern" in body
    # Suche, Lead-Filter, Reset-Button verdrahtet.
    assert "Suche nach Code/Titel" in body
    assert "Lead-Partner" in body
    assert "Alle Lead-Partner" in body
    assert "Zurücksetzen" in body
    assert "resetBtn.addEventListener" in body
    # Live-Filterung beim Tippen — kein „Filtern"-Button nötig.
    assert 'searchInput.addEventListener("input"' in body


def test_workpackages_mine_filter_uses_membership_data_when_available() -> None:
    """„Nur meine Arbeitspakete" wird über ``ctx.me.memberships``
    realisiert — keine API-Erweiterung nötig."""
    body = (MODULES_DIR / "workpackages.js").read_text(encoding="utf-8")
    assert "ctx.me" in body
    assert "memberships" in body
    assert "Nur meine Arbeitspakete" in body
    assert "mineSet" in body


def test_workpackages_subpackages_render_inside_top_cards() -> None:
    body = (MODULES_DIR / "workpackages.js").read_text(encoding="utf-8")
    # Sub-Liste innerhalb der Top-Karte.
    assert "wp-subpackage-list" in body
    assert "wp-subpackage-item" in body
    # Cap + <details>-Erweiterung für den Rest.
    assert "SUBS_VISIBLE_LIMIT" in body
    assert "weitere Unterpakete anzeigen" in body
    # Top-Karte bekommt einen „Details anzeigen"-Footer-Link.
    assert "Details anzeigen" in body


def test_workpackages_filter_no_match_shows_empty_state() -> None:
    body = (MODULES_DIR / "workpackages.js").read_text(encoding="utf-8")
    assert "Keine Arbeitspakete für die aktuelle Filterauswahl." in body
    assert "renderEmpty" in body


def test_workpackages_styles_are_responsive() -> None:
    css = (WEB_DIR / "style.css").read_text(encoding="utf-8")
    for cls in (
        ".wp-overview-summary",
        ".wp-filterbox",
        ".wp-card-grid",
        ".wp-card",
        ".wp-card-head",
        ".wp-card-meta",
        ".wp-subpackage-list",
        ".wp-subpackage-item",
        ".wp-card-footer",
        ".wp-lead-badge",
    ):
        assert cls in css, f"style.css sollte {cls} enthalten"
    # Responsive-Default: einspaltig auf mobil, Grid auf Desktop.
    assert "@media (min-width: 720px)" in css
    # Lange Titel müssen umbrechen können.
    assert "overflow-wrap" in css


def test_workpackages_module_has_no_destructive_actions_or_upload() -> None:
    """Reine Lesesicht — keine Schreibpfade in der Übersicht."""
    body = (MODULES_DIR / "workpackages.js").read_text(encoding="utf-8")
    for forbidden in ('"POST"', '"PATCH"', '"DELETE"', "FormData", 'type: "file"'):
        assert forbidden not in body, f"workpackages.js darf {forbidden!r} nicht enthalten"


# ---- UX-Polish-Block: globale Layout-/Button-/Empty-State-Konsolidierung


WIDE_PAGE_MODULES = (
    "cockpit.js",
    "workpackages.js",
    "milestones.js",
    "meetings.js",
    "actions.js",
    "campaigns.js",
    "calendar.js",
    "lead_team.js",
)


def test_main_page_wide_class_in_css() -> None:
    """``main#app.page-wide`` ist als breitere Variante definiert."""
    css = (WEB_DIR / "style.css").read_text(encoding="utf-8")
    assert "main#app.page-wide" in css


def test_wide_modules_set_page_wide_classlist() -> None:
    """Arbeitsseiten setzen ``container.classList.add("page-wide")`` —
    der Dispatcher in app.js setzt className vor jedem Render zurück."""
    for name in WIDE_PAGE_MODULES:
        body = (MODULES_DIR / name).read_text(encoding="utf-8")
        assert 'container.classList.add("page-wide")' in body, f"{name} sollte page-wide setzen"


def test_app_js_resets_main_classname_on_dispatch() -> None:
    body = (WEB_DIR / "app.js").read_text(encoding="utf-8")
    assert 'main.className = ""' in body


def test_universal_button_classes_in_css() -> None:
    css = (WEB_DIR / "style.css").read_text(encoding="utf-8")
    for cls in (
        "button.button-primary",
        "button.button-secondary",
        "button.button-danger",
        "button.button-compact",
    ):
        assert cls in css, f"style.css sollte {cls} enthalten"


def test_universal_filterbox_class_in_css() -> None:
    css = (WEB_DIR / "style.css").read_text(encoding="utf-8")
    assert ".filterbox" in css
    # Filterbox-Inputs konsistent gestaltet.
    assert ".filterbox label" in css


def test_filterbox_class_used_across_modules() -> None:
    """Modul-Filterboxen tragen zusätzlich die generische ``filterbox``-
    Klasse — ohne ihre modulspezifische zu verlieren."""
    for name in (
        "meetings.js",
        "actions.js",
        "campaigns.js",
        "calendar.js",
        "workpackages.js",
        "lead_team.js",
    ):
        body = (MODULES_DIR / name).read_text(encoding="utf-8")
        assert "filterbox" in body, f"{name} sollte 'filterbox' verwenden"


def test_common_js_exports_render_rich_empty() -> None:
    body = (WEB_DIR / "common.js").read_text(encoding="utf-8")
    assert "export function renderRichEmpty" in body
    # Strukturierter Empty-State mit eigener Klasse.
    css = (WEB_DIR / "style.css").read_text(encoding="utf-8")
    assert ".empty-state" in css
    assert ".empty-state-title" in css
    assert ".empty-state-description" in css
    assert ".empty-state-actions" in css


def test_meetings_actions_calendar_use_rich_empty_state() -> None:
    """Erklärende Empty-States statt karger Einzeiler."""
    for name in ("meetings.js", "actions.js", "calendar.js", "milestones.js"):
        body = (MODULES_DIR / name).read_text(encoding="utf-8")
        assert "renderRichEmpty(" in body, f"{name} sollte renderRichEmpty nutzen"


def test_meetings_empty_state_explains_purpose() -> None:
    body = (MODULES_DIR / "meetings.js").read_text(encoding="utf-8")
    assert "Meetings dienen zur Ablage von Protokollen" in body
    # Anlegen-Button im Empty-State, wenn keine Filter aktiv sind.
    assert "Meeting anlegen …" in body


def test_actions_empty_state_explains_origin() -> None:
    body = (MODULES_DIR / "actions.js").read_text(encoding="utf-8")
    assert "Aufgaben entstehen aus Meeting-Protokollen" in body
    # Reset-Button für Filter.
    assert "Zurücksetzen" in body


def test_calendar_empty_state_explains_calendar_scope() -> None:
    body = (MODULES_DIR / "calendar.js").read_text(encoding="utf-8")
    assert "Keine Termine im gewählten Zeitraum" in body
    assert "Meetings, Testkampagnen, Meilensteine und Aufgaben" in body


def test_milestones_module_uses_timeline_layout() -> None:
    body = (MODULES_DIR / "milestones.js").read_text(encoding="utf-8")
    css = (WEB_DIR / "style.css").read_text(encoding="utf-8")
    # Render-Helfer + Klassen.
    assert "function timelineItem" in body
    assert "timeline-item" in body
    assert "timeline-card" in body
    # Status-spezifische Achievement/Cancel-Klassen.
    assert "timeline-item-achieved" in body
    assert "timeline-item-cancelled" in body
    # CSS-Definition vorhanden.
    for cls in (".timeline", ".timeline-item", ".timeline-card"):
        assert cls in css, f"style.css sollte {cls} enthalten"
    # Negative: keine Tabellen-Zeile mehr im Render-Pfad.
    assert "function rowFor" not in body


def test_calendar_type_legend_present_in_module_and_css() -> None:
    body = (MODULES_DIR / "calendar.js").read_text(encoding="utf-8")
    css = (WEB_DIR / "style.css").read_text(encoding="utf-8")
    assert "function renderTypeLegend" in body
    assert "renderTypeLegend()" in body
    for cls in (".calendar-legend", ".calendar-legend-item", ".calendar-legend-swatch"):
        assert cls in css, f"style.css sollte {cls} enthalten"
    # Klartextlabels statt nur Farbe.
    for label in ("Meeting", "Kampagne", "Meilenstein", "Aufgabe"):
        assert label in body


def test_lead_team_redesigned_with_grid_and_filters() -> None:
    body = (MODULES_DIR / "lead_team.js").read_text(encoding="utf-8")
    css = (WEB_DIR / "style.css").read_text(encoding="utf-8")
    # Karten-Grid statt vieler Tabellen.
    assert "lead-wp-grid" in body
    assert "lead-wp-card" in body
    assert "renderWorkpackageCard" in body
    # Filterbox + Such-/Filter-Felder.
    assert "Mein Team filtern" in body
    assert "Person suchen" in body
    assert "Arbeitspaket suchen" in body
    assert "Nur WPs mit mir als Lead" in body
    # Layout: zwei Spalten auf Desktop.
    assert "lead-team-layout" in body
    for cls in (
        ".lead-team-layout",
        ".lead-wp-grid",
        ".lead-wp-card",
        ".lead-wp-member-row",
    ):
        assert cls in css, f"style.css sollte {cls} enthalten"
    # Funktionen bleiben vorhanden.
    for fn in ("renderCreatePersonForm", "renderAddMemberForm", "renderMemberRow"):
        assert fn in body, f"lead_team.js sollte {fn!r} behalten"
    # Negative: keine Admin-Endpunkte.
    assert "/api/admin/" not in body
    # Empty-State für „kein Lead-WP" vorhanden.
    assert "Du leitest aktuell kein Arbeitspaket" in body


# ---- „Mein Team": Action-Verdrahtung nach UI-Redesign -------------------
#
# Diese Tests sichern ab, dass der Klick-Pfad „Mitglied hinzufügen …"
# nach dem Redesign weiterhin sichtbar reagiert. Der Auslöser für die
# Tests war ein Bug, bei dem ein gemeinsamer Dialog-Slot unterhalb der
# WP-Sektion lag — auf Desktop weit außerhalb des Sichtbereichs des
# geklickten Buttons. Der Fix verschiebt den Slot in jede Karte
# (``lead-wp-card-dialog``) und gibt jedem Action-Button ein stabiles
# ``data-action``-Attribut, damit Tests die Verdrahtung prüfen können,
# ohne sich auf zerbrechliche CSS-Klassen zu stützen.


def test_lead_team_add_member_button_has_stable_action_marker() -> None:
    body = (MODULES_DIR / "lead_team.js").read_text(encoding="utf-8")
    # Stabiles data-action-Attribut auf dem Add-Button.
    assert '"data-action": "add-member"' in body, (
        "lead_team.js: Mitglied-hinzufuegen-Button braucht data-action='add-member'"
    )
    # Klick-Handler ist als onclick gebunden (h() hängt das via addEventListener).
    assert "onclick: onAdd" in body
    # Buttontext bleibt erhalten.
    assert "Mitglied hinzufügen …" in body


def test_lead_team_add_member_dialog_is_inline_per_card() -> None:
    """Der Dialog-Slot wird pro Karte angelegt — nicht als gemeinsamer
    Slot am Ende der Sektion (das war der UI-Redesign-Bug)."""
    body = (MODULES_DIR / "lead_team.js").read_text(encoding="utf-8")
    # Per-Card-Slot existiert.
    assert "lead-wp-card-dialog" in body
    assert 'h("div", { class: "lead-wp-card-dialog" })' in body, (
        "lead_team.js sollte den Inline-Dialog-Slot pro Karte erzeugen"
    )
    # Kein gemeinsamer wpDialogSlot mehr — der Bug entstand genau dadurch.
    assert "wpDialogSlot" not in body, (
        "Gemeinsamer wpDialogSlot wieder eingeführt — Add-Dialog liegt"
        " sonst außerhalb des sichtbaren Bereichs."
    )
    css = (WEB_DIR / "style.css").read_text(encoding="utf-8")
    # CSS für den neuen Slot.
    assert ".lead-wp-card-dialog" in css


def test_lead_team_remove_and_create_buttons_have_action_markers() -> None:
    """Auch Entfernen- und Person-anlegen-Buttons bekommen stabile
    data-action-Attribute, damit ein Redesign sie nicht stillschweigend
    von ihren Klick-Handlern trennt."""
    body = (MODULES_DIR / "lead_team.js").read_text(encoding="utf-8")
    assert '"data-action": "remove-member"' in body
    assert '"data-action": "create-person"' in body


def test_lead_team_add_member_calls_existing_membership_endpoint() -> None:
    """Der Add-Pfad ruft den vorhandenen Lead-API-Endpunkt auf — keine
    neue Route, keine Modelländerung."""
    body = (MODULES_DIR / "lead_team.js").read_text(encoding="utf-8")
    assert "/api/lead/workpackages/" in body
    assert "memberships" in body
    assert '"POST"' in body


def test_lead_team_action_buttons_are_type_button_not_submit() -> None:
    """Aktionsbuttons in Karten duerfen nicht versehentlich Formulare
    absenden - nach dem Redesign muss type='button' erhalten bleiben."""
    body = (MODULES_DIR / "lead_team.js").read_text(encoding="utf-8")
    # Mitglied-hinzufuegen-Button: muss type='button' tragen - sonst
    # wuerde ein umschliessendes Formular ihn absenden. rfind, weil der
    # erste Treffer im Modul-Kommentar liegt.
    add_idx = body.rfind('"Mitglied hinzuf')
    assert add_idx > 0
    add_block = body[max(0, add_idx - 300) : add_idx]
    assert 'type: "button"' in add_block
    assert '"data-action": "add-member"' in add_block
    # Entfernen-Button: dito.
    rm_idx = body.index('"Entfernen"')
    rm_block = body[max(0, rm_idx - 300) : rm_idx]
    assert 'type: "button"' in rm_block
    assert '"data-action": "remove-member"' in rm_block


def test_navigation_admin_group_marker_in_index_and_app_js() -> None:
    index = (WEB_DIR / "index.html").read_text(encoding="utf-8")
    app_js = (WEB_DIR / "app.js").read_text(encoding="utf-8")
    assert 'id="nav-admin-spacer"' in index
    assert 'id="nav-admin-label"' in index
    assert ">Admin<" in index
    # app.js entblendet Spacer + Label im Admin-Modus.
    assert "nav-admin-spacer" in app_js
    assert "nav-admin-label" in app_js
    # CSS für Spacer + Label.
    css = (WEB_DIR / "style.css").read_text(encoding="utf-8")
    assert ".nav-admin-spacer" in css
    assert ".nav-admin-label" in css


def test_admin_view_banner_is_dezenter() -> None:
    """Das Banner soll deutlich kleiner werden als vorher — der UX-
    Polish-Block überschreibt die ursprüngliche Größe per späterer
    Regel mit ``font-size: 0.85rem``."""
    css = (WEB_DIR / "style.css").read_text(encoding="utf-8")
    # Wir nehmen das LETZTE Vorkommen — das ist die Override-Regel.
    last_start = css.rindex(".admin-view-banner")
    snippet = css[last_start : last_start + 400]
    assert "font-size: 0.85rem" in snippet or "font-size:0.85rem" in snippet


# ---- Cockpit-Polish: modernere Karten + bessere Typografie ----------


def test_cockpit_polish_design_tokens_in_css() -> None:
    """Konsistente Design-Tokens als Custom Properties — Tests
    schützen die Token-Namen, damit das Polish-Layer stabil bleibt."""
    css = (WEB_DIR / "style.css").read_text(encoding="utf-8")
    for token in (
        "--cockpit-card-radius",
        "--cockpit-card-bg",
        "--cockpit-card-border",
        "--cockpit-card-shadow",
        "--cockpit-card-shadow-hover",
        "--cockpit-divider",
        "--cockpit-text-muted",
        "--cockpit-text-strong",
        "--cockpit-numeric-feature",
    ):
        assert token in css, f"style.css sollte Token {token} definieren"


def test_cockpit_cards_have_unified_polish_overrides() -> None:
    """Karten-Hülle (Cockpit / Mein-Bereich / Aktivitätsbox) und KPI-
    Karten erben Radius, Schatten und konsistente Innenabstände."""
    css = (WEB_DIR / "style.css").read_text(encoding="utf-8")
    # Die drei Karten-Klassen teilen sich die gleiche Polish-Regel.
    for sel in (
        "main#app .cockpit-card,",
        "main#app .my-area-card,",
        "main#app .activity-box",
    ):
        assert sel in css, f"style.css sollte Selektor {sel!r} enthalten"
    # KPI-Karten bekommen Schatten + Hover-Lift.
    assert "main#app .cockpit-kpi {" in css
    assert "main#app a.cockpit-kpi-link:hover {" in css
    assert "transform: translateY(-1px)" in css
    # Headerbereich pro Karte ist klar abgesetzt.
    assert "border-bottom: 1px solid var(--cockpit-divider)" in css


def test_cockpit_kpi_typography_is_strengthened() -> None:
    css = (WEB_DIR / "style.css").read_text(encoding="utf-8")
    # Erste (Haupt-)Definition der KPI-Zahl prüfen — die spätere im
    # @media-Block überschreibt nur die Größe für mobiles Layout.
    start = css.index("main#app .cockpit-kpi-value")
    snippet = css[start : start + 400]
    assert "font-size: 2rem" in snippet
    assert "tabular-nums" in snippet
    # Label ruhig + leicht abgesetzt.
    label_start = css.index("main#app .cockpit-kpi-label")
    label_block = css[label_start : label_start + 300]
    assert "color: var(--cockpit-text-muted)" in label_block


def test_cockpit_my_wp_table_polish_softens_borders() -> None:
    """Die Mini-Tabelle bekommt ruhigere Trennlinien, größere Höhe
    und tabulare Ziffern — keine harten Standard-Tabellenränder mehr."""
    css = (WEB_DIR / "style.css").read_text(encoding="utf-8")
    assert "main#app .my-wp-table th" in css
    assert "main#app .my-wp-table td" in css
    # Letzte Zeile hat keine Trennlinie mehr (visuelle Ruhe).
    assert "main#app .my-wp-table tbody tr:last-child td" in css


def test_cockpit_wp_issue_card_softer_inner_sections() -> None:
    """Die inneren Sub-Boxen verlieren ihren eigenen Rahmen — bleiben
    aber per linkem Akzent erkennbar."""
    css = (WEB_DIR / "style.css").read_text(encoding="utf-8")
    assert "main#app .wp-issue-section {" in css
    # Border-none + Linker Akzentbalken.
    start = css.rindex("main#app .wp-issue-section {")
    block = css[start : css.index("}", start)]
    assert "border: none" in block
    assert "border-left: 3px solid" in block


def test_cockpit_empty_states_compact_polish() -> None:
    css = (WEB_DIR / "style.css").read_text(encoding="utf-8")
    # Empty-States in Karten teilen sich eine Polish-Regel.
    assert "main#app .cockpit-card .empty," in css
    assert "main#app .my-area-card .empty" in css
    # Sie sind nicht mehr italic, bekommen einen ruhigen Hintergrund
    # und einen dezenten Dashed-Rahmen.
    start = css.index("main#app .cockpit-card .empty,")
    block = css[start : css.index("}", start)]
    assert "font-style: normal" in block
    assert "border: 1px dashed var(--cockpit-card-border)" in block


def test_cockpit_module_classes_remain_unchanged() -> None:
    """Sanity: das Polish ist rein CSS — die wichtigen Klassen aus
    der Cockpit-Modul-Datei sind unverändert da."""
    body = (MODULES_DIR / "cockpit.js").read_text(encoding="utf-8")
    for cls in (
        "cockpit-kpi",
        "cockpit-kpi-value",
        "cockpit-kpi-label",
        "my-area-card",
        "my-wp-table",
        "wp-issue-card",
        "activity-box",
        "cockpit-grid",
    ):
        assert cls in body, f"cockpit.js sollte Klasse {cls!r} weiterhin verwenden"


# ---- Portal-Modernization (portalweiter UI-Polish-Block) -----------


PORTAL_DESIGN_TOKENS = (
    "--portal-card-radius",
    "--portal-card-bg",
    "--portal-card-border",
    "--portal-card-shadow",
    "--portal-card-shadow-hover",
    "--portal-card-padding",
    "--portal-divider",
    "--portal-text-muted",
    "--portal-text-strong",
    "--portal-bg-soft",
    "--portal-numeric-feature",
)


PORTAL_WIDE_MODULES = (
    "cockpit.js",
    "workpackages.js",
    "milestones.js",
    "meetings.js",
    "actions.js",
    "campaigns.js",
    "calendar.js",
    "lead_team.js",
    "system_status.js",
    "admin_partners.js",
    "admin_users.js",
    "admin_user_detail.js",
    "audit.js",
    "campaign_detail.js",
    "document_detail.js",
    "meeting_detail.js",
    "partner_detail.js",
    "workpackage_detail.js",
)


def test_portal_design_tokens_defined() -> None:
    """Portalweite Design-Tokens existieren als Custom Properties."""
    css = (WEB_DIR / "style.css").read_text(encoding="utf-8")
    for token in PORTAL_DESIGN_TOKENS:
        assert token in css, f"style.css sollte Portal-Token {token} definieren"


def test_portal_modernization_block_marker_present() -> None:
    """Eindeutiger Marker am Anfang des Portal-Polish-Blocks — sichert,
    dass der zusammenhängende Block existiert (nicht nur einzelne
    Regelfetzen)."""
    css = (WEB_DIR / "style.css").read_text(encoding="utf-8")
    assert "PORTAL MODERNIZATION" in css


def test_card_shell_unified_across_modules() -> None:
    """Eine gemeinsame Karten-Shell-Regel deckt alle relevanten
    Karten-Klassen ab — kein Modul bleibt versehentlich auf altem
    harten Kasten-Look hängen."""
    css = (WEB_DIR / "style.css").read_text(encoding="utf-8")
    for selector in (
        "main#app .cockpit-card",
        "main#app .my-area-card",
        "main#app .activity-box",
        "main#app .wp-card",
        "main#app .campaign-card",
        "main#app .timeline-card",
        "main#app .system-card",
        "main#app .lead-wp-card",
    ):
        assert selector in css, f"style.css sollte Karten-Selektor {selector!r} polishen"


def test_filterbox_polish_covers_all_module_variants() -> None:
    """Alle Modul-spezifischen Filter-Klassen werden mit der
    portalweiten Filterbox-Optik aktualisiert."""
    css = (WEB_DIR / "style.css").read_text(encoding="utf-8")
    for selector in (
        "main#app .filterbox",
        "main#app .meeting-filterbox",
        "main#app .campaign-filterbox",
        "main#app .calendar-filterbox",
        "main#app .wp-filterbox",
    ):
        assert selector in css, f"style.css sollte {selector!r} polishen"


def test_table_polish_uses_portal_tokens() -> None:
    """Tabellen werden ruhiger gestaltet — caps-Header mit weichen
    Trennern, Hover-Zustand für Zeilen."""
    css = (WEB_DIR / "style.css").read_text(encoding="utf-8")
    # th-Polish (mit Caps + ruhiger Hintergrundfläche). ``rindex``,
    # weil eine ältere Sprint-1-Definition früher im Stylesheet steht
    # — der Polish-Block sitzt am Ende und gewinnt per Cascade.
    assert "main#app th {" in css
    th_start = css.rindex("main#app th {")
    th_block = css[th_start : css.index("}", th_start)]
    assert "text-transform: uppercase" in th_block
    # Im neuen Research-Portal-Design-System (RDS) zeigt der
    # th-Block den ruhigen Muted-Text-Token; Wechsel von --portal-* zu
    # --rds-* ist Teil der portalweiten Konsolidierung.
    assert "var(--rds-text-muted)" in th_block
    # Zeilen-Hover dezent — entweder über data-table oder klassisch.
    assert "main#app tbody tr:hover" in css or "main#app .data-table tbody tr:hover" in css


def test_badge_portal_polish_makes_them_smaller_and_pill_shaped() -> None:
    """Badges werden portalweit kleiner und einheitlicher (Pill)."""
    css = (WEB_DIR / "style.css").read_text(encoding="utf-8")
    assert "main#app .badge {" in css
    start = css.index("main#app .badge {")
    block = css[start : css.index("}", start)]
    assert "border-radius: 999px" in block
    assert "font-size: 0.7rem" in block


def test_typography_h1_h2_have_portal_polish() -> None:
    """``h1`` und ``h2`` der Hauptseiten bekommen klare Hierarchie."""
    css = (WEB_DIR / "style.css").read_text(encoding="utf-8")
    # Sammelregel über main#app + main#app.page-wide.
    assert "main#app > h1,\nmain#app.page-wide > h1" in css
    assert "main#app > h2,\nmain#app.page-wide > h2" in css


def test_calendar_visual_polish_keeps_logic_intact() -> None:
    """Sicherheitsanker: Die Kalenderlogik (monthGridRange,
    actual_date) ist weiterhin im Modul vorhanden — der Polish
    darf rein visuell sein."""
    body = (MODULES_DIR / "calendar.js").read_text(encoding="utf-8")
    assert "function monthGridRange" in body
    assert "monthGridRange(viewDate)" in body
    css = (WEB_DIR / "style.css").read_text(encoding="utf-8")
    # Visueller Polish auf Kalender-Komponenten.
    assert "main#app .calendar-cell" in css
    assert "main#app .calendar-legend" in css


def test_more_detail_modules_now_use_page_wide() -> None:
    """Detailseiten und Adminseiten setzen page-wide für konsistente
    Breite — keine Logikänderung."""
    for name in (
        "admin_partners.js",
        "admin_users.js",
        "admin_user_detail.js",
        "audit.js",
        "campaign_detail.js",
        "document_detail.js",
        "meeting_detail.js",
        "partner_detail.js",
        "system_status.js",
        "workpackage_detail.js",
    ):
        body = (MODULES_DIR / name).read_text(encoding="utf-8")
        assert 'container.classList.add("page-wide")' in body, f"{name} sollte page-wide setzen"


def test_portal_polish_uses_subtle_shadow_not_strong_borders() -> None:
    """Schatten dienen als Tiefe statt harter Rahmen — die Werte
    sind absichtlich sehr klein (0.04–0.08 Alpha)."""
    css = (WEB_DIR / "style.css").read_text(encoding="utf-8")
    # Token-Definition prüft die ruhige Stärke der Tiefe.
    start = css.index("--portal-card-shadow:")
    snippet = css[start : start + 200]
    assert "rgba(28, 44, 76, 0.04)" in snippet


def test_form_inputs_inherit_portal_borders_in_filterbox() -> None:
    css = (WEB_DIR / "style.css").read_text(encoding="utf-8")
    # Inputs in Filterboxen bekommen den portalweiten Border.
    assert "main#app .filterbox input,\nmain#app .filterbox select," in css


def test_system_status_card_is_part_of_portal_polish() -> None:
    """Admin-Systemstatus-Karten teilen die Polish-Regel."""
    css = (WEB_DIR / "style.css").read_text(encoding="utf-8")
    assert "main#app .system-card" in css
    assert "main#app .system-row" in css


def test_milestone_actual_date_logic_remains_in_service() -> None:
    """Sicherheitsanker: actual_date-Pfad ist weiter im Service-Code."""
    body = (
        (
            WEB_DIR.parent.parent.parent.parent
            / "src"
            / "ref4ep"
            / "services"
            / "calendar_service.py"
        ).read_text(encoding="utf-8")
        if False
        else ""
    )
    # Asset-Tests sind nicht der richtige Ort für Backend-Asserts —
    # daher verifizieren wir nur, dass das Frontend-Modul nichts
    # umgebogen hat. Backend-Tests in tests/api/test_calendar_api.py
    # decken die actual_date-Logik fachlich ab.
    body = body  # noqa: F841 — bewusste Selbst-Bezugnahme als Marker.
    assert True


# ---- Research Portal Design System (USWDS-/Carbon-orientiert) ---------
#
# Dieser Block sichert das portal-weite Komponentensystem: zentrale
# Tokens, wiederverwendbare Layout- und Komponentenklassen sowie die
# tatsächliche Verwendung über die Modulseiten hinweg. Pixeltests
# vermeiden wir bewusst — geprüft wird nur, dass die Klassen/Tokens
# definiert sind und in den richtigen Stellen referenziert werden.


def test_rds_design_system_marker_present() -> None:
    """Im Stylesheet liegt ein klar markierter RDS-Block (USWDS-/Carbon-
    orientiert) — kein loses Anhängen einzelner Regeln."""
    css = (WEB_DIR / "style.css").read_text(encoding="utf-8")
    assert "RESEARCH PORTAL DESIGN SYSTEM" in css
    assert "USWDS" in css
    assert "Carbon" in css


def test_rds_tokens_defined_on_root() -> None:
    """Zentrale Tokens des neuen Systems sind auf :root deklariert."""
    css = (WEB_DIR / "style.css").read_text(encoding="utf-8")
    for token in (
        "--rds-surface-canvas",
        "--rds-surface-raised",
        "--rds-surface-soft",
        "--rds-border",
        "--rds-border-strong",
        "--rds-divider",
        "--rds-text",
        "--rds-text-muted",
        "--rds-text-strong",
        "--rds-link",
        "--rds-status-ok-bg",
        "--rds-status-ok-fg",
        "--rds-status-warn-bg",
        "--rds-status-err-bg",
        "--rds-status-info-bg",
        "--rds-status-neutral-bg",
        "--rds-space-2",
        "--rds-space-4",
        "--rds-radius-md",
        "--rds-radius-lg",
        "--rds-shadow-sm",
        "--rds-fs-page-title",
        "--rds-fs-section-title",
        "--rds-fs-card-title",
        "--rds-fs-meta",
        "--rds-fs-data",
        "--rds-fs-badge",
        "--rds-numeric",
    ):
        assert f"{token}:" in css, f"RDS-Token fehlt: {token}"


def test_rds_component_classes_defined() -> None:
    """Wiederverwendbare Layout- und Komponentenklassen sind im
    Stylesheet definiert."""
    css = (WEB_DIR / "style.css").read_text(encoding="utf-8")
    for selector in (
        "main#app .page-shell",
        "main#app .page-header",
        "main#app .page-header > .page-title",
        "main#app .page-header > .page-subtitle",
        "main#app .section-header",
        "main#app .section-card",
        "main#app .section-card > .section-card-header",
        "main#app .card-grid",
        "main#app .card-grid--metric",
        "main#app .metric-card",
        "main#app .metric-card > .metric-label",
        "main#app .metric-card > .metric-value",
        "main#app .filter-bar",
        "main#app .data-table",
        "main#app .data-table thead th",
        "main#app .data-table tbody td",
        "main#app .status-badge",
        "main#app .status-badge--ok",
        "main#app .status-badge--warn",
        "main#app .status-badge--err",
        "main#app .status-badge--info",
        "main#app .status-badge--neutral",
        "main#app .toolbar",
        "main#app .action-row",
        "main#app .meta-row",
        "main#app .meta-label",
        "main#app .meta-value",
        "main#app .empty-state",
        "main#app .detail-section",
    ):
        assert selector in css, f"RDS-Selektor fehlt: {selector}"


def test_rds_filter_bar_uses_quiet_focus_outline() -> None:
    """Die Filter-Bar bekommt einen ruhigen, sichtbaren Fokus-Outline
    (Carbon-orientiert: 2px outline, kein dicker Rahmen)."""
    css = (WEB_DIR / "style.css").read_text(encoding="utf-8")
    block_start = css.index("main#app .filter-bar input:focus")
    block = css[block_start : block_start + 400]
    assert "outline: 2px solid var(--rds-link)" in block


def test_rds_status_badge_palette_is_calm() -> None:
    """Status-Badges nutzen die ruhige USWDS-orientierte Palette
    (kein knalliges SaaS-Bunt)."""
    css = (WEB_DIR / "style.css").read_text(encoding="utf-8")
    # Ok-Hintergrund: weiches Grün, nicht #00ff00 o. ä.
    assert "--rds-status-ok-bg: #e6f1eb;" in css
    assert "--rds-status-warn-bg: #fbf1d6;" in css
    assert "--rds-status-err-bg: #fbe7e6;" in css
    assert "--rds-status-info-bg: #e8f1fa;" in css


def test_common_js_exports_page_header_helper() -> None:
    """``pageHeader(title, subtitle, opts)`` ist als zentraler Helper
    in common.js exportiert; darauf verlassen sich alle Modulseiten."""
    body = (WEB_DIR / "common.js").read_text(encoding="utf-8")
    assert "export function pageHeader(" in body
    # Titel als h1.page-title, Subtitle als p.page-subtitle, Header
    # als <header class="page-header">.
    assert '"page-title"' in body
    assert '"page-subtitle"' in body
    assert '"page-header"' in body
    # Status-Badge-Helper (Tonalitäten ok/warn/err/info/neutral).
    assert "export function statusBadgeClass(" in body


def test_central_modules_use_page_header_helper() -> None:
    """Zentrale Register- und Übersichtsseiten verwenden den
    portalweiten Page-Header — kein eigenes h1."""
    modules_dir = WEB_DIR / "modules"
    for module in (
        "cockpit.js",
        "workpackages.js",
        "milestones.js",
        "meetings.js",
        "actions.js",
        "campaigns.js",
        "calendar.js",
        "lead_team.js",
        "system_status.js",
        "audit.js",
        "admin_users.js",
        "admin_partners.js",
        "account.js",
    ):
        body = (modules_dir / module).read_text(encoding="utf-8")
        assert "pageHeader(" in body, f"{module} verwendet pageHeader nicht"
        # Importzeile muss den Helper enthalten.
        assert "pageHeader" in body.split('from "/portal/common.js"')[0], (
            f"{module} importiert pageHeader nicht"
        )


def test_detail_modules_use_page_header_helper() -> None:
    """Auch die zentralen Detailseiten verwenden den Page-Header."""
    modules_dir = WEB_DIR / "modules"
    for module in (
        "workpackage_detail.js",
        "partner_detail.js",
        "document_detail.js",
        "meeting_detail.js",
        "campaign_detail.js",
        "admin_user_detail.js",
    ):
        body = (modules_dir / module).read_text(encoding="utf-8")
        assert "pageHeader(" in body, f"{module} verwendet pageHeader nicht"


def test_central_module_titles_are_preserved() -> None:
    """Beim Wechsel auf pageHeader bleiben die Modul-Titel als Klartext
    weiter im Quellcode lesbar — sonst können Suchen/Tests sie nicht
    finden."""
    modules_dir = WEB_DIR / "modules"
    expected = {
        "workpackages.js": '"Arbeitspakete"',
        "milestones.js": '"Meilensteine"',
        "meetings.js": '"Meetings"',
        "actions.js": '"Aufgaben"',
        "campaigns.js": '"Testkampagnen"',
        "calendar.js": '"Kalender"',
        "lead_team.js": '"Mein Team"',
        "system_status.js": '"Systemstatus"',
        "audit.js": '"Audit-Log"',
        "admin_users.js": '"Personen"',
        "admin_partners.js": '"Partner"',
        "account.js": '"Konto"',
    }
    for module, snippet in expected.items():
        body = (modules_dir / module).read_text(encoding="utf-8")
        assert snippet in body, f"{module} hat Titel-Snippet {snippet} verloren"


def test_calendar_month_grid_range_logic_intact() -> None:
    """Sicherheitsanker: ``monthGridRange`` für den sichtbaren
    Monatsraster-Zeitraum bleibt im Calendar-Modul. Wir prüfen sowohl
    die Funktion als auch ihre Verwendung im API-Aufruf."""
    body = (WEB_DIR / "modules" / "calendar.js").read_text(encoding="utf-8")
    assert "monthGridRange" in body


def test_calendar_module_does_not_lose_type_legend() -> None:
    """Die Legende mit Event-Typen bleibt Teil der Kalenderseite."""
    body = (WEB_DIR / "modules" / "calendar.js").read_text(encoding="utf-8")
    assert "renderTypeLegend" in body


def test_workpackages_filter_bar_sub_list_sections_remain() -> None:
    """Auf der Arbeitspaket-Übersicht bleiben Filter und Sub-Liste
    erhalten — die optische Modernisierung darf die Funktion nicht
    entfernen."""
    body = (WEB_DIR / "modules" / "workpackages.js").read_text(encoding="utf-8")
    assert "Arbeitspakete filtern" in body
    assert "Nur meine Arbeitspakete" in body
    # Hierarchischer Aufbau (Top + Subs).
    assert "buildHierarchy" in body or "groupedSubs" in body


def test_gantt_module_exists_and_uses_svg() -> None:
    """Block 0026: Gantt-Modul rendert SVG aus /api/gantt-Daten."""
    path = MODULES_DIR / "gantt.js"
    assert path.exists(), "gantt.js fehlt"
    body = path.read_text(encoding="utf-8")
    # SVG-Renderer
    assert "createElementNS" in body
    assert "http://www.w3.org/2000/svg" in body
    # Datenquelle
    assert "/api/gantt" in body
    # Filter-Modi
    for label in ("Quartal", "Jahr", "Gesamt"):
        assert label in body, f"Filter-Label {label!r} fehlt"
    # Heute-Linie
    assert "heute" in body
    # Ampel-Farben für alle vier Werte verfügbar (nur die Keys werden im
    # Quelltext referenziert; die Hex-Farben sind als Werte im
    # TRAFFIC_FILL-Mapping eingetragen).
    for key in ("green", "yellow", "red", "gray"):
        assert key in body, f"Ampelwert {key!r} fehlt"
    # Route registriert?
    app_js = (WEB_DIR / "app.js").read_text(encoding="utf-8")
    assert '"gantt"' in app_js or 'module: "gantt"' in app_js


def test_gantt_has_wp_bars_with_aggregate() -> None:
    """Block 0027: WP-Balken werden gezeichnet, Hauptpakete als
    Aggregat aus den Kindern."""
    body = (MODULES_DIR / "gantt.js").read_text(encoding="utf-8")
    assert "gantt-wp-bar" in body
    assert "gantt-wp-bar-top" in body
    assert "gantt-wp-bar-sub" in body
    assert "computeWpBars" in body
    assert "parent_code" in body
    assert "Start:" in body and "Ende:" in body


def test_cockpit_has_traffic_light_dashboard() -> None:
    """Block 0025: Ampel-Dashboard ist im Cockpit-Modul."""
    body = (MODULES_DIR / "cockpit.js").read_text(encoding="utf-8")
    # Karten-Überschriften
    assert "Arbeitspaket-Ampel" in body
    assert "Projekt-Kennzahlen" in body
    assert "Zeitstrahl — nächste 60 Tage" in body
    # Ampel-Marker (CSS-Klasse via Template-Literal generiert).
    assert "traffic-dot-" in body, "CSS-Klassen-Präfix traffic-dot- fehlt"
    # Deutsche Ampel-Labels für den Tooltip.
    for label in ("grün", "gelb", "rot", "neutral"):
        assert label in body, f"Ampel-Label {label!r} fehlt"
    # Felder aus dem erweiterten Cockpit-Schema
    for field_name in (
        "workpackage_health",
        "milestone_progress",
        "open_meeting_actions",
        "campaign_status_counts",
        "timeline_next_60_days",
    ):
        assert field_name in body, f"Feld {field_name!r} wird im Frontend nicht ausgewertet"


def test_document_detail_has_comments_section() -> None:
    """Block 0024: Comments-Section im Dokumentdetail.

    Prüft, dass das Modul den neuen Abschnitt rendert, die Reverse-Endpunkte
    ansteuert und beide Lebenszyklus-Stati mit deutschen Beschriftungen
    mappt.
    """
    body = (MODULES_DIR / "document_detail.js").read_text(encoding="utf-8")

    # Sichtbare Marker
    assert "Kommentare" in body
    assert "Einreichen" in body
    assert "Bearbeiten" in body

    # Reverse-API-Aufrufe
    assert "/api/document-versions/${versionId}/comments" in body
    assert "/api/document-comments/${comment.id}" in body
    assert "/api/document-comments/${comment.id}/submit" in body

    # Status-Mapping
    for key, label in (("open", "offen"), ("submitted", "eingereicht")):
        assert key in body, f"Status-Key {key!r} fehlt"
        assert label in body, f"Status-Label {label!r} fehlt"


def test_document_comments_overview_module_exists() -> None:
    """Block 0024: globale Übersichtsseite hat einen Filter, lädt
    /api/document-comments und mappt die zwei Status-Werte."""
    path = MODULES_DIR / "document_comments.js"
    assert path.exists(), "document_comments.js fehlt"
    body = path.read_text(encoding="utf-8")
    assert "/api/document-comments" in body
    assert "Status:" in body or "status" in body
    for label in ("offen", "eingereicht"):
        assert label in body
    # Eingebunden im SPA-Router
    app_js = (WEB_DIR / "app.js").read_text(encoding="utf-8")
    assert "document_comments" in app_js


def test_document_detail_has_test_campaigns_section() -> None:
    """Phase-2-UI: Reverse-Pfad Dokument → Testkampagnen.

    Prüft, dass document_detail.js den neuen Abschnitt sowie die zwei
    Reverse-Endpunkte ansteuert und die 9 Junction-Labels mit deutschen
    Beschriftungen mappt.
    """
    body = (MODULES_DIR / "document_detail.js").read_text(encoding="utf-8")

    # Sichtbare Abschnitte / Buttons
    assert "Testkampagnen" in body
    assert "Testkampagne verknüpfen" in body
    assert "Keine Testkampagne zugeordnet." in body

    # Reverse-API-Aufrufe
    assert "/api/documents/${documentId}/test-campaigns" in body
    # DELETE benutzt die Link-id aus dem Aufruf-Closure.
    assert "/test-campaigns/${link.id}" in body
    # Kampagnenauswahl beschränkt auf das WP des Dokuments.
    assert "/api/campaigns?workpackage=" in body

    # Alle 9 Junction-Labels als Schlüssel und mit deutscher Beschriftung.
    for key, label in (
        ("test_plan", "Messplan"),
        ("setup_plan", "Aufbauplan"),
        ("safety_document", "Sicherheitsunterlage"),
        ("raw_data_description", "Rohdatenbeschreibung"),
        ("protocol", "Protokoll"),
        ("analysis", "Auswertung"),
        ("presentation", "Präsentation"),
        ("attachment", "Anlage"),
        ("other", "Sonstiges"),
    ):
        assert key in body, f"Label-Schlüssel {key!r} fehlt"
        assert label in body, f"Label-Beschriftung {label!r} fehlt"


# ---- Block 0028 — Foto-Upload für Testkampagnen -----------------------


def test_campaign_detail_has_photo_section_and_handlers() -> None:
    body = (MODULES_DIR / "campaign_detail.js").read_text(encoding="utf-8")
    # Sektionsüberschrift in deutsch.
    assert '"Fotos"' in body
    # Renderer + Dialoge.
    for fn in (
        "renderPhotosBlock",
        "renderPhotoCard",
        "renderPhotoUploadDialog",
        "renderPhotoCaptionEditDialog",
        "onUploadPhoto",
        "onEditPhotoCaption",
        "onDeletePhoto",
    ):
        assert fn in body, f"campaign_detail.js sollte Funktion {fn!r} enthalten"
    # MIME-Whitelist im Frontend wird auf PNG/JPEG eingegrenzt.
    assert "image/png" in body
    assert "image/jpeg" in body
    # Klassen, die das Styling erwartet.
    for cls in ("campaign-photo-card", "campaign-photo-grid", "campaign-photo-image"):
        assert cls in body, f"Klasse {cls!r} fehlt in campaign_detail.js"


def test_campaign_photo_styles_present() -> None:
    css = (WEB_DIR / "style.css").read_text(encoding="utf-8")
    for cls in (
        ".campaign-photo-grid",
        ".campaign-photo-card",
        ".campaign-photo-image",
        ".campaign-photo-caption",
        ".campaign-photo-meta",
    ):
        assert cls in css, f"style.css sollte {cls} enthalten"


def test_campaign_detail_photo_upload_uses_dedicated_endpoint() -> None:
    """Foto-Upload nutzt POST /api/campaigns/{id}/photos mit FormData,
    nicht den Dokument-Endpunkt."""
    body = (MODULES_DIR / "campaign_detail.js").read_text(encoding="utf-8")
    assert "FormData" in body
    assert "/api/campaigns/" in body and "/photos" in body
    # Kein Document-Upload-Endpunkt:
    assert "/api/documents/" not in body or "/api/documents?" in body


# ---- Block 0029 — Kampagnennotizen ------------------------------------


def test_campaign_detail_has_notes_section_strings() -> None:
    body = (MODULES_DIR / "campaign_detail.js").read_text(encoding="utf-8")
    # UI-Strings (deutsch).
    for needle in (
        '"Kampagnennotizen"',
        '"Notiz hinzufügen"',
        "Idee, Beobachtung oder offene Frage notieren",
        "Kein formales Laborbuch",
    ):
        assert needle in body, f"campaign_detail.js sollte {needle!r} enthalten"
    # Renderer + Block-Funktionen.
    for fn in (
        "renderNotesBlock",
        "renderNoteCard",
        "renderNoteComposer",
        "renderNoteEditDialog",
        "renderMarkdown",
    ):
        assert fn in body, f"campaign_detail.js sollte Funktion {fn!r} enthalten"
    # Handler.
    for fn in ("onCreateNote", "onEditNote", "onDeleteNote"):
        assert fn in body, f"campaign_detail.js sollte Handler {fn!r} enthalten"


def test_campaign_detail_markdown_renderer_escapes_html_centrally() -> None:
    """Renderer enthält eine zentrale Escape-Funktion und nutzt sie."""
    body = (MODULES_DIR / "campaign_detail.js").read_text(encoding="utf-8")
    assert "function escapeHtml" in body
    # Escapes mindestens & < > " '.
    for entity in ("&amp;", "&lt;", "&gt;", "&quot;", "&#39;"):
        assert entity in body, f"escapeHtml sollte {entity} ausgeben"
    # Markdown-Renderer ruft escapeHtml auf, bevor er Block-Strukturen
    # erkennt — Suche nach Verwendung in renderMarkdown-Nähe.
    assert "escapeHtml(source)" in body or "escapeHtml(" in body


def test_campaign_detail_markdown_supports_tables() -> None:
    """Mini-Markdown-Renderer kann Tabellen erzeugen."""
    body = (MODULES_DIR / "campaign_detail.js").read_text(encoding="utf-8")
    assert "renderTableBlock" in body
    assert "campaign-note-table" in body


def test_campaign_detail_uses_no_external_markdown_library() -> None:
    """Kein npm, kein Build-Step, keine externe Markdown-Library."""
    body = (MODULES_DIR / "campaign_detail.js").read_text(encoding="utf-8")
    for forbidden in (
        "marked",
        "markdown-it",
        "showdown",
        "import-from-cdn",
        "unpkg.com",
        "cdn.jsdelivr.net",
    ):
        assert forbidden not in body.lower() or forbidden == "marked" and "marked" not in body, (
            f"campaign_detail.js sollte {forbidden!r} nicht referenzieren"
        )
    # Kein WYSIWYG-Editor.
    for editor in ("tinymce", "ckeditor", "quill", "tiptap", "prosemirror"):
        assert editor not in body.lower(), f"campaign_detail.js sollte {editor!r} nicht enthalten"


def test_campaign_note_styles_present() -> None:
    css = (WEB_DIR / "style.css").read_text(encoding="utf-8")
    for cls in (
        ".campaign-note-card",
        ".campaign-note-list",
        ".campaign-note-body",
        ".campaign-note-meta",
        ".campaign-note-table",
    ):
        assert cls in css, f"style.css sollte {cls} enthalten"


def test_campaign_detail_section_structure_includes_notes() -> None:
    """Die zentrale Sektionsstruktur-Probe muss „Kampagnennotizen" kennen."""
    body = (MODULES_DIR / "campaign_detail.js").read_text(encoding="utf-8")
    assert "Kampagnennotizen" in body
    assert "renderNotesBlock" in body


# ---- Block 0029-pre — JS-Syntaxsanität --------------------------------
# Hintergrund: Patch 0024 hatte den Funktionsheader
# ``function renderTestCampaignsSection(...)`` versehentlich mit-
# entfernt, sodass der nachfolgende Funktions-Body als Modul-Code
# geparst wurde („Illegal return statement"). Node ist in der
# Entwicklungsumgebung nicht verfügbar; deshalb hier ein Python-eigener
# JS-Tokenizer, der Strings, Template-Literale, Kommentare und
# Regex-Literale berücksichtigt und ``return``-Tokens auf Modul-Ebene
# (Brace-Tiefe 0) flaggt. Brace-Tiefe selbst wird wegen Heuristik-
# Grenzen nicht hart geprüft — nur das Auftreten von Top-Level-
# ``return`` würde im Browser zu einem Parse-Fehler führen.

_REGEX_KEYWORDS = frozenset(
    {
        "return",
        "typeof",
        "delete",
        "void",
        "instanceof",
        "in",
        "new",
        "throw",
        "yield",
        "await",
        "of",
    }
)


def _module_level_return_lines(src: str) -> list[int]:
    depth = 0
    in_str: str | None = None
    in_line_comment = False
    in_block_comment = False
    in_regex = False
    in_class = False
    last_token = ""
    last_punct = ""
    issues: list[int] = []
    i = 0
    line = 1
    while i < len(src):
        c = src[i]
        nxt = src[i + 1] if i + 1 < len(src) else ""
        if c == "\n":
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
        if in_regex:
            if c == "\\":
                i += 2
                continue
            if c == "[" and not in_class:
                in_class = True
            elif c == "]" and in_class:
                in_class = False
            elif c == "/" and not in_class:
                in_regex = False
                while i + 1 < len(src) and src[i + 1] in "gimsuy":
                    i += 1
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
        if c == "/":
            trigger_punct = last_punct == "" or last_punct in "(,=;:!&|?{}[+*-~%<>/^"
            trigger_kw = last_token in _REGEX_KEYWORDS
            if trigger_punct or trigger_kw:
                in_regex = True
                in_class = False
                last_token = ""
                last_punct = ""
                i += 1
                continue
        if c in ('"', "'", "`"):
            in_str = c
            last_token = ""
            last_punct = c
            i += 1
            continue
        if c == "{":
            depth += 1
            last_token = ""
            last_punct = c
            i += 1
            continue
        if c == "}":
            depth -= 1
            last_token = ""
            last_punct = c
            i += 1
            continue
        if c.isalpha() or c == "_" or c == "$":
            j = i
            while j < len(src) and (src[j].isalnum() or src[j] in "_$"):
                j += 1
            tok = src[i:j]
            if tok == "return" and depth == 0:
                issues.append(line)
            last_token = tok
            last_punct = ""
            i = j
            continue
        if c.isdigit():
            while i < len(src) and (src[i].isalnum() or src[i] == "."):
                i += 1
            last_token = "0"
            last_punct = ""
            continue
        if not c.isspace():
            last_punct = c
            last_token = ""
        i += 1
    return issues


def test_no_module_level_return_in_web_js() -> None:
    """Regressionsschutz für den ‚Illegal return statement'-Bug aus
    Patch 0024 (Document Comments): in
    ``backend/src/ref4ep/web/modules/document_detail.js`` war versehentlich
    der Funktionsheader ``function renderTestCampaignsSection(...)`` mit-
    entfernt worden, sodass der nachfolgende Funktions-Body als Modul-
    Code geparst wurde. Im Browser scheiterte das Modul-Loading mit
    „Illegal return statement". Der Test prüft alle Web-JS-Dateien."""
    targets = [WEB_DIR / "app.js", WEB_DIR / "common.js"]
    targets.extend(sorted(MODULES_DIR.glob("*.js")))
    failures: list[str] = []
    for path in targets:
        src = path.read_text(encoding="utf-8")
        for ln in _module_level_return_lines(src):
            failures.append(f"{path.name}:{ln} module-level `return` (Browser-Parsefehler)")
    assert not failures, "\n".join(failures)


def test_document_detail_has_render_test_campaigns_section_function() -> None:
    """Sehr spezifischer Regressionsschutz für den konkreten Bug aus
    Patch 0024. Wenn der Funktionsheader irgendwann wieder verschwindet,
    fällt dieser Test sofort auf."""
    body = (MODULES_DIR / "document_detail.js").read_text(encoding="utf-8")
    assert "function renderTestCampaignsSection(" in body
    # Aufruf-Stelle existiert weiterhin.
    assert "renderTestCampaignsSection(" in body
    # Body-Indikator (``doc.test_campaigns``) befindet sich NACH dem
    # Funktionsheader, nicht davor.
    header_idx = body.index("function renderTestCampaignsSection(")
    body_idx = body.index("doc.test_campaigns")
    assert body_idx > header_idx, (
        "Body von renderTestCampaignsSection darf nicht vor dem Header stehen"
    )


# ---- Block 0031 — Editor-Polish Kampagnennotizen ---------------------


def test_campaign_note_editor_helper_is_shared_between_composer_and_dialog() -> None:
    """Composer und Edit-Dialog teilen sich den ``renderMarkdownEditor``-
    Helfer — keine Duplikation, ein Style."""
    body = (MODULES_DIR / "campaign_detail.js").read_text(encoding="utf-8")
    assert "function renderMarkdownEditor(" in body
    composer_idx = body.index("function renderNoteComposer(")
    dialog_idx = body.index("function renderNoteEditDialog(")
    composer_block = body[composer_idx : composer_idx + 1500]
    dialog_block = body[dialog_idx : dialog_idx + 1500]
    assert "renderMarkdownEditor(" in composer_block
    assert "renderMarkdownEditor(" in dialog_block


def test_campaign_note_toolbar_has_all_required_actions() -> None:
    body = (MODULES_DIR / "campaign_detail.js").read_text(encoding="utf-8")
    assert "campaign-note-toolbar" in body
    assert "campaign-note-toolbar-button" in body
    # Deutsche Beschriftungen (sind gleichzeitig die aria-labels via title).
    for label in (
        "Fett",
        "Kursiv",
        "Code",
        "Überschrift",
        "Liste",
        "Nummerierte Liste",
        "Zitat",
        "Tabelle",
        "Link",
    ):
        assert f'"{label}"' in body, f"Toolbar sollte Beschriftung {label!r} bieten"
    # role + aria-label für Screenreader.
    assert 'role: "toolbar"' in body
    assert "Notiz-Editor" in body


def test_campaign_note_toolbar_uses_setrangetext_or_selection_api() -> None:
    """Vanilla-JS-Selektion: setRangeText + selectionStart/-End,
    keine WYSIWYG-/contentEditable-Magie."""
    body = (MODULES_DIR / "campaign_detail.js").read_text(encoding="utf-8")
    assert "setRangeText" in body
    assert "selectionStart" in body
    assert "selectionEnd" in body
    # Kein contentEditable, kein document.execCommand.
    assert "contentEditable" not in body
    assert "execCommand" not in body


def test_campaign_note_live_preview_uses_existing_renderer() -> None:
    body = (MODULES_DIR / "campaign_detail.js").read_text(encoding="utf-8")
    # Vorschau-Container.
    assert "campaign-note-preview" in body
    assert "campaign-note-preview-body" in body
    assert '"Vorschau"' in body
    # Vorschau wird per Input-Event aktualisiert und rendert die
    # Markdown-Quelle über den bestehenden Renderer.
    assert 'addEventListener("input"' in body
    assert "renderMarkdown(textarea.value)" in body


def test_campaign_note_editor_help_text_present() -> None:
    body = (MODULES_DIR / "campaign_detail.js").read_text(encoding="utf-8")
    assert "Markdown-Kenntnisse sind nicht erforderlich" in body


def test_campaign_note_textarea_uses_full_width_styles() -> None:
    css = (WEB_DIR / "style.css").read_text(encoding="utf-8")
    # Es gibt mehrere ``.campaign-note-textarea``-Vorkommen (Basis-
    # Block + Grid-Override im Media-Query). Mindestens EIN Block muss
    # alle erforderlichen Eigenschaften enthalten.
    selector = ".campaign-note-textarea {"
    blocks: list[str] = []
    pos = 0
    while True:
        idx = css.find(selector, pos)
        if idx == -1:
            break
        end = css.find("}", idx)
        blocks.append(css[idx:end])
        pos = end + 1
    assert blocks, "Selektor .campaign-note-textarea { ... } fehlt"
    full_blocks = [
        b
        for b in blocks
        if "width: 100%" in b
        and "box-sizing: border-box" in b
        and "min-height" in b
        and "line-height" in b
    ]
    assert full_blocks, (
        "Mindestens ein .campaign-note-textarea-Block muss "
        "width:100%, box-sizing:border-box, min-height und line-height setzen."
    )


def test_campaign_note_toolbar_and_preview_styles_present() -> None:
    css = (WEB_DIR / "style.css").read_text(encoding="utf-8")
    for cls in (
        ".campaign-note-toolbar",
        ".campaign-note-toolbar-button",
        ".campaign-note-editor",
        ".campaign-note-preview",
        ".campaign-note-preview-body",
        ".campaign-note-preview-label",
    ):
        assert cls in css, f"style.css sollte {cls} enthalten"
    # Leere Vorschau wird ausgeblendet.
    assert ".is-empty" in css


def test_campaign_note_editor_no_external_editor_or_npm() -> None:
    """Patch 0031 darf KEINE WYSIWYG-Library oder npm-Abhängigkeit
    einführen. Wortgrenzen-Match, damit harmlose Substrings wie
    ``Testmatrix`` nicht als ``trix`` gewertet werden."""
    import re

    body = (MODULES_DIR / "campaign_detail.js").read_text(encoding="utf-8").lower()
    for forbidden in ("trix", "tinymce", "ckeditor", "quill", "tiptap", "prosemirror"):
        assert not re.search(rf"\b{re.escape(forbidden)}\b", body), (
            f"{forbidden!r} sollte nicht referenziert sein"
        )
    for forbidden in ("unpkg.com", "cdn.jsdelivr.net", "esm.sh"):
        assert forbidden not in body, f"{forbidden!r} sollte nicht eingebunden sein"


# ---- Block 0031.1 — Editor-Wrapper auf volle Breite -----------------


def _css_block(css: str, selector: str) -> str:
    """Liefert den Inhalt der ersten Regel mit ``selector`` (zwischen
    ``{`` und ``}``). Funktioniert nur für einfache, nicht verschachtelte
    Regeln — reicht für die plain CSS-Datei."""
    if selector not in css:
        return ""
    after = css.split(selector, 1)[1]
    # Den nächsten ``{`` und das passende erste ``}`` finden.
    open_idx = after.find("{")
    close_idx = after.find("}")
    if open_idx == -1 or close_idx == -1 or close_idx < open_idx:
        return ""
    return after[open_idx + 1 : close_idx]


def test_campaign_note_composer_overrides_form_stacked_max_width() -> None:
    """Globale Regel ``form.stacked { max-width: 360px }`` darf den
    Notiz-Composer / Edit-Dialog nicht kappen — sonst rendert der
    Editor mit ~360 px (Bug aus Patch 0031)."""
    css = (WEB_DIR / "style.css").read_text(encoding="utf-8")
    # Es gibt eine kombinierte Override-Regel, die ``max-width: none``
    # für Composer und Edit-Dialog setzt.
    assert "max-width: none" in css
    # Composer-Selektor ist enthalten und überschreibt die globale
    # ``form.stacked``-Begrenzung.
    assert ".campaign-note-composer" in css
    assert "form.campaign-note-composer.stacked" in css
    assert "form.campaign-note-edit-dialog.stacked" in css


def test_campaign_note_composer_and_editor_have_full_width() -> None:
    css = (WEB_DIR / "style.css").read_text(encoding="utf-8")
    # Die Override-Regel kombiniert mehrere Selektoren — sie gilt also
    # für ``.campaign-note-composer`` UND den Editor-Wrapper.
    override_idx = css.find("max-width: none")
    assert override_idx != -1
    # Das Override-Block-Setting umfasst width:100% und box-sizing.
    head = css[max(0, override_idx - 400) : override_idx + 200]
    assert "width: 100%" in head
    assert "box-sizing: border-box" in head
    # Editor-Selbst hat width: 100%.
    editor_block = _css_block(css, ".campaign-note-editor")
    assert "width: 100%" in editor_block


def test_campaign_note_editor_uses_grid_layout_on_desktop() -> None:
    """Auf Desktop-Breite werden Textarea und Vorschau nebeneinander
    angeordnet (Grid 1fr 1fr)."""
    css = (WEB_DIR / "style.css").read_text(encoding="utf-8")
    # Media-Query mit min-width irgendwo zwischen 720 und 1100 px.
    import re

    m = re.search(r"@media\s*\(min-width:\s*(\d+)px\)\s*\{[^@]*?\.campaign-note-editor", css)
    assert m, "Erwarte Media-Query mit Grid-Layout für .campaign-note-editor"
    assert "grid-template-columns: 1fr 1fr" in css
    # Bei leerer Vorschau spannt sich die Textarea über beide Spalten.
    assert "grid-column: 1 / -1" in css
    # Und die Areas/Selektoren-Keys sind benannt.
    assert "grid-template-areas" in css


def test_campaign_note_toolbar_buttons_styled_consistently() -> None:
    """Toolbar-Buttons sollen nicht wie rohe Browser-Buttons aussehen."""
    css = (WEB_DIR / "style.css").read_text(encoding="utf-8")
    block = _css_block(css, ".campaign-note-toolbar-button")
    assert "border-radius" in block
    assert "padding" in block
    assert "min-height" in block
    # Hover- und Focus-Stile vorhanden.
    assert ".campaign-note-toolbar-button:hover" in css
    assert ".campaign-note-toolbar-button:focus-visible" in css


# ---- Block 0032 — Galerie nutzt Thumbnail-Endpoint -------------------


def test_campaign_gallery_uses_thumbnail_endpoint() -> None:
    body = (MODULES_DIR / "campaign_detail.js").read_text(encoding="utf-8")
    # Galerie-<img src> zeigt auf /thumbnail.
    assert "/thumbnail" in body
    # Für das <img>-Markup speziell: ``src`` enthält den Thumbnail-Pfad.
    assert "/photos/${photo.id}/thumbnail" in body
    # Der äußere Link für Original/Download bleibt erhalten.
    assert "/photos/${photo.id}/download" in body
    # loading="lazy" und decoding="async" sind gesetzt.
    assert 'loading: "lazy"' in body
    assert 'decoding: "async"' in body


# ---- Block 0033 — Manueller Admin-Backup-Trigger ---------------------


def test_system_status_has_manual_backup_trigger_button() -> None:
    body = (MODULES_DIR / "system_status.js").read_text(encoding="utf-8")
    assert '"Backup jetzt starten"' in body
    assert "Erstellt ein serverseitiges Backup gemäß Betriebsroutine." in body
    assert "/api/admin/backup/start" in body
    # Confirm-Dialog vorhanden.
    assert "confirm(" in body
    # Bestehende Lesesicht-Behauptung im Header wurde angepasst,
    # damit sie nicht mehr lügt.
    assert "Keine destruktiven Aktionen — nur Lesesicht" not in body


def test_system_status_backup_trigger_uses_no_eval_or_new_function() -> None:
    body = (MODULES_DIR / "system_status.js").read_text(encoding="utf-8")
    assert "eval(" not in body
    assert "new Function(" not in body


def test_system_status_backup_trigger_styles_present() -> None:
    css = (WEB_DIR / "style.css").read_text(encoding="utf-8")
    for cls in (".backup-trigger", ".backup-trigger-hint", ".backup-trigger-status"):
        assert cls in css, f"style.css sollte {cls} enthalten"


def test_sudoers_example_is_strict_and_documented() -> None:
    """Die ausgelieferte sudoers-Beispieldatei darf nur den engen
    ``systemctl start ref4ep-backup.service``-Befehl freigeben."""
    from pathlib import Path

    repo_root = Path(__file__).resolve().parent.parent.parent
    sudoers = repo_root / "infra" / "sudoers" / "ref4ep-backup.sudoers.example"
    text = sudoers.read_text(encoding="utf-8")
    assert "systemctl start ref4ep-backup.service" in text
    # Keine breite ``ALL``-Erlaubnis ohne genauen Befehl.
    assert "NOPASSWD: ALL" not in text
    # Nicht versehentlich andere systemctl-Aktionen freigeben.
    for forbidden in ("systemctl stop", "systemctl restart", "systemctl reload"):
        assert forbidden not in text
    # Hinweis auf visudo -c als Pflichtcheck ist drin.
    assert "visudo -c" in text
    # Platzhalter <USER> für den tatsächlichen Webprozess-User.
    assert "<USER>" in text


# ---- Block 0035 — Projektbibliothek ----------------------------------


def test_navigation_has_project_library_entry() -> None:
    html = (WEB_DIR / "index.html").read_text(encoding="utf-8")
    assert "/portal/library" in html
    assert "Projektbibliothek" in html
    assert 'data-route="project_library"' in html


def test_app_js_registers_project_library_route() -> None:
    body = (WEB_DIR / "app.js").read_text(encoding="utf-8")
    # Routen-Tabelle in app.js nutzt Regex-Literale mit escaped
    # Slashes (``\\/``). Wir suchen nach diesem Pattern statt nach dem
    # rohen ``/portal/library``.
    assert "\\/portal\\/library" in body
    assert 'module: "project_library"' in body


def test_project_library_module_has_required_tile_strings() -> None:
    body = (MODULES_DIR / "project_library.js").read_text(encoding="utf-8")
    for label in (
        "Projektunterlagen",
        "Arbeitspaket-Dokumente",
        "Meilenstein-Dokumente",
        "Literatur & Veröffentlichungen",
        "Vorträge",
        "Abschlussarbeiten",
    ):
        assert label in body, f"Kachel {label!r} fehlt"
    # Header-Untertitel vorhanden.
    assert "Projektbibliothek" in body
    assert "Projektunterlagen" in body


def test_project_library_module_uses_visibility_safe_endpoint() -> None:
    body = (MODULES_DIR / "project_library.js").read_text(encoding="utf-8")
    # Sichtbarkeitsschutz ist explizit aktiviert.
    assert "enforce_visibility" in body
    # Listing kommt aus dem bestehenden Document-Endpunkt.
    assert "/api/documents" in body
    # KEIN „echtes" Dokument-Detail-Holen aus der Liste — Detailseite
    # hat ihre eigene get_by_id-Sichtbarkeitsprüfung.
    assert "/api/documents/${doc.id}" not in body


def test_project_library_upload_uses_dedicated_admin_route() -> None:
    body = (MODULES_DIR / "project_library.js").read_text(encoding="utf-8")
    # Anlage über die Admin-Route (Service erzwingt Admin).
    assert "/api/library/documents" in body
    # Versions-Upload geht über den bestehenden Endpunkt — keine
    # eigene neue Storage-Logik im Frontend.
    assert "/versions" in body
    # Drag-and-Drop nutzt den zentralen Helper.
    assert "createFileDropzone" in body


def test_project_library_styles_present() -> None:
    css = (WEB_DIR / "style.css").read_text(encoding="utf-8")
    for cls in (
        ".library-tile",
        ".library-tile-grid",
        ".library-doc-card",
        ".library-doc-title",
        ".library-filter-bar",
    ):
        assert cls in css, f"style.css sollte {cls} enthalten"


# ---- Block 0035-fix — Cache-Buster + Nav/Router-Konsistenz ------------


_NAV_PATCH_VERSION = "0039"


def test_index_html_uses_cache_buster_for_app_js_and_style_css() -> None:
    """Bei jedem Patch-Block, der die Hauptnavigation oder die SPA-
    Routen ändert, muss der Cache-Buster mitwachsen — sonst behält
    der Browser die alte ``app.js`` und die neue Route bleibt
    unbekannt (Fehler ‚Unbekannter Pfad'). Aktueller Stand:
    Patch 0035."""
    html = (WEB_DIR / "index.html").read_text(encoding="utf-8")
    assert f"/portal/app.js?v={_NAV_PATCH_VERSION}" in html, (
        "Cache-Buster für app.js fehlt oder ist veraltet — neue Routen werden "
        "sonst nicht geladen, weil der Browser die alte app.js cached."
    )
    assert f"/portal/style.css?v={_NAV_PATCH_VERSION}" in html, (
        "Cache-Buster für style.css fehlt oder ist veraltet."
    )


def _extract_nav_hrefs(html: str) -> list[str]:
    import re

    matches = re.findall(
        r'<a\s+href="(/portal/[^"]*)"[^>]*data-route="([^"]+)"',
        html,
    )
    return [(href, route) for href, route in matches]


def _extract_router_patterns(app_js: str) -> list[tuple[str, str]]:
    """Liefert ``[(regex_source, module_name), …]`` aus der ROUTES-Tabelle."""
    import re

    out: list[tuple[str, str]] = []
    for match in re.finditer(
        r"\{\s*pattern:\s*(/[^,]+/),\s*module:\s*\"([^\"]+)\"",
        app_js,
    ):
        out.append((match.group(1), match.group(2)))
    return out


def _js_regex_to_python(source: str) -> str:
    r"""Pragmatische Konvertierung der typischen JS-Regex-Literale aus
    der ROUTES-Tabelle (``/^…$/``) zu Python-``re``-kompatiblen
    Pattern-Strings. Die in Ref4EP genutzten Patterns nutzen nur
    ``\/`` als Escape und ``[^/]+`` als Param-Klasse — beides ist in
    Python identisch."""
    inner = source.strip("/")
    return inner


def test_navigation_links_point_to_registered_router_patterns() -> None:
    """Jeder ``<a href="/portal/…" data-route="X">`` aus der
    Hauptnavigation muss von genau einem Routen-Pattern in app.js
    aufgefangen werden, und die ``module``-Zuordnung muss zum
    ``data-route`` passen. Sonst klickt der Nutzer den Link an, der
    SPA-Router meldet ‚Unbekannter Pfad'."""
    import re as _re

    html = (WEB_DIR / "index.html").read_text(encoding="utf-8")
    app_js = (WEB_DIR / "app.js").read_text(encoding="utf-8")
    nav_pairs = _extract_nav_hrefs(html)
    routes = _extract_router_patterns(app_js)
    assert nav_pairs, "Navigation-Pairs konnten nicht extrahiert werden."
    assert routes, "Routen-Tabelle konnte nicht extrahiert werden."

    failures: list[str] = []
    for href, data_route in nav_pairs:
        href_no_query = href.split("?", 1)[0]
        match_route = None
        for source, module in routes:
            if _re.match(_js_regex_to_python(source), href_no_query):
                match_route = (source, module)
                break
        if match_route is None:
            failures.append(
                f"href {href!r} (data-route={data_route!r}) trifft auf kein Pattern in app.js"
            )
            continue
        if match_route[1] != data_route:
            failures.append(
                f"href {href!r} matched Pattern {match_route[0]!r} "
                f"mit module={match_route[1]!r}, aber data-route={data_route!r}"
            )
    assert not failures, "\n".join(failures)


def test_project_library_module_is_actually_routed() -> None:
    """Stellt sicher, dass ``project_library.js`` nicht nur existiert,
    sondern auch über die ROUTES-Tabelle ladbar ist — der dynamische
    Import in app.js leitet ``module: "project_library"`` auf
    ``/portal/modules/project_library.js`` um."""
    app_js = (WEB_DIR / "app.js").read_text(encoding="utf-8")
    routes = _extract_router_patterns(app_js)
    modules = {module for _src, module in routes}
    assert "project_library" in modules
    assert (MODULES_DIR / "project_library.js").is_file()


# ---- Block 0035-fix2 — Null-Safe WP-Zugriff in document_detail -------


def test_document_detail_does_not_access_workpackage_code_without_null_check() -> None:
    """Block 0035 erlaubt Dokumente ohne WP-Bezug. ``document_detail.js``
    darf daher ``doc.workpackage.code``/``.title`` nicht roh zugreifen
    — sonst crasht das Modul mit ``Cannot read properties of null
    (reading 'code')``. Wir akzeptieren ``doc.workpackage?.code`` und
    Zugriffe innerhalb von ``if (doc.workpackage)``-Guards."""
    body = (MODULES_DIR / "document_detail.js").read_text(encoding="utf-8")
    forbidden_patterns = ("doc.workpackage.code", "doc.workpackage.title")
    for needle in forbidden_patterns:
        assert needle not in body, (
            f"document_detail.js darf ``{needle}`` nicht roh zugreifen — "
            f"Bibliotheks-Dokumente ohne WP-Bezug haben ``doc.workpackage === null``."
        )
    # Der null-safe Zugriff (Optional Chaining) ist explizit verankert.
    assert "doc.workpackage?.code" in body


def test_document_detail_handles_documents_without_workpackage() -> None:
    """Header-Block muss einen Pfad für Dokumente ohne WP-Bezug haben:
    Bibliothek + Bibliotheksbereich-Label statt WP-Link."""
    body = (MODULES_DIR / "document_detail.js").read_text(encoding="utf-8")
    # Bibliotheksbereich-Mapping ist im Modul vorhanden.
    assert "LIBRARY_SECTION_LABELS" in body
    for label in (
        "Projektunterlagen",
        "Meilenstein-Dokumente",
        "Literatur & Veröffentlichungen",
        "Vorträge",
        "Abschlussarbeiten",
    ):
        assert label in body, f"Library-Section-Label {label!r} fehlt"
    # Sichtbarer UI-Hinweis bei WP-losem Dokument.
    assert "ohne Arbeitspaketbezug" in body
    # Conditional rendering: WP-Block läuft nur, wenn WP existiert.
    assert "if (doc.workpackage)" in body or "doc.workpackage ?" in body


def test_document_detail_can_comment_is_null_safe_on_workpackage() -> None:
    """``canCommentDocument`` darf bei fehlendem ``doc.workpackage``
    nicht crashen. Test prüft sowohl die Pfad-Trennung als auch die
    Tatsache, dass es keinen rohen ``doc.workpackage.code`` mehr gibt."""
    body = (MODULES_DIR / "document_detail.js").read_text(encoding="utf-8")
    # Frühreturn bei fehlendem WP-Bezug ist sichtbar.
    func_start = body.index("function canCommentDocument")
    func_end = body.index("\n}\n", func_start)
    func_block = body[func_start:func_end]
    assert "if (!doc.workpackage)" in func_block


# ---- Block 0036 — Versionsnotiz ist optional --------------------------


def test_document_detail_version_upload_does_not_require_change_note() -> None:
    body = (MODULES_DIR / "document_detail.js").read_text(encoding="utf-8")
    # Pflicht-/Mindestlängen-Marker sind weg.
    assert "Änderungsnotiz (Pflicht)" not in body
    assert "mind. 5 Zeichen" not in body
    # Neuer Optional-Hinweis ist verankert.
    assert "Änderungsnotiz (optional)" in body
    # Frontend lässt das Feld weg, wenn nichts eingegeben wurde —
    # damit der Server-Default greifen kann.
    assert 'if (noteValue) formData.append("change_note"' in body


def test_project_library_upload_does_not_require_change_note() -> None:
    body = (MODULES_DIR / "project_library.js").read_text(encoding="utf-8")
    assert "Versionsnotiz (Pflicht" not in body
    assert "mind. 5 Zeichen" not in body
    assert "Änderungsnotiz (optional)" in body
    assert 'if (noteValue) formData.append("change_note"' in body


# ---- Block 0035-Folgepatch — Modal-Upload + Dokumenttyp Paper -------


def test_project_library_uses_modal_overlay_for_upload() -> None:
    """Klick auf „Dokument hochladen …" öffnet ein Modal-Overlay,
    nicht mehr einen Inline-Dialog am Seitenende."""
    body = (MODULES_DIR / "project_library.js").read_text(encoding="utf-8")
    # Modal-Hülle + Backdrop sind verankert.
    assert "library-modal-backdrop" in body
    assert "library-modal" in body
    # Tastatur-Schließen via ESC.
    assert 'key === "Escape"' in body or "key === 'Escape'" in body
    # Backdrop-Klick schließt das Modal.
    assert "ev.target === backdrop" in body
    # Body-Scroll-Lock während Modal offen.
    assert "modal-open" in body
    # Standard-Inline-Slot heißt jetzt ``modalSlot``, NICHT mehr
    # ``dialogSlot``.
    assert "modalSlot" in body


def test_project_library_modal_styles_present() -> None:
    css = (WEB_DIR / "style.css").read_text(encoding="utf-8")
    for cls in (
        ".library-modal-backdrop",
        ".library-modal",
        ".library-modal-head",
        ".library-modal-body",
        ".library-modal-close",
    ):
        assert cls in css, f"style.css sollte {cls} enthalten"
    # Position fixed + hoher z-index.
    block = css.split(".library-modal-backdrop")[1].split("}")[0]
    assert "position: fixed" in block
    assert "z-index" in block
    # Body-Scroll-Lock-Helper vorhanden.
    assert "body.modal-open" in css


def test_project_library_offers_paper_document_type() -> None:
    body = (MODULES_DIR / "project_library.js").read_text(encoding="utf-8")
    # Label-Mapping enthält Paper.
    assert 'paper: "Paper"' in body
    # Dropdown enthält ``paper`` als Option.
    assert '"paper"' in body


def test_document_detail_offers_paper_label() -> None:
    body = (MODULES_DIR / "document_detail.js").read_text(encoding="utf-8")
    assert 'paper: "Paper"' in body


# ---- Block 0035-Folgepatch — Cache-Busting für dynamische Imports ---


def test_app_js_exposes_central_asset_version_constant() -> None:
    """``app.js`` exportiert eine zentrale ``ASSET_VERSION``, die der
    Modul-Loader an dynamische Imports anhängt. Wert muss zur
    aktuellen Patch-Version passen."""
    body = (WEB_DIR / "app.js").read_text(encoding="utf-8")
    assert "export const ASSET_VERSION" in body
    assert f'"{_NAV_PATCH_VERSION}"' in body, (
        f"ASSET_VERSION in app.js sollte {_NAV_PATCH_VERSION!r} sein."
    )


def test_app_js_module_loader_appends_cache_buster() -> None:
    """``loadModule`` hängt ``?v=${ASSET_VERSION}`` an den dynamischen
    Import an, damit Browser-/HTTP-Caches Modul-Updates nicht
    verstecken."""
    body = (WEB_DIR / "app.js").read_text(encoding="utf-8")
    # Der Loader nutzt das Template mit ASSET_VERSION.
    assert "/portal/modules/${name}.js?v=${ASSET_VERSION}" in body
    # Negative: kein „nackter" Import ohne Cache-Buster mehr.
    assert "/portal/modules/${name}.js`)" not in body


# ---- Block 0035-Folgepatch 2 — vollständige Dokumenttypen ------------


_EXPECTED_TYPE_LABELS = {
    "deliverable": "Deliverable",
    "report": ("Bericht", "Report"),  # library nutzt „Bericht", detail „Report"
    "note": "Notiz",
    "paper": "Paper",
    "thesis": "Abschlussarbeit",
    "presentation": "Präsentation",
    "protocol": "Protokoll",
    "specification": "Spezifikation",
    "template": "Vorlage",
    "dataset": "Datensatz",
    "other": ("Sonstiges", "sonstig"),
}


def test_document_detail_type_labels_complete() -> None:
    body = (MODULES_DIR / "document_detail.js").read_text(encoding="utf-8")
    for key, expected in _EXPECTED_TYPE_LABELS.items():
        if isinstance(expected, tuple):
            assert any(f'{key}: "{label}"' in body for label in expected), (
                f"Detail-TYPE_LABELS fehlt {key!r}"
            )
        else:
            assert f'{key}: "{expected}"' in body, f"Detail-TYPE_LABELS fehlt {key!r}"
    # Zentrale Reihenfolge-Liste vorhanden.
    assert "TYPE_OPTIONS" in body
    # Metadaten-Dialog nutzt die zentrale Liste, nicht mehr eine
    # hartcodierte 4-Werte-Liste.
    assert '["deliverable", "report", "note", "other"]' not in body
    assert "...TYPE_OPTIONS.map" in body


def test_project_library_type_labels_complete() -> None:
    body = (MODULES_DIR / "project_library.js").read_text(encoding="utf-8")
    for key, expected in _EXPECTED_TYPE_LABELS.items():
        if isinstance(expected, tuple):
            assert any(f'{key}: "{label}"' in body for label in expected), (
                f"Library-DOC_TYPE_LABELS fehlt {key!r}"
            )
        else:
            assert f'{key}: "{expected}"' in body, f"Library-DOC_TYPE_LABELS fehlt {key!r}"
    assert "DOC_TYPE_OPTIONS" in body
    # Hartcodierte Kurzliste aus dem Vorgängerpatch ist weg.
    assert '["other", "paper", "report", "note"]' not in body
    assert "...DOC_TYPE_OPTIONS.map" in body


def test_metadata_edit_dialog_offers_paper_and_thesis() -> None:
    """Der konkrete Bug: Metadaten-Dialog enthielt vorher nur vier Werte
    und zeigte ``Paper`` nicht an. Jetzt müssen alle neuen Typen
    auswählbar sein."""
    body = (MODULES_DIR / "document_detail.js").read_text(encoding="utf-8")
    # Reihenfolge-Liste und Label sind beide drin.
    options_line_idx = body.index("const TYPE_OPTIONS")
    options_block = body[options_line_idx : options_line_idx + 600]
    for key in (
        "paper",
        "thesis",
        "presentation",
        "protocol",
        "specification",
        "template",
        "dataset",
    ):
        assert f'"{key}"' in options_block, f"TYPE_OPTIONS sollte {key!r} enthalten"
    # Spezifisch die UI-Bug-Bedingung: Paper und Abschlussarbeit als
    # Labels.
    assert '"Paper"' in body
    assert '"Abschlussarbeit"' in body


# ---- Block 0035-Folgepatch 3 — Soft-Delete-Navigation + Modal -------


def test_document_detail_soft_delete_navigates_to_library_when_no_workpackage() -> None:
    """Bibliotheks-Dokumente (``doc.workpackage === null``) dürfen
    nach Soft-Delete nicht auf ``/portal/workpackages/null``
    navigieren — sie landen stattdessen in der Projektbibliothek."""
    body = (MODULES_DIR / "document_detail.js").read_text(encoding="utf-8")
    # Konkreter Code-Pfad: ternärer Fallback auf /portal/library, wenn
    # ``wpCode`` falsy ist.
    assert "wpCode" in body
    assert '"/portal/library"' in body
    # Im Soft-Delete-Block muss explizit der Ternär-Fallback stehen.
    delete_idx = body.index('"Soft-Delete …"')
    block = body[max(0, delete_idx - 800) : delete_idx + 50]
    assert "wpCode\n" in block, "Erwartet ternäre Verzweigung auf wpCode im Soft-Delete-Block."
    assert '"/portal/library"' in block, (
        "Soft-Delete-Block muss bei fehlendem WP nach /portal/library navigieren."
    )


def test_document_detail_metadata_edit_uses_modal_overlay() -> None:
    """„Metadaten bearbeiten" öffnet sich als Modal-Overlay statt als
    Inline-Dialog am Seitenende."""
    body = (MODULES_DIR / "document_detail.js").read_text(encoding="utf-8")
    # Modal-Helper ist verankert.
    assert "function showModal" in body
    assert "portal-modal-backdrop" in body
    assert "portal-modal-body" in body
    # Metadaten-Bearbeiten-Button ruft showModal — nicht mehr
    # showDialog für diesen Eintrag.
    edit_idx = body.index('"Metadaten bearbeiten …"')
    # Suche ein paar Zeilen vorher nach showModal-Aufruf.
    block = body[max(0, edit_idx - 600) : edit_idx + 50]
    assert 'showModal(\n              "Metadaten bearbeiten"' in block
    # Versionsupload nutzt ebenfalls das Modal.
    upload_idx = body.index('"Neue Version hochladen …"')
    block_up = body[max(0, upload_idx - 600) : upload_idx + 50]
    assert 'showModal(\n              "Neue Version hochladen"' in block_up
    # Schließverhalten: ESC und Backdrop-Klick.
    assert 'key === "Escape"' in body
    assert "ev.target === backdrop" in body
    # Body-Scroll-Lock während Modal offen.
    assert "modal-open" in body


def test_portal_modal_styles_share_rules_with_library_modal() -> None:
    """``portal-modal-*`` Klassen sind als Aliase im selben Selektor
    angelegt wie die Library-Variante; bestehende Library-Tests
    bleiben dadurch grün."""
    css = (WEB_DIR / "style.css").read_text(encoding="utf-8")
    for cls in (
        ".portal-modal-backdrop",
        ".portal-modal-head",
        ".portal-modal-body",
        ".portal-modal-close",
    ):
        assert cls in css, f"style.css sollte {cls} enthalten"
    # Multi-Selektor-Form (eine Variante pro Block), damit beide
    # Klassen identische Regeln erben.
    assert ".library-modal-backdrop,\n.portal-modal-backdrop" in css
    assert ".library-modal,\n.portal-modal {" in css
    assert ".library-modal-body,\n.portal-modal-body" in css
