"""ref4ep-admin workpackage."""

from __future__ import annotations

import pytest

from ref4ep.cli.admin import main


def test_workpackage_create_with_parent(cli_db: str, capsys: pytest.CaptureFixture[str]) -> None:
    main(["seed", "--from", "antrag"])
    capsys.readouterr()
    rc = main(
        [
            "workpackage",
            "create",
            "--code",
            "WP9",
            "--title",
            "Sondermodul",
            "--lead",
            "JLU",
        ]
    )
    assert rc == 0
    rc = main(
        [
            "workpackage",
            "create",
            "--code",
            "WP9.1",
            "--title",
            "Sub Sondermodul",
            "--lead",
            "JLU",
            "--parent",
            "WP9",
        ]
    )
    assert rc == 0
    capsys.readouterr()
    main(["workpackage", "list"])
    out = capsys.readouterr().out
    assert "WP9" in out
    assert "WP9.1" in out
