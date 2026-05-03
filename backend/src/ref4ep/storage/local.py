"""Lokales Filesystem-Backend für das Storage-Interface.

Schreibt jedes Objekt unter ``{REF4EP_STORAGE_DIR}/{key}``. Der ``key``
folgt dem Schema ``documents/<document_id>/<version_id>.bin`` (siehe
``services/storage_validation.py``); jeder andere ``key`` wird vor
dem Zugriff abgelehnt (Path-Traversal-Schutz).

Sprint 2 implementiert ausschließlich dieses Backend. S3/MinIO wird
später ergänzt.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
from pathlib import Path
from typing import BinaryIO

from ref4ep.storage import Storage, StorageWriteResult

CHUNK_SIZE = 1024 * 1024  # 1 MiB


class LocalFileStorage(Storage):
    def __init__(self, base_dir: str | Path) -> None:
        self._base = Path(base_dir).resolve()
        self._base.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ #
    # Pfad-Auflösung mit Traversal-Schutz                                #
    # ------------------------------------------------------------------ #

    def _resolve(self, key: str) -> Path:
        # Storage-Key wird vor jedem Aufruf von services/storage_validation
        # geprüft; hier nur die zusätzliche Path-Traversal-Sicherung.
        candidate = (self._base / key).resolve()
        try:
            candidate.relative_to(self._base)
        except ValueError as exc:
            raise PermissionError(f"Storage-Key verlässt das Basisverzeichnis: {key!r}") from exc
        return candidate

    # ------------------------------------------------------------------ #
    # Storage-Protocol                                                   #
    # ------------------------------------------------------------------ #

    def put_stream(self, key: str, stream: BinaryIO) -> StorageWriteResult:
        target = self._resolve(key)
        target.parent.mkdir(parents=True, exist_ok=True)

        hasher = hashlib.sha256()
        size = 0

        # In temporäre Datei im selben Verzeichnis schreiben, dann atomar
        # umbenennen — schützt vor halb-geschriebenen Zieldateien.
        fd, tmp_path = tempfile.mkstemp(prefix=".upload-", dir=target.parent)
        try:
            with os.fdopen(fd, "wb") as out:
                while True:
                    chunk = stream.read(CHUNK_SIZE)
                    if not chunk:
                        break
                    hasher.update(chunk)
                    size += len(chunk)
                    out.write(chunk)
            shutil.move(tmp_path, target)
        except Exception:
            # Aufräumen, falls die Temp-Datei noch herumliegt.
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

        return StorageWriteResult(sha256=hasher.hexdigest(), file_size_bytes=size)

    def open_read(self, key: str) -> BinaryIO:
        path = self._resolve(key)
        if not path.is_file():
            raise FileNotFoundError(f"Storage-Eintrag fehlt: {key!r}")
        return path.open("rb")

    def exists(self, key: str) -> bool:
        try:
            return self._resolve(key).is_file()
        except PermissionError:
            return False

    def size(self, key: str) -> int:
        path = self._resolve(key)
        if not path.is_file():
            raise FileNotFoundError(f"Storage-Eintrag fehlt: {key!r}")
        return path.stat().st_size
