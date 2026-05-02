"""Auth-Helfer: Argon2id, Stdlib-HMAC-Tokens, CSRF."""

from __future__ import annotations

import time

import pytest

from ref4ep.services.auth import (
    MIN_PASSWORD_LEN,
    create_csrf_token,
    create_session_token,
    hash_password,
    needs_rehash,
    read_session_token,
    verify_csrf,
    verify_password,
)

SECRET = "y" * 48


def test_hash_then_verify_succeeds() -> None:
    h = hash_password("strong-pass-1234")
    assert verify_password("strong-pass-1234", h) is True
    assert verify_password("wrong-password!!", h) is False


def test_hash_password_enforces_minimum_length() -> None:
    with pytest.raises(ValueError):
        hash_password("short")
    assert MIN_PASSWORD_LEN == 10


def test_needs_rehash_returns_false_for_fresh_hash() -> None:
    h = hash_password("strong-pass-1234")
    assert needs_rehash(h) is False
    assert needs_rehash("not-a-real-hash") is False


def test_session_token_roundtrip() -> None:
    token = create_session_token("person-abc", SECRET)
    assert token.count(".") == 2
    assert read_session_token(token, SECRET, max_age_seconds=60) == "person-abc"


def test_session_token_rejects_tampered_signature() -> None:
    token = create_session_token("person-abc", SECRET)
    head, ts, sig = token.split(".")
    tampered = f"{head}.{ts}.{'0' * len(sig)}"
    assert read_session_token(tampered, SECRET, 60) is None


def test_session_token_rejects_other_secret() -> None:
    token = create_session_token("person-abc", SECRET)
    assert read_session_token(token, "z" * 48, 60) is None


def test_session_token_rejects_expired() -> None:
    token = create_session_token("person-abc", SECRET)
    # Warten ist im Test unpraktisch — wir prüfen mit max_age=0:
    time.sleep(1)
    assert read_session_token(token, SECRET, max_age_seconds=0) is None


def test_short_secret_raises() -> None:
    with pytest.raises(RuntimeError):
        create_session_token("person", "too-short")


def test_csrf_compare_constant_time() -> None:
    a = create_csrf_token()
    assert verify_csrf(a, a) is True
    assert verify_csrf(a, "anders") is False
    assert verify_csrf(None, a) is False
    assert verify_csrf(a, None) is False
