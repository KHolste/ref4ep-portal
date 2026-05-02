"""ref4ep-admin seed --from antrag."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from ref4ep.cli.admin import main
from ref4ep.domain.models import Partner, Workpackage


def _counts(url: str) -> tuple[int, int, int, int]:
    eng = create_engine(url)
    with sessionmaker(bind=eng)() as s:
        partners = s.query(Partner).count()
        wps = s.query(Workpackage).count()
        parent_filter = Workpackage.parent_workpackage_id.is_(None)
        child_filter = Workpackage.parent_workpackage_id.isnot(None)
        parents = s.query(Workpackage).filter(parent_filter).count()
        children = s.query(Workpackage).filter(child_filter).count()
    return partners, wps, parents, children


def test_seed_first_run(cli_db: str, capsys: pytest.CaptureFixture[str]) -> None:
    rc = main(["seed", "--from", "antrag"])
    assert rc == 0
    partners, wps, parents, children = _counts(cli_db)
    assert partners == 5
    assert wps == 35
    assert parents == 8
    assert children == 27
    out = capsys.readouterr().out
    assert "5 angelegt" in out
    assert "35 angelegt" in out
    assert "8 Hauptarbeitspakete + 27 Unterarbeitspakete" in out


def test_seed_idempotent(cli_db: str, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["seed", "--from", "antrag"]) == 0
    capsys.readouterr()  # erste Ausgabe verwerfen
    assert main(["seed", "--from", "antrag"]) == 0
    out = capsys.readouterr().out
    assert "0 angelegt" in out
    assert "5 übersprungen" in out
    assert "35 übersprungen" in out
    partners, wps, _, _ = _counts(cli_db)
    assert partners == 5
    assert wps == 35


def test_seed_structure_spot_checks(cli_db: str) -> None:
    main(["seed", "--from", "antrag"])
    eng = create_engine(cli_db)
    with sessionmaker(bind=eng)() as s:
        wp4 = s.query(Workpackage).filter_by(code="WP4").one()
        wp3 = s.query(Workpackage).filter_by(code="WP3").one()
        wp83 = s.query(Workpackage).filter_by(code="WP8.3").one()
        children_4 = s.query(Workpackage).filter_by(parent_workpackage_id=wp4.id).count()
        children_3 = s.query(Workpackage).filter_by(parent_workpackage_id=wp3.id).count()
    assert children_4 == 6
    assert children_3 == 3
    assert wp83.title == "Energiekalibrierung"
