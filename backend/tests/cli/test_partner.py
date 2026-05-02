"""ref4ep-admin partner."""

from __future__ import annotations

import pytest

from ref4ep.cli.admin import main


def test_partner_create_and_list(cli_db: str, capsys: pytest.CaptureFixture[str]) -> None:
    rc = main(["partner", "create", "--short-name", "ACM", "--name", "Acme", "--country", "DE"])
    assert rc == 0
    capsys.readouterr()
    assert main(["partner", "list"]) == 0
    out = capsys.readouterr().out
    assert "ACM" in out
    assert "Acme" in out
