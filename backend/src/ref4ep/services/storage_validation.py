"""Validatoren und Helfer rund um Datei-Uploads.

Sprint-2-Konstanten:
- ``MIME_WHITELIST``: erlaubte MIME-Typen.
- ``compute_storage_key`` / ``validate_storage_key``: Pfad-Schema
  ``documents/{document_id}/{version_id}.bin``.

``Settings.max_upload_mb`` (Sprint-0-Setting) liefert das Größenlimit
in MiB; ``validate_size`` prüft gegen Bytes.
"""

from __future__ import annotations

import re

MIME_WHITELIST: frozenset[str] = frozenset(
    {
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "application/zip",
        "image/png",
        "image/jpeg",
    }
)

CHANGE_NOTE_MIN_LEN = 5

_UUID_PATTERN = r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
_STORAGE_KEY_RE = re.compile(rf"^documents/{_UUID_PATTERN}/{_UUID_PATTERN}\.bin$")


def validate_mime(mime: str) -> None:
    if mime not in MIME_WHITELIST:
        raise ValueError(f"MIME-Typ nicht erlaubt: {mime!r}")


def validate_size(size_bytes: int, max_bytes: int) -> None:
    if size_bytes <= 0:
        raise ValueError("Datei ist leer.")
    if size_bytes > max_bytes:
        raise ValueError(
            f"Datei zu groß: {size_bytes} Bytes überschreitet Limit von {max_bytes} Bytes."
        )


def validate_change_note(note: str) -> str:
    """Trimmt Whitespace und erzwingt die Mindestlänge."""
    cleaned = (note or "").strip()
    if len(cleaned) < CHANGE_NOTE_MIN_LEN:
        raise ValueError(f"Änderungsnotiz muss mindestens {CHANGE_NOTE_MIN_LEN} Zeichen enthalten.")
    return cleaned


def compute_storage_key(document_id: str, version_id: str) -> str:
    return f"documents/{document_id}/{version_id}.bin"


def validate_storage_key(key: str) -> None:
    if not _STORAGE_KEY_RE.match(key):
        raise ValueError(f"Storage-Key ungültig: {key!r}")
