"""CLI-Smoke-Tests."""

from __future__ import annotations

import subprocess
import sys


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "ref4ep.cli.admin", *args],
        capture_output=True,
        text=True,
    )


def test_help_lists_subcommands() -> None:
    result = _run("--help")
    assert result.returncode == 0
    assert "seed" in result.stdout
    assert "version" in result.stdout


def test_version_prints_version_string() -> None:
    result = _run("version")
    assert result.returncode == 0
    assert "0.0.1" in result.stdout
    assert "python" in result.stdout.lower()


def test_seed_from_antrag_is_a_stub_returning_zero() -> None:
    result = _run("seed", "--from", "antrag")
    assert result.returncode == 0
    assert "Sprint-0-Stub" in result.stdout


def test_seed_from_unknown_value_fails() -> None:
    result = _run("seed", "--from", "unbekannt")
    assert result.returncode != 0
