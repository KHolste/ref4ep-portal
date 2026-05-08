"""API-Tests: manueller Admin-Backup-Trigger (Block 0033)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from ref4ep.api.app import create_app
from ref4ep.api.config import Settings
from ref4ep.domain.models import AuditLog
from tests.conftest import (
    ADMIN_EMAIL,
    ADMIN_PASSWORD,
    _apply_migrations,
    make_test_settings,
)


@dataclass
class _FakeCompleted:
    returncode: int
    stdout: bytes = b""
    stderr: bytes = b""


class _Recorder:
    def __init__(
        self,
        *,
        returncode: int = 0,
        stderr: bytes = b"",
    ) -> None:
        self.calls: list[tuple[Any, dict[str, Any]]] = []
        self._returncode = returncode
        self._stderr = stderr

    def __call__(self, args, **kwargs):
        self.calls.append((args, kwargs))
        return _FakeCompleted(returncode=self._returncode, stderr=self._stderr)


def _csrf(client: TestClient) -> dict[str, str]:
    return {"X-CSRF-Token": client.cookies.get("ref4ep_csrf") or ""}


@pytest.fixture
def patched_settings(settings: Settings) -> Settings:
    """Settings mit kurzem Timeout — der Default ist sicher; der Test
    nutzt einen Recorder-Runner und braucht kein echtes Timeout."""
    return settings


def test_anonymous_cannot_start_backup(client: TestClient) -> None:
    """Anonyme Anfragen werden abgelehnt — je nach Reihenfolge der
    CSRF-/Auth-Middleware mit 401 oder 403."""
    client.cookies.clear()
    r = client.post("/api/admin/backup/start", json={})
    assert r.status_code in (401, 403)


def test_member_cannot_start_backup(member_client: TestClient) -> None:
    r = member_client.post("/api/admin/backup/start", json={}, headers=_csrf(member_client))
    assert r.status_code == 403


def test_admin_without_csrf_cannot_start_backup(admin_client: TestClient) -> None:
    r = admin_client.post("/api/admin/backup/start", json={})
    assert r.status_code == 403


def _swap_runner(monkeypatch: pytest.MonkeyPatch, recorder: _Recorder) -> None:
    """Patch ``subprocess.run`` für die Dauer eines Tests, damit der
    Default-Runner im Service-Builder nicht echt ausführt."""
    import ref4ep.services.backup_trigger_service as svc

    monkeypatch.setattr(svc.subprocess, "run", recorder)


def test_admin_with_csrf_starts_backup_success(
    admin_client: TestClient,
    seeded_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rec = _Recorder(returncode=0)
    _swap_runner(monkeypatch, rec)
    r = admin_client.post("/api/admin/backup/start", json={}, headers=_csrf(admin_client))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["result"] == "success"
    assert body["exit_code"] == 0
    assert "gestartet" in body["message"]
    # Subprocess wurde mit der Default-Argumentliste aufgerufen.
    assert len(rec.calls) == 1
    args, kwargs = rec.calls[0]
    assert args[0].startswith("/")
    assert "ref4ep-backup.service" in args[-1]
    assert kwargs.get("shell") is False


def test_admin_with_csrf_handles_failure(
    admin_client: TestClient,
    seeded_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rec = _Recorder(returncode=1, stderr=b"systemctl: not allowed\n")
    _swap_runner(monkeypatch, rec)
    r = admin_client.post("/api/admin/backup/start", json={}, headers=_csrf(admin_client))
    # Der Aufruf bleibt 200 — das Ergebnisfeld trägt das ``failure``.
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["result"] == "failure"
    assert body["exit_code"] == 1
    assert body["message"]


def test_audit_entry_is_written_for_admin_trigger(
    seeded_session: Session,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Eigener TestClient-Setup — wir wollen die Audit-Tabelle der
    seeded session direkt inspizieren."""
    rec = _Recorder(returncode=0)
    _swap_runner(monkeypatch, rec)
    _apply_migrations(settings.database_url)  # idempotent
    app = create_app(settings=settings)
    with TestClient(app) as client:
        from ref4ep.services.partner_service import PartnerService
        from ref4ep.services.person_service import PersonService

        partner = PartnerService(seeded_session).get_by_short_name("JLU")
        if partner is None:
            partner = PartnerService(seeded_session).create(
                name="Test-JLU", short_name="JLU", country="DE"
            )
        admin = PersonService(seeded_session, role="admin").create(
            email=ADMIN_EMAIL,
            display_name="Test admin",
            partner_id=partner.id,
            password=ADMIN_PASSWORD,
            platform_role="admin",
        )
        admin.must_change_password = False
        seeded_session.commit()
        login = client.post(
            "/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
        )
        assert login.status_code == 200
        r = client.post(
            "/api/admin/backup/start",
            json={},
            headers={"X-CSRF-Token": client.cookies.get("ref4ep_csrf") or ""},
        )
        assert r.status_code == 200
    seeded_session.expire_all()
    log = (
        seeded_session.query(AuditLog)
        .filter_by(action="admin.backup.start")
        .order_by(AuditLog.created_at.desc())
        .first()
    )
    assert log is not None
    blob = str(log.details)
    assert '"trigger": "manual_web"' in blob
    assert '"result": "success"' in blob


# Unused-fixture hint — ``patched_settings``/``make_test_settings`` are
# referenced in ``conftest`` chain to keep the file linter-friendly.
_ = make_test_settings  # noqa: F841
