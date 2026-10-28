#!/usr/bin/env bash
# Erzeugt die Lock-Dateien mit exakten Paketversionen.
#
#   requirements.txt      Laufzeit (Server)
#   requirements-dev.txt  Laufzeit + Tests/Lint + PostgreSQL-Treiber (CI, lokal)
#
# Aufruf aus dem Ordner backend (braucht ``uv``: pip install uv):
#
#   scripts/lock_dependencies.sh            # nur an pyproject.toml angleichen,
#                                           # bestehende Versionen bleiben
#   scripts/lock_dependencies.sh --upgrade  # bewusst auf neueste Versionen heben
#   scripts/lock_dependencies.sh --check    # nur prüfen (CI), Exit 1 wenn veraltet
#
# Die Dateien sind plattformübergreifend (--universal): dieselbe Datei gilt
# für den Linux-Server, die CI und Windows. Zielversion ist Python 3.12 wie
# auf dem Server.
set -euo pipefail
cd "$(dirname "$0")/.."

mode="${1:-}"
extra=()
[[ "$mode" == "--upgrade" ]] && extra=(--upgrade)

compile() {
  uv pip compile pyproject.toml --universal --python-version 3.12 --no-annotate \
    "${extra[@]}" -q -o requirements.txt
  uv pip compile pyproject.toml --extra dev --extra postgres --universal \
    --python-version 3.12 --no-annotate -c requirements.txt -q -o requirements-dev.txt
}

if [[ "$mode" == "--check" ]]; then
  # Neu erzeugen, vergleichen, Originale in jedem Fall zurücklegen.
  tmp="$(mktemp -d)"
  cp requirements.txt requirements-dev.txt "$tmp/"
  restore() { cp "$tmp/requirements.txt" "$tmp/requirements-dev.txt" .; }
  trap restore EXIT
  compile
  if ! diff -q "$tmp/requirements.txt" requirements.txt >/dev/null \
    || ! diff -q "$tmp/requirements-dev.txt" requirements-dev.txt >/dev/null; then
    diff -u "$tmp/requirements.txt" requirements.txt || true
    diff -u "$tmp/requirements-dev.txt" requirements-dev.txt || true
    echo "Lock-Dateien passen nicht zu pyproject.toml — scripts/lock_dependencies.sh ausführen."
    exit 1
  fi
  echo "Lock-Dateien sind aktuell."
  exit 0
fi

compile
echo "requirements.txt und requirements-dev.txt geschrieben."
