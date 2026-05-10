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

# Block 0036 — Versionsnotiz ist optional. Frühere Pflicht-
# Mindestlänge entfällt; der Service setzt bei leerer Eingabe einen
# neutralen Default („Initialer Upload" bzw. „Neue Version
# hochgeladen"), siehe ``DocumentVersionService.upload_new_version``.
CHANGE_NOTE_DEFAULT_FIRST = "Initialer Upload"
CHANGE_NOTE_DEFAULT_NEXT = "Neue Version hochgeladen"

# Block 0028 — engere MIME-Whitelist nur für Fotos (Schnappschüsse aus
# der Vakuumkammer o. ä.). Bewusst kein PDF/Office hier: das wäre eine
# fachliche Type-Verwechslung — formale Unterlagen gehören als Document.
PHOTO_MIME_WHITELIST: frozenset[str] = frozenset({"image/png", "image/jpeg"})

_UUID_PATTERN = r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
_STORAGE_KEY_RE = re.compile(rf"^documents/{_UUID_PATTERN}/{_UUID_PATTERN}\.bin$")
_PHOTO_STORAGE_KEY_RE = re.compile(rf"^photos/{_UUID_PATTERN}/{_UUID_PATTERN}\.bin$")
_PHOTO_THUMBNAIL_STORAGE_KEY_RE = re.compile(
    rf"^photos/{_UUID_PATTERN}/{_UUID_PATTERN}\.thumb\.bin$"
)


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


def validate_change_note(note: str | None) -> str:
    """Trimmt Whitespace.

    Block 0036: Die frühere Pflicht-Mindestlänge entfällt. Aufrufer
    erhalten den getrimmten String — gegebenenfalls leer. Den
    Default-Text setzt der Service in
    :meth:`DocumentVersionService.upload_new_version`.
    """
    return (note or "").strip()


def compute_storage_key(document_id: str, version_id: str) -> str:
    return f"documents/{document_id}/{version_id}.bin"


def validate_storage_key(key: str) -> None:
    if not _STORAGE_KEY_RE.match(key):
        raise ValueError(f"Storage-Key ungültig: {key!r}")


# ---- Block 0028 — Foto-Upload-Helfer ---------------------------------


def validate_photo_mime(mime: str) -> None:
    if mime not in PHOTO_MIME_WHITELIST:
        raise ValueError(f"Foto-MIME-Typ nicht erlaubt: {mime!r} — nur PNG und JPEG.")


def compute_photo_storage_key(campaign_id: str, photo_id: str) -> str:
    return f"photos/{campaign_id}/{photo_id}.bin"


def validate_photo_storage_key(key: str) -> None:
    if not _PHOTO_STORAGE_KEY_RE.match(key):
        raise ValueError(f"Foto-Storage-Key ungültig: {key!r}")


# ---- Block 0032 — Thumbnail-Storage-Key ------------------------------


def compute_photo_thumbnail_storage_key(campaign_id: str, photo_id: str) -> str:
    return f"photos/{campaign_id}/{photo_id}.thumb.bin"


def validate_photo_thumbnail_storage_key(key: str) -> None:
    if not _PHOTO_THUMBNAIL_STORAGE_KEY_RE.match(key):
        raise ValueError(f"Foto-Thumbnail-Storage-Key ungültig: {key!r}")
