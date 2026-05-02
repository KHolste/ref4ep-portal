"""SeedService — Idempotenz und Lead-Vererbung."""

from __future__ import annotations

from sqlalchemy.orm import Session

from ref4ep.domain.models import Partner, Workpackage
from ref4ep.services.seed_service import SeedService


def test_seed_loads_5_partners_and_35_workpackages(session: Session) -> None:
    result = SeedService(session).apply_initial_seed(source="antrag")
    assert result["partners_added"] == 5
    assert result["workpackages_added"] == 35

    partners = session.query(Partner).all()
    wps = session.query(Workpackage).all()
    assert len(partners) == 5
    assert len(wps) == 35

    parents = [w for w in wps if w.parent_workpackage_id is None]
    children = [w for w in wps if w.parent_workpackage_id is not None]
    assert len(parents) == 8
    assert len(children) == 27


def test_seed_lead_inheritance(session: Session) -> None:
    SeedService(session).apply_initial_seed(source="antrag")
    by_code = {w.code: w for w in session.query(Workpackage).all()}

    # Spot-Check der WP-Tabelle aus §13.4
    expected_leads = {
        "WP1": "JLU",
        "WP2": "IOM",
        "WP3": "TUD",
        "WP4": "CAU",
        "WP5": "THM",
        "WP6": "IOM",
        "WP7": "JLU",
        "WP8": "JLU",
    }
    for code, lead in expected_leads.items():
        assert by_code[code].lead_partner.short_name == lead

    # Sub-WPs erben
    assert by_code["WP3.1"].lead_partner.short_name == "TUD"
    assert by_code["WP3.3"].lead_partner.short_name == "TUD"
    assert by_code["WP6.4"].lead_partner.short_name == "IOM"
    assert by_code["WP8.3"].lead_partner.short_name == "JLU"


def test_seed_titles_match_specification(session: Session) -> None:
    SeedService(session).apply_initial_seed(source="antrag")
    by_code = {w.code: w for w in session.query(Workpackage).all()}
    assert by_code["WP1"].title == "Projektmanagement, Daten und Dissemination"
    assert by_code["WP3"].title == "Referenz-Halltriebwerk"
    assert by_code["WP8.3"].title == "Energiekalibrierung"
    assert by_code["WP4.6"].title == "Plasmasonden"


def test_seed_is_idempotent(session: Session) -> None:
    svc = SeedService(session)
    first = svc.apply_initial_seed(source="antrag")
    session.commit()
    second = svc.apply_initial_seed(source="antrag")
    assert first["partners_added"] == 5
    assert second["partners_added"] == 0
    assert second["partners_skipped"] == 5
    assert second["workpackages_added"] == 0
    assert second["workpackages_skipped"] == 35


def test_seed_does_not_overwrite_manual_changes(session: Session) -> None:
    SeedService(session).apply_initial_seed(source="antrag")
    wp = session.query(Workpackage).filter_by(code="WP1.1").one()
    wp.title = "Manuell geändert"
    session.commit()
    SeedService(session).apply_initial_seed(source="antrag")
    refreshed = session.query(Workpackage).filter_by(code="WP1.1").one()
    assert refreshed.title == "Manuell geändert"
