"""Manueller Admin-Backup-Trigger (Block 0033).

Der Webprozess startet ausschließlich den fest definierten
``ref4ep-backup.service`` über ``subprocess.run`` mit fester
Argumentliste; weder dynamische Befehle noch ``shell=True``.

Die exakte Argumentliste kommt aus
``Settings.backup_trigger_command``. Der Service ist nicht für die
Backup-Logik selbst zuständig — die liegt im systemd-Service auf dem
Server (siehe ``docs/server_operations.md``).

Audit:
- ``admin.backup.start`` mit ``entity_type='backup'``,
  ``entity_id`` = Trigger-UUID, ``after`` enthält
  ``trigger='manual_web'``, ``result``, ``exit_code`` und (gekürzt)
  ``stderr_excerpt``. Keine Pfade oder Secrets.
"""

from __future__ import annotations

import subprocess
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from ref4ep.services.audit_logger import AuditLogger

# Maximale Länge eines im Audit/Antwort-Feld zurückgegebenen
# Fehlerausschnitts. Genug für eine sprechende Meldung, aber nicht
# genug, um längere Pfadlisten oder Stacktraces durchzureichen.
_STDERR_EXCERPT_LIMIT = 200

# Default-Runner-Typ. Echte Aufrufer geben ``subprocess.run`` mit
# allen üblichen Keyword-Argumenten weiter; Tests injizieren einen
# Fake.
RunnerCallable = Callable[..., subprocess.CompletedProcess]


@dataclass(frozen=True)
class BackupTriggerResult:
    triggered_at: datetime
    result: str  # "success" | "failure"
    exit_code: int
    message: str


def _excerpt(text: str | bytes | None) -> str:
    if text is None:
        return ""
    if isinstance(text, bytes):
        try:
            text = text.decode("utf-8", errors="replace")
        except Exception:  # noqa: BLE001 — defensiv
            text = ""
    text = (text or "").strip()
    if len(text) > _STDERR_EXCERPT_LIMIT:
        return text[:_STDERR_EXCERPT_LIMIT] + " …"
    return text


class BackupTriggerService:
    """Triggert genau einen festen systemd-Service.

    ``runner`` ist standardmäßig ``subprocess.run``. Tests injizieren
    eine Fake-Funktion, die die übergebenen Argumente protokolliert.
    """

    def __init__(
        self,
        *,
        audit: AuditLogger,
        command: Sequence[str],
        timeout_seconds: int = 30,
        runner: RunnerCallable | None = None,
    ) -> None:
        if not command:
            raise ValueError("Backup-Trigger-Befehl darf nicht leer sein.")
        self._audit = audit
        self._command = tuple(command)
        self._timeout = int(timeout_seconds)
        self._runner: RunnerCallable = runner or subprocess.run

    @property
    def command(self) -> tuple[str, ...]:
        return self._command

    @property
    def timeout_seconds(self) -> int:
        return self._timeout

    def start(self) -> BackupTriggerResult:
        """Startet den Backup-Service und liefert ein strukturiertes
        Ergebnis. Schreibt **immer** einen Audit-Eintrag — auch bei
        Fehler oder Timeout."""
        triggered_at = datetime.now(tz=UTC)
        trigger_id = str(uuid.uuid4())
        result_label: str
        exit_code: int
        message: str
        stderr_excerpt = ""

        try:
            completed = self._runner(
                list(self._command),
                capture_output=True,
                timeout=self._timeout,
                check=False,
                shell=False,
            )
        except subprocess.TimeoutExpired:
            result_label = "failure"
            exit_code = -1
            message = f"Backup-Start nach {self._timeout}s ohne Antwort abgebrochen."
            self._log_audit(
                trigger_id=trigger_id,
                triggered_at=triggered_at,
                result=result_label,
                exit_code=exit_code,
                stderr_excerpt="timeout",
            )
            return BackupTriggerResult(
                triggered_at=triggered_at,
                result=result_label,
                exit_code=exit_code,
                message=message,
            )
        except FileNotFoundError as exc:
            result_label = "failure"
            exit_code = -2
            message = f"Backup-Befehl nicht gefunden: {_excerpt(str(exc))}"
            self._log_audit(
                trigger_id=trigger_id,
                triggered_at=triggered_at,
                result=result_label,
                exit_code=exit_code,
                stderr_excerpt=_excerpt(str(exc)),
            )
            return BackupTriggerResult(
                triggered_at=triggered_at,
                result=result_label,
                exit_code=exit_code,
                message=message,
            )
        except OSError as exc:
            result_label = "failure"
            exit_code = -3
            message = f"Backup-Start fehlgeschlagen: {_excerpt(str(exc))}"
            self._log_audit(
                trigger_id=trigger_id,
                triggered_at=triggered_at,
                result=result_label,
                exit_code=exit_code,
                stderr_excerpt=_excerpt(str(exc)),
            )
            return BackupTriggerResult(
                triggered_at=triggered_at,
                result=result_label,
                exit_code=exit_code,
                message=message,
            )

        exit_code = int(completed.returncode)
        stderr_excerpt = _excerpt(getattr(completed, "stderr", b""))
        if exit_code == 0:
            result_label = "success"
            message = "Backup wurde gestartet."
        else:
            result_label = "failure"
            message = f"Backup-Start scheiterte (Exit-Code {exit_code})." + (
                f" Detail: {stderr_excerpt}" if stderr_excerpt else ""
            )

        self._log_audit(
            trigger_id=trigger_id,
            triggered_at=triggered_at,
            result=result_label,
            exit_code=exit_code,
            stderr_excerpt=stderr_excerpt,
        )
        return BackupTriggerResult(
            triggered_at=triggered_at,
            result=result_label,
            exit_code=exit_code,
            message=message,
        )

    def _log_audit(
        self,
        *,
        trigger_id: str,
        triggered_at: datetime,
        result: str,
        exit_code: int,
        stderr_excerpt: str,
    ) -> None:
        after: dict[str, Any] = {
            "trigger": "manual_web",
            "result": result,
            "exit_code": exit_code,
            "triggered_at": triggered_at,
        }
        if stderr_excerpt:
            after["stderr_excerpt"] = stderr_excerpt
        self._audit.log(
            "admin.backup.start",
            entity_type="backup",
            entity_id=trigger_id,
            after=after,
        )


__all__ = ["BackupTriggerResult", "BackupTriggerService"]
