"""ref4ep-admin membership add/remove."""

from __future__ import annotations

import pytest

from ref4ep.cli.admin import main


def test_membership_add_and_remove(
    cli_db: str,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    main(["seed", "--from", "antrag"])
    monkeypatch.setattr("ref4ep.cli.admin._prompt_password", lambda min_len=10: "InitialPw-1234")
    main(
        [
            "person",
            "create",
            "--email",
            "carol@test.example",
            "--display-name",
            "Carol",
            "--partner",
            "JLU",
            "--role",
            "member",
        ]
    )
    capsys.readouterr()
    rc = main(
        [
            "membership",
            "add",
            "--person",
            "carol@test.example",
            "--workpackage",
            "WP1",
            "--role",
            "wp_member",
        ]
    )
    assert rc == 0
    rc = main(
        [
            "membership",
            "remove",
            "--person",
            "carol@test.example",
            "--workpackage",
            "WP1",
        ]
    )
    assert rc == 0
