"""Thumbnail-Erzeugung für Foto-Uploads (Block 0032).

Reine Hilfs-Funktionen — keine Storage-/DB-Kopplung. Aufrufer:
``TestCampaignPhotoService.upload``.

Designentscheidungen:
- ``THUMBNAIL_MAX_EDGE = 480`` Pixel pro Achse (proportional skaliert).
- Quellen größer als ``MAX_THUMBNAIL_SOURCE_BYTES`` werden bewusst
  abgelehnt, um RAM-Spitzen beim Decode sehr großer Originale zu
  vermeiden. Der Upload selbst läuft trotzdem durch (Aufrufer fängt
  die Exception ab).
- ``Image.MAX_IMAGE_PIXELS = 50_000_000`` als Decompression-Bomb-Cap.
- EXIF-Orientierung wird via ``ImageOps.exif_transpose`` beim Lesen
  korrigiert; ins Thumbnail-Output landet KEIN EXIF (kein ``exif=``
  beim ``save``).
- MIME-Strategie: Quelle mit Alpha → PNG-Thumbnail (Transparenz
  bleibt); sonst → JPEG-Thumbnail (kleiner, progressive, optimiert).
"""

from __future__ import annotations

from io import BytesIO

from PIL import Image, ImageOps, UnidentifiedImageError

# Decompression-Bomb-Schutz: Bilder über 50 MP werden von Pillow
# abgewiesen. Aktuelle Handyfotos liegen klar darunter.
Image.MAX_IMAGE_PIXELS = 50_000_000

THUMBNAIL_MAX_EDGE = 480
MAX_THUMBNAIL_SOURCE_BYTES = 30 * 1024 * 1024
JPEG_QUALITY = 82


class ThumbnailError(ValueError):
    """Wird geworfen, wenn ein Thumbnail nicht erzeugt werden kann.

    Aufrufer (``TestCampaignPhotoService.upload``) fängt die Exception
    ab und lässt den Upload ohne Thumbnail durchlaufen — die
    Originaldatei bleibt intakt.
    """


def _has_alpha(image: Image.Image) -> bool:
    if image.mode in ("RGBA", "LA"):
        return True
    if image.mode == "P":
        # Palette mit Transparenzeintrag.
        return "transparency" in image.info
    return False


def generate_thumbnail(source_bytes: bytes) -> tuple[bytes, str]:
    """Erzeugt ein Thumbnail aus den übergebenen Bilddaten.

    Liefert ``(thumbnail_bytes, mime_type)``. Wirft ``ThumbnailError``,
    wenn die Quelle zu groß ist, korrupt ist oder Pillow sie nicht
    decodieren kann.
    """
    if not source_bytes:
        raise ThumbnailError("Leere Quelldatei.")
    if len(source_bytes) > MAX_THUMBNAIL_SOURCE_BYTES:
        raise ThumbnailError(
            f"Quelle zu groß für Thumbnail-Erzeugung: "
            f"{len(source_bytes)} Bytes überschreitet Limit von "
            f"{MAX_THUMBNAIL_SOURCE_BYTES} Bytes."
        )

    try:
        with Image.open(BytesIO(source_bytes)) as image:
            # ``exif_transpose`` liefert eine neue Image-Instanz mit
            # angewandter Orientierung (gibt das Original zurück, wenn
            # keine EXIF-Orientation gesetzt ist).
            oriented = ImageOps.exif_transpose(image)
            if oriented is None:
                oriented = image
            # In-place-Skalierung; ``thumbnail`` behält Seitenverhältnis.
            oriented.thumbnail(
                (THUMBNAIL_MAX_EDGE, THUMBNAIL_MAX_EDGE),
                Image.Resampling.LANCZOS,
            )
            buffer = BytesIO()
            if _has_alpha(oriented):
                # Alpha erhalten — als PNG.
                if oriented.mode == "P":
                    oriented = oriented.convert("RGBA")
                oriented.save(buffer, format="PNG", optimize=True)
                return buffer.getvalue(), "image/png"
            # Sonst: JPEG, da deutlich kleiner.
            if oriented.mode != "RGB":
                oriented = oriented.convert("RGB")
            oriented.save(
                buffer,
                format="JPEG",
                quality=JPEG_QUALITY,
                optimize=True,
                progressive=True,
            )
            return buffer.getvalue(), "image/jpeg"
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise ThumbnailError(f"Thumbnail-Erzeugung fehlgeschlagen: {exc}") from exc
