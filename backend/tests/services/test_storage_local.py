"""LocalFileStorage."""

from __future__ import annotations

import hashlib
import io
from pathlib import Path

import pytest

from ref4ep.storage.local import LocalFileStorage

_DOC_UUID = "11111111-1111-1111-1111-111111111111"
_VER_UUID = "22222222-2222-2222-2222-222222222222"


def _key(doc: str = _DOC_UUID, ver: str = _VER_UUID) -> str:
    return f"documents/{doc}/{ver}.bin"


def test_put_stream_writes_and_reports_hash_size(tmp_path: Path) -> None:
    storage = LocalFileStorage(tmp_path)
    payload = b"Hallo Ref4EP!" * 100
    expected_hash = hashlib.sha256(payload).hexdigest()
    result = storage.put_stream(_key(), io.BytesIO(payload))
    assert result.sha256 == expected_hash
    assert result.file_size_bytes == len(payload)


def test_open_read_returns_byte_identical_content(tmp_path: Path) -> None:
    storage = LocalFileStorage(tmp_path)
    payload = b"binary content \x00\x01\x02"
    storage.put_stream(_key(), io.BytesIO(payload))
    with storage.open_read(_key()) as fh:
        read_back = fh.read()
    assert read_back == payload


def test_path_traversal_is_rejected(tmp_path: Path) -> None:
    storage = LocalFileStorage(tmp_path)
    with pytest.raises(PermissionError):
        storage.put_stream("../escape.bin", io.BytesIO(b"x"))


def test_open_read_missing_file_raises(tmp_path: Path) -> None:
    storage = LocalFileStorage(tmp_path)
    with pytest.raises(FileNotFoundError):
        storage.open_read(_key())


def test_size_reports_bytes(tmp_path: Path) -> None:
    storage = LocalFileStorage(tmp_path)
    storage.put_stream(_key(), io.BytesIO(b"abcde"))
    assert storage.size(_key()) == 5


def test_exists_true_after_put(tmp_path: Path) -> None:
    storage = LocalFileStorage(tmp_path)
    assert storage.exists(_key()) is False
    storage.put_stream(_key(), io.BytesIO(b"a"))
    assert storage.exists(_key()) is True


def test_temp_file_cleaned_on_inner_exception(tmp_path: Path) -> None:
    storage = LocalFileStorage(tmp_path)

    class BoomStream:
        def __init__(self) -> None:
            self._first = True

        def read(self, n: int) -> bytes:
            if self._first:
                self._first = False
                return b"halb"
            raise OSError("Lesefehler")

    with pytest.raises(OSError):
        storage.put_stream(_key(), BoomStream())

    # Im Zielverzeichnis darf nichts liegen — auch keine .upload-*-Reste.
    target_dir = tmp_path / "documents" / "11111111-1111-1111-1111-111111111111"
    leftovers = list(target_dir.iterdir()) if target_dir.exists() else []
    assert leftovers == []
