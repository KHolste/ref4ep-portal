"""Tests für ``BackupTriggerService`` (Block 0033)."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from typing import Any

import pytest
from sqlalchemy.orm import Session

from ref4ep.domain.models import AuditLog
from ref4ep.services.audit_logger import AuditLogger
from ref4ep.services.backup_trigger_service import (
    BackupTriggerResult,
    BackupTriggerService,
)


@dataclass
class _FakeCompleted:
    returncode: int
    stdout: bytes = b""
    stderr: bytes = b""


class _Recorder:
    """Protokolliert subprocess-Aufrufe und liefert ein vorbereitetes
    ``CompletedProcess`` zurück. Erlaubt das Hochwerfen von
    Exceptions für Timeout-/Error-Pfade."""

    def __init__(
        self,
        *,
        returncode: int = 0,
        stderr: bytes = b"",
        raise_exc: BaseException | None = None,
    ) -> None:
        self.calls: list[tuple[Any, dict[str, Any]]] = []
        self._returncode = returncode
        self._stderr = stderr
        self._raise_exc = raise_exc

    def __call__(self, args, **kwargs):
        self.calls.append((args, kwargs))
        if self._raise_exc is not None:
            raise self._raise_exc
        return _FakeCompleted(returncode=self._returncode, stderr=self._stderr)


def _make_service(
    seeded_session: Session,
    *,
    runner,
    command=("/usr/bin/sudo", "-n", "/usr/bin/systemctl", "start", "ref4ep-backup.service"),
    timeout: int = 30,
) -> tuple[BackupTriggerService, AuditLogger]:
    audit = AuditLogger(seeded_session, actor_label="admin@test.example")
    service = BackupTriggerService(
        audit=audit, command=command, timeout_seconds=timeout, runner=runner
    )
    return service, audit


def test_runner_is_called_with_exact_argument_list(seeded_session: Session) -> None:
    rec = _Recorder(returncode=0)
    service, _ = _make_service(seeded_session, runner=rec)
    service.start()
    assert len(rec.calls) == 1
    args, kwargs = rec.calls[0]
    assert args == [
        "/usr/bin/sudo",
        "-n",
        "/usr/bin/systemctl",
        "start",
        "ref4ep-backup.service",
    ]


def test_runner_is_called_without_shell(seeded_session: Session) -> None:
    rec = _Recorder(returncode=0)
    service, _ = _make_service(seeded_session, runner=rec)
    service.start()
    _, kwargs = rec.calls[0]
    assert kwargs.get("shell") is False
    assert kwargs.get("capture_output") is True
    assert kwargs.get("check") is False
    assert kwargs.get("timeout") == 30


def test_success_result_and_audit(seeded_session: Session) -> None:
    rec = _Recorder(returncode=0)
    service, _ = _make_service(seeded_session, runner=rec)
    result = service.start()
    seeded_session.commit()
    assert isinstance(result, BackupTriggerResult)
    assert result.result == "success"
    assert result.exit_code == 0
    assert "gestartet" in result.message
    log = (
        seeded_session.query(AuditLog)
        .filter_by(action="admin.backup.start")
        .order_by(AuditLog.created_at.desc())
        .first()
    )
    assert log is not None
    blob = str(log.details)
    assert '"result": "success"' in blob
    assert '"trigger": "manual_web"' in blob


def test_failure_result_records_stderr_excerpt(seeded_session: Session) -> None:
    rec = _Recorder(returncode=2, stderr=b"sudoers: not allowed\n")
    service, _ = _make_service(seeded_session, runner=rec)
    result = service.start()
    seeded_session.commit()
    assert result.result == "failure"
    assert result.exit_code == 2
    assert "Exit-Code 2" in result.message
    log = (
        seeded_session.query(AuditLog)
        .filter_by(action="admin.backup.start")
        .order_by(AuditLog.created_at.desc())
        .first()
    )
    assert log is not None
    blob = str(log.details)
    assert "stderr_excerpt" in blob
    assert "sudoers" in blob


def test_timeout_is_handled_gracefully(seeded_session: Session) -> None:
    rec = _Recorder(raise_exc=subprocess.TimeoutExpired(cmd="x", timeout=30))
    service, _ = _make_service(seeded_session, runner=rec)
    result = service.start()
    seeded_session.commit()
    assert result.result == "failure"
    assert result.exit_code == -1
    assert "abgebrochen" in result.message.lower() or "timeout" in result.message.lower()
    log = (
        seeded_session.query(AuditLog)
        .filter_by(action="admin.backup.start")
        .order_by(AuditLog.created_at.desc())
        .first()
    )
    assert log is not None
    assert "timeout" in str(log.details)


def test_filenotfound_is_handled_gracefully(seeded_session: Session) -> None:
    rec = _Recorder(raise_exc=FileNotFoundError("/usr/bin/sudo not found"))
    service, _ = _make_service(seeded_session, runner=rec)
    result = service.start()
    assert result.result == "failure"
    assert result.exit_code == -2
    assert "nicht gefunden" in result.message.lower()


def test_empty_command_is_rejected(seeded_session: Session) -> None:
    audit = AuditLogger(seeded_session, actor_label="x")
    with pytest.raises(ValueError):
        BackupTriggerService(audit=audit, command=(), timeout_seconds=30)


def test_long_stderr_is_truncated(seeded_session: Session) -> None:
    long_err = b"x" * 1000
    rec = _Recorder(returncode=3, stderr=long_err)
    service, _ = _make_service(seeded_session, runner=rec)
    result = service.start()
    # Detail im Result-Message ist auf den 200-Zeichen-Excerpt gekappt.
    assert len(result.message) < 400
