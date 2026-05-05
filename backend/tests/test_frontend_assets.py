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


def test_milestones_page_renders_table() -> None:
    body = (MODULES_DIR / "milestones.js").read_text(encoding="utf-8")
    for term in ("Code", "Titel", "Arbeitspaket", "Plandatum", "Istdatum", "Status", "Notiz"):
        assert term in body
    # Status-Übersetzungen
    assert "geplant" in body
    assert "erreicht" in body
    assert "verschoben" in body
    assert "gefährdet" in body
    assert "entfallen" in body


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
    # Filterbox ist ein <fieldset class="meeting-filterbox"> mit <legend>.
    assert '"meeting-filterbox"' in body
    assert "Meetings filtern" in body
    # Klarerer Placeholder.
    assert "WP-Code filtern, z. B. WP3.1" in body
    # Alter Placeholder ist verschwunden.
    assert "WP-Code (z. B. WP3.1)" not in body
    # CSS-Klasse vorhanden.
    css = (WEB_DIR / "style.css").read_text(encoding="utf-8")
    assert ".meeting-filterbox" in css


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
