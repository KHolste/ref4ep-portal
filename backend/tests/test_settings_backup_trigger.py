"""Settings-Validatoren für den Backup-Trigger (Block 0033)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from tests.conftest import make_test_settings


def test_default_backup_trigger_command_is_absolute_and_plausible() -> None:
    settings = make_test_settings()
    cmd = settings.backup_trigger_command
    assert isinstance(cmd, tuple)
    assert cmd, "Default-Befehl darf nicht leer sein."
    assert cmd[0].startswith("/")
    # Default-Service-Name ist verankert.
    assert "ref4ep-backup.service" in cmd[-1]
    assert settings.backup_trigger_timeout_seconds >= 1


def test_relative_first_argument_is_rejected() -> None:
    with pytest.raises(ValidationError):
        make_test_settings(backup_trigger_command=("systemctl", "start", "ref4ep-backup.service"))


def test_dotdot_in_first_argument_is_rejected() -> None:
    with pytest.raises(ValidationError):
        make_test_settings(
            backup_trigger_command=("/usr/bin/../bin/systemctl", "start", "ref4ep-backup.service")
        )


def test_shell_metacharacters_are_rejected() -> None:
    bad_args = [
        ("/usr/bin/sudo", "-n", "systemctl;rm -rf /"),
        ("/usr/bin/sudo", "-n", "/bin/sh", "-c", "systemctl start x | mail"),
        ("/usr/bin/sudo", "$INJECT"),
        ("/usr/bin/sudo", "`whoami`"),
        ("/usr/bin/sudo", "echo & sleep 99"),
    ]
    for combo in bad_args:
        with pytest.raises(ValidationError):
            make_test_settings(backup_trigger_command=combo)


def test_empty_command_is_rejected() -> None:
    with pytest.raises(ValidationError):
        make_test_settings(backup_trigger_command=())


def test_string_override_is_split_to_list() -> None:
    """Override per Env-Variable kommt als String. Validator darf
    sie zu einer Liste machen."""
    settings = make_test_settings(
        backup_trigger_command="/usr/bin/sudo -n /usr/bin/systemctl start ref4ep-backup.service"
    )
    assert settings.backup_trigger_command == (
        "/usr/bin/sudo",
        "-n",
        "/usr/bin/systemctl",
        "start",
        "ref4ep-backup.service",
    )


def test_timeout_must_be_positive() -> None:
    with pytest.raises(ValidationError):
        make_test_settings(backup_trigger_timeout_seconds=0)
    with pytest.raises(ValidationError):
        make_test_settings(backup_trigger_timeout_seconds=-1)
