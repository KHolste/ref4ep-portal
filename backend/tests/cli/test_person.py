"""ref4ep-admin person — create/list/reset-password/set-role."""

from __future__ import annotations

import pytest

from ref4ep.cli.admin import main


def test_person_create_and_list(
    cli_db: str,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    main(["seed", "--from", "antrag"])
    capsys.readouterr()
    monkeypatch.setattr("ref4ep.cli.admin._prompt_password", lambda min_len=10: "InitialPw-1234")
    rc = main(
        [
            "person",
            "create",
            "--email",
            "alice@test.example",
            "--display-name",
            "Alice",
            "--partner",
            "JLU",
            "--role",
            "admin",
        ]
    )
    assert rc == 0
    capsys.readouterr()
    main(["person", "list"])
    out = capsys.readouterr().out
    assert "alice@test.example" in out
    assert "admin" in out


def test_person_set_role(
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
            "bob@test.example",
            "--display-name",
            "Bob",
            "--partner",
            "IOM",
            "--role",
            "member",
        ]
    )
    capsys.readouterr()
    rc = main(["person", "set-role", "--email", "bob@test.example", "--role", "admin"])
    assert rc == 0
    main(["person", "list"])
    out = capsys.readouterr().out
    assert "bob@test.example" in out
    assert "admin" in out
