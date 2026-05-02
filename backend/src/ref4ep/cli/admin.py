"""Ref4EP-Admin-CLI.

Sprint-0-Skelett: argparse-basierte Subcommands. ``seed`` ist ein
Stub und implementiert noch keine Logik — der echte Seed aus
``docs/mvp_specification.md`` §13 folgt in Sprint 1. Geplante
weitere Subcommands ab Sprint 1:

- ``users create | reset-password | enable | disable | set-role``
- ``partners create``
- ``workpackages create``
- ``memberships add``
"""

from __future__ import annotations

import argparse
import sys

from ref4ep import __version__


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ref4ep-admin",
        description="Ref4EP-Portal Admin-CLI",
    )
    subparsers = parser.add_subparsers(dest="command", required=False)

    subparsers.add_parser("version", help="Version und Python-Info anzeigen")

    seed_parser = subparsers.add_parser(
        "seed",
        help="Initial-Seed laden (Sprint 0: Stub ohne Logik)",
    )
    seed_parser.add_argument(
        "--from",
        dest="from_source",
        choices=["antrag"],
        required=True,
        help="Quelle des Seeds; in Sprint 0 nur 'antrag'",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        return 0

    if args.command == "version":
        print(f"ref4ep {__version__}")
        print(f"python {sys.version.split()[0]}")
        return 0

    if args.command == "seed":
        print(
            "Sprint-0-Stub: Seed-Logik wird in Sprint 1 implementiert. "
            "Quelldatei (geplant): "
            "backend/src/ref4ep/cli/seed_data/antrag_initial.yaml"
        )
        return 0

    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
