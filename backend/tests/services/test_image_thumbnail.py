"""Tests für ``services.image_thumbnail.generate_thumbnail`` (Block 0032)."""

from __future__ import annotations

from io import BytesIO

import pytest
from PIL import Image

from ref4ep.services.image_thumbnail import (
    MAX_THUMBNAIL_SOURCE_BYTES,
    THUMBNAIL_MAX_EDGE,
    ThumbnailError,
    generate_thumbnail,
)


def _jpeg_bytes(width: int, height: int, color: tuple[int, int, int] = (200, 100, 50)) -> bytes:
    image = Image.new("RGB", (width, height), color)
    buf = BytesIO()
    image.save(buf, format="JPEG", quality=90)
    return buf.getvalue()


def _png_with_alpha(width: int, height: int) -> bytes:
    image = Image.new("RGBA", (width, height), (255, 0, 0, 128))  # halbtransparent
    buf = BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()


def _jpeg_with_exif_orientation_6(width: int, height: int) -> bytes:
    """JPEG mit EXIF-Orientation=6 (90° im Uhrzeigersinn drehen)."""
    image = Image.new("RGB", (width, height), (50, 200, 100))
    exif = image.getexif()
    exif[0x0112] = 6  # Orientation
    buf = BytesIO()
    image.save(buf, format="JPEG", exif=exif.tobytes())
    return buf.getvalue()


def test_jpeg_thumbnail_is_jpeg_and_within_max_edge() -> None:
    src = _jpeg_bytes(2000, 1000)
    thumb_bytes, mime = generate_thumbnail(src)
    assert mime == "image/jpeg"
    with Image.open(BytesIO(thumb_bytes)) as out:
        assert max(out.size) <= THUMBNAIL_MAX_EDGE
        assert out.format == "JPEG"


def test_thumbnail_is_smaller_than_source_for_realistic_input() -> None:
    src = _jpeg_bytes(3000, 2000, color=(120, 60, 200))
    thumb_bytes, _ = generate_thumbnail(src)
    assert len(thumb_bytes) < len(src)


def test_png_with_alpha_keeps_transparency_as_png() -> None:
    src = _png_with_alpha(900, 600)
    thumb_bytes, mime = generate_thumbnail(src)
    assert mime == "image/png"
    with Image.open(BytesIO(thumb_bytes)) as out:
        assert out.mode in ("RGBA", "LA", "P")
        assert out.format == "PNG"
        # Alpha-Kanal vorhanden, mindestens ein nicht-opakes Pixel.
        if out.mode == "RGBA":
            alphas = {a for _r, _g, _b, a in out.getdata()}
            assert any(a < 255 for a in alphas)


def test_corrupted_image_raises_thumbnail_error() -> None:
    with pytest.raises(ThumbnailError):
        generate_thumbnail(b"not an image at all")


def test_empty_source_raises_thumbnail_error() -> None:
    with pytest.raises(ThumbnailError):
        generate_thumbnail(b"")


def test_oversized_source_raises_thumbnail_error() -> None:
    huge = b"\x00" * (MAX_THUMBNAIL_SOURCE_BYTES + 1)
    with pytest.raises(ThumbnailError, match="zu groß"):
        generate_thumbnail(huge)


def test_exif_orientation_is_applied() -> None:
    """Quellbild ist 600×300 (breiter als hoch). Mit Orientation=6
    soll der Decoder es als 300×600 (höher als breit) interpretieren;
    das Thumbnail muss diese Drehung beibehalten."""
    src = _jpeg_with_exif_orientation_6(600, 300)
    thumb_bytes, _ = generate_thumbnail(src)
    with Image.open(BytesIO(thumb_bytes)) as out:
        w, h = out.size
        # Nach exif_transpose ist die Höhe größer als die Breite.
        assert h > w


def test_rgb_jpeg_is_re_encoded_as_jpeg() -> None:
    src = _jpeg_bytes(1024, 768)
    thumb_bytes, mime = generate_thumbnail(src)
    assert mime == "image/jpeg"
    # Output enthält JPEG-Magic-Bytes.
    assert thumb_bytes[:3] == b"\xff\xd8\xff"
