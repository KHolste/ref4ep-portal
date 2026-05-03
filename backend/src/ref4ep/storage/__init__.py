"""Storage-Interface für das Ref4EP-Dokumentenregister.

Sprint-2-Schnittstelle: bewusst dünn, deckt nur die Operationen ab,
die Sprint 2 wirklich braucht (Upload-Stream, Lese-Stream, Existenz,
Größe). S3-/MinIO-Backends können später ohne Service-Umbau ergänzt
werden, indem dasselbe Protocol implementiert wird.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import BinaryIO, Protocol

__all__ = ["Storage", "StorageWriteResult"]


@dataclass(frozen=True)
class StorageWriteResult:
    """Rückgabe von ``Storage.put_stream`` — server-berechnete Werte."""

    sha256: str
    file_size_bytes: int


class Storage(Protocol):
    """Schnittstelle für Datei-Backends."""

    def put_stream(self, key: str, stream: BinaryIO) -> StorageWriteResult:
        """Schreibt den Stream unter ``key`` ab und liefert SHA-256 und Größe."""

    def open_read(self, key: str) -> BinaryIO:
        """Öffnet einen byte-orientierten Lese-Stream für ``key``."""

    def exists(self, key: str) -> bool:
        """Existiert ein Eintrag unter ``key``?"""

    def size(self, key: str) -> int:
        """Größe des Eintrags in Bytes."""
