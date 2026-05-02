"""Auth-Helfer: Argon2id-Passwort-Hashing, HMAC-signierte Session-Tokens
und Double-Submit-CSRF-Tokens.

Session-Token-Schema entspricht 1:1 dem Referenzsystem
``jluspaceforge-reference/src/lab_management/api/deps.py`` (siehe
``create_session_token`` / ``verify_session_token``):
``<person_id>.<unix_ts>.<hex_signature>``. **Keine** itsdangerous-
oder andere Auth-Zusatzbibliothek — nur ``argon2-cffi`` plus Stdlib.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import time

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

MIN_SESSION_SECRET_LEN = 32
MIN_PASSWORD_LEN = 10

_hasher = PasswordHasher()


# ---------------------------------------------------------------------------
# Passwort-Hashing
# ---------------------------------------------------------------------------


def hash_password(plain: str) -> str:
    if len(plain) < MIN_PASSWORD_LEN:
        raise ValueError(f"Passwort muss mindestens {MIN_PASSWORD_LEN} Zeichen lang sein.")
    return _hasher.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return _hasher.verify(hashed, plain)
    except (VerifyMismatchError, InvalidHashError, ValueError, TypeError):
        return False


def needs_rehash(hashed: str) -> bool:
    try:
        return _hasher.check_needs_rehash(hashed)
    except (InvalidHashError, ValueError):
        return False


# ---------------------------------------------------------------------------
# Session-Tokens (HMAC-SHA256, Stdlib, analog Referenz)
# ---------------------------------------------------------------------------


def _require_secret(secret: str) -> None:
    if not secret or len(secret) < MIN_SESSION_SECRET_LEN:
        raise RuntimeError(
            "REF4EP_SESSION_SECRET fehlt oder ist zu kurz "
            f"(mindestens {MIN_SESSION_SECRET_LEN} Zeichen erforderlich)."
        )


def create_session_token(person_id: str, secret: str) -> str:
    _require_secret(secret)
    ts = str(int(time.time()))
    payload = f"{person_id}.{ts}"
    sig = hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{payload}.{sig}"


def read_session_token(token: str, secret: str, max_age_seconds: int) -> str | None:
    """Validiere Token; gib `person_id` oder `None` (ungültig/abgelaufen) zurück."""
    if not token or not secret:
        return None
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        person_id, ts_str, sig = parts
        payload = f"{person_id}.{ts_str}"
        expected = hmac.new(
            secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(sig, expected):
            return None
        ts = int(ts_str)
        if time.time() - ts > max_age_seconds:
            return None
        return person_id
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# CSRF (Double-Submit)
# ---------------------------------------------------------------------------


def create_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def verify_csrf(cookie_token: str | None, header_token: str | None) -> bool:
    if not cookie_token or not header_token:
        return False
    return hmac.compare_digest(cookie_token, header_token)
