"""Kleine, library-freie Eingabe-Validatoren für Service-Layer.

Bewusst ohne externe Abhängigkeiten (kein ``email-validator``):
das Konsortium braucht eine plausible Schreibweise, keine
RFC-vollständige Prüfung. Strenge Validierung würde alte
Datenbestände blockieren ohne fachlichen Mehrwert.
"""

from __future__ import annotations


def validate_email(value: str | None, field: str) -> None:
    """Erwartet ``user@domain`` ohne Leerzeichen.

    Leere Strings und ``None`` sind erlaubt — die meisten Aufrufer
    haben optionale Felder. Die Prüfung wird nach ``normalise_text``
    ausgeführt, daher wird hier nur der echte Wert geprüft.
    """
    if value is None or value == "":
        return
    if " " in value or "@" not in value:
        raise ValueError(f"{field}: ungültige E-Mail-Adresse.")
    local, _, domain = value.partition("@")
    if not local or not domain or "." not in domain:
        raise ValueError(f"{field}: ungültige E-Mail-Adresse.")


def validate_country_code(value: str | None, field: str) -> None:
    """ISO-3166-1-alpha-2 — zwei Buchstaben, sonst Fehler."""
    if value is None or value == "":
        return
    if len(value) != 2 or not value.isalpha():
        raise ValueError(f"{field}: erwartet ISO-3166-1-alpha-2 (zwei Buchstaben).")


def normalise_text(value: str | None) -> str | None:
    """Trim. Leerstring → ``None``, damit DB konsistent ``NULL`` speichert."""
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None
