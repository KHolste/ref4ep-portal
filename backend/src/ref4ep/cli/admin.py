"""Ref4EP-Admin-CLI.

Sprint-1-Funktionsumfang gemäß ``docs/sprint1_implementation_plan.md`` §6:

- ``ref4ep-admin seed --from antrag`` lädt den Initial-Seed
  idempotent (5 Partner, 35 Workpackage-Einträge: 8 Hauptarbeits-
  pakete + 27 Unterarbeitspakete).
- ``ref4ep-admin partner {list,create}``
- ``ref4ep-admin workpackage {list,create}``
- ``ref4ep-admin person {list,create,reset-password,set-role,enable,disable}``
- ``ref4ep-admin membership {add,remove}``

Passwörter werden grundsätzlich über ``getpass`` abgefragt — nie über
Argumente. Schreiboperationen laufen mit ``role="admin"`` und
``person_id="cli-admin"`` (Marker für künftige Audit-Einträge,
Sprint 3).
"""

from __future__ import annotations

import argparse
import getpass
import sys
from collections.abc import Callable, Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from ref4ep import __version__
from ref4ep.api.config import get_settings
from ref4ep.services.audit_logger import AuditLogger
from ref4ep.services.partner_service import PartnerService
from ref4ep.services.person_service import PersonService
from ref4ep.services.seed_service import SeedService
from ref4ep.services.workpackage_service import WorkpackageService

CLI_ACTOR = "cli-admin"


# ---------------------------------------------------------------------------
# Session-Helfer
# ---------------------------------------------------------------------------


@contextmanager
def _session_scope() -> Iterator[Session]:
    settings = get_settings()
    engine = create_engine(settings.database_url, future=True)
    SessionLocal = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
        future=True,
        expire_on_commit=False,
    )
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _admin_services(session: Session) -> tuple[PartnerService, PersonService, WorkpackageService]:
    audit = AuditLogger(session, actor_label=CLI_ACTOR)
    p = PartnerService(session, role="admin", person_id=CLI_ACTOR, audit=audit)
    pe = PersonService(session, role="admin", person_id=CLI_ACTOR, audit=audit)
    w = WorkpackageService(session, role="admin", person_id=CLI_ACTOR, audit=audit)
    return p, pe, w


# ---------------------------------------------------------------------------
# Tabellen-Druck-Helfer (kein zusätzliches Paket)
# ---------------------------------------------------------------------------


def _print_table(rows: list[dict[str, object]], columns: list[str]) -> None:
    if not rows:
        print("(leer)")
        return
    widths = {col: max(len(col), *(len(str(r.get(col, ""))) for r in rows)) for col in columns}
    header = "  ".join(col.ljust(widths[col]) for col in columns)
    print(header)
    print("  ".join("-" * widths[col] for col in columns))
    for row in rows:
        print("  ".join(str(row.get(col, "")).ljust(widths[col]) for col in columns))


# ---------------------------------------------------------------------------
# Subcommand-Implementierungen
# ---------------------------------------------------------------------------


def _cmd_version(_: argparse.Namespace) -> int:
    print(f"ref4ep {__version__}")
    print(f"python {sys.version.split()[0]}")
    return 0


def _cmd_seed(args: argparse.Namespace) -> int:
    with _session_scope() as session:
        result = SeedService(session).apply_initial_seed(source=args.from_source)
    print(f"Seed-Quelle: {result['source']}")
    print(
        f"Partner: {result['partners_added']} angelegt, {result['partners_skipped']} übersprungen"
    )
    added = result["workpackages_added"]
    skipped = result["workpackages_skipped"]
    breakdown = "(8 Hauptarbeitspakete + 27 Unterarbeitspakete)"
    if added >= skipped:
        print(f"Workpackages: {added} angelegt {breakdown}, {skipped} übersprungen")
    else:
        print(f"Workpackages: {added} angelegt, {skipped} übersprungen {breakdown}")
    return 0


# ---- partner --------------------------------------------------------------


def _cmd_partner_list(_: argparse.Namespace) -> int:
    with _session_scope() as session:
        partners, _, _ = _admin_services(session)
        rows = [
            {
                "short_name": p.short_name,
                "name": p.name,
                "country": p.country,
                "website": p.website or "",
            }
            for p in partners.list_partners()
        ]
    _print_table(rows, ["short_name", "name", "country", "website"])
    return 0


def _cmd_partner_create(args: argparse.Namespace) -> int:
    with _session_scope() as session:
        partners, _, _ = _admin_services(session)
        partner = partners.create(
            name=args.name,
            short_name=args.short_name,
            country=args.country,
            website=args.website,
        )
    print(f"Partner angelegt: {partner.short_name} — {partner.name}")
    return 0


# ---- workpackage ----------------------------------------------------------


def _cmd_workpackage_list(_: argparse.Namespace) -> int:
    with _session_scope() as session:
        _, _, wps = _admin_services(session)
        rows = []
        for wp in wps.list_workpackages():
            parent_code = ""
            if wp.parent_workpackage_id:
                parent = wps.get_by_id(wp.parent_workpackage_id)
                if parent is not None:
                    parent_code = parent.code
            rows.append(
                {
                    "code": wp.code,
                    "title": wp.title,
                    "parent": parent_code,
                    "lead": wp.lead_partner.short_name,
                }
            )
    _print_table(rows, ["code", "title", "parent", "lead"])
    return 0


def _cmd_workpackage_create(args: argparse.Namespace) -> int:
    with _session_scope() as session:
        _, _, wps = _admin_services(session)
        wp = wps.create(
            code=args.code,
            title=args.title,
            lead_partner_short_name=args.lead,
            description=args.description,
            parent_code=args.parent,
        )
    print(f"Workpackage angelegt: {wp.code} — {wp.title}")
    return 0


# ---- person ---------------------------------------------------------------


def _cmd_person_list(_: argparse.Namespace) -> int:
    with _session_scope() as session:
        _, persons, _ = _admin_services(session)
        rows = [
            {
                "email": p.email,
                "display_name": p.display_name,
                "partner": p.partner.short_name if p.partner else "",
                "role": p.platform_role,
                "active": "yes" if p.is_active else "no",
                "must_change_pw": "yes" if p.must_change_password else "no",
            }
            for p in persons.list_persons()
        ]
    _print_table(
        rows,
        ["email", "display_name", "partner", "role", "active", "must_change_pw"],
    )
    return 0


def _prompt_password(min_len: int = 10) -> str:
    while True:
        pw = getpass.getpass("Neues Passwort (mind. 10 Zeichen): ")
        confirm = getpass.getpass("Bestätigen: ")
        if pw != confirm:
            print("Passwörter stimmen nicht überein, bitte erneut.")
            continue
        if len(pw) < min_len:
            print(f"Mindestens {min_len} Zeichen, bitte erneut.")
            continue
        return pw


def _cmd_person_create(args: argparse.Namespace) -> int:
    password = _prompt_password()
    with _session_scope() as session:
        partners, persons, _ = _admin_services(session)
        partner = partners.get_by_short_name(args.partner)
        if partner is None:
            print(f"Partner {args.partner!r} nicht gefunden.", file=sys.stderr)
            return 1
        person = persons.create(
            email=args.email,
            display_name=args.display_name,
            partner_id=partner.id,
            password=password,
            platform_role=args.role,
        )
    print(f"Person angelegt: {person.email} ({person.platform_role})")
    return 0


def _cmd_person_reset_password(args: argparse.Namespace) -> int:
    password = _prompt_password()
    with _session_scope() as session:
        _, persons, _ = _admin_services(session)
        person = persons.get_by_email(args.email)
        if person is None:
            print(f"Person {args.email!r} nicht gefunden.", file=sys.stderr)
            return 1
        persons.reset_password(person.id, password)
    print(f"Passwort zurückgesetzt für {args.email}.")
    return 0


def _cmd_person_set_role(args: argparse.Namespace) -> int:
    with _session_scope() as session:
        _, persons, _ = _admin_services(session)
        person = persons.get_by_email(args.email)
        if person is None:
            print(f"Person {args.email!r} nicht gefunden.", file=sys.stderr)
            return 1
        persons.set_role(person.id, args.role)
    print(f"Rolle gesetzt: {args.email} → {args.role}")
    return 0


def _cmd_person_enable(args: argparse.Namespace) -> int:
    with _session_scope() as session:
        _, persons, _ = _admin_services(session)
        person = persons.get_by_email(args.email)
        if person is None:
            print(f"Person {args.email!r} nicht gefunden.", file=sys.stderr)
            return 1
        persons.enable(person.id)
    print(f"Aktiviert: {args.email}")
    return 0


def _cmd_person_disable(args: argparse.Namespace) -> int:
    with _session_scope() as session:
        _, persons, _ = _admin_services(session)
        person = persons.get_by_email(args.email)
        if person is None:
            print(f"Person {args.email!r} nicht gefunden.", file=sys.stderr)
            return 1
        persons.disable(person.id)
    print(f"Deaktiviert: {args.email}")
    return 0


# ---- membership -----------------------------------------------------------


def _cmd_membership_add(args: argparse.Namespace) -> int:
    with _session_scope() as session:
        _, persons, wps = _admin_services(session)
        person = persons.get_by_email(args.person)
        if person is None:
            print(f"Person {args.person!r} nicht gefunden.", file=sys.stderr)
            return 1
        wp = wps.get_by_code(args.workpackage)
        if wp is None:
            print(f"Workpackage {args.workpackage!r} nicht gefunden.", file=sys.stderr)
            return 1
        wps.add_membership(person.id, wp.id, args.role)
    print(f"Mitgliedschaft angelegt: {args.person} ↔ {args.workpackage} ({args.role})")
    return 0


def _cmd_membership_remove(args: argparse.Namespace) -> int:
    with _session_scope() as session:
        _, persons, wps = _admin_services(session)
        person = persons.get_by_email(args.person)
        if person is None:
            print(f"Person {args.person!r} nicht gefunden.", file=sys.stderr)
            return 1
        wp = wps.get_by_code(args.workpackage)
        if wp is None:
            print(f"Workpackage {args.workpackage!r} nicht gefunden.", file=sys.stderr)
            return 1
        wps.remove_membership(person.id, wp.id)
    print(f"Mitgliedschaft entfernt: {args.person} ↔ {args.workpackage}")
    return 0


# ---------------------------------------------------------------------------
# Parser-Bau
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ref4ep-admin", description="Ref4EP-Portal Admin-CLI")
    sub = parser.add_subparsers(dest="command", required=False)

    # version
    p_version = sub.add_parser("version", help="Version und Python-Info anzeigen")
    p_version.set_defaults(func=_cmd_version)

    # seed
    p_seed = sub.add_parser("seed", help="Initial-Seed laden")
    p_seed.add_argument(
        "--from",
        dest="from_source",
        choices=["antrag"],
        required=True,
        help="Seed-Quelle (Sprint 1: nur 'antrag')",
    )
    p_seed.set_defaults(func=_cmd_seed)

    # partner
    p_partner = sub.add_parser("partner", help="Partner verwalten")
    p_partner_sub = p_partner.add_subparsers(dest="partner_cmd", required=True)
    p_partner_list = p_partner_sub.add_parser("list", help="Partner auflisten")
    p_partner_list.set_defaults(func=_cmd_partner_list)
    p_partner_create = p_partner_sub.add_parser("create", help="Partner anlegen")
    p_partner_create.add_argument("--short-name", required=True)
    p_partner_create.add_argument("--name", required=True)
    p_partner_create.add_argument("--country", required=True, help="ISO-3166-1 Alpha-2 (z. B. DE)")
    p_partner_create.add_argument("--website", default=None)
    p_partner_create.set_defaults(func=_cmd_partner_create)

    # workpackage
    p_wp = sub.add_parser("workpackage", help="Arbeitspakete verwalten")
    p_wp_sub = p_wp.add_subparsers(dest="workpackage_cmd", required=True)
    p_wp_list = p_wp_sub.add_parser("list", help="Workpackages auflisten")
    p_wp_list.set_defaults(func=_cmd_workpackage_list)
    p_wp_create = p_wp_sub.add_parser("create", help="Workpackage anlegen")
    p_wp_create.add_argument("--code", required=True, help='z. B. "WP9" oder "WP3.4"')
    p_wp_create.add_argument("--title", required=True)
    p_wp_create.add_argument("--lead", required=True, help="Short-Name des Lead-Partners")
    p_wp_create.add_argument("--parent", default=None, help="Code des Parent-WP, falls Sub-WP")
    p_wp_create.add_argument("--description", default=None)
    p_wp_create.set_defaults(func=_cmd_workpackage_create)

    # person
    p_person = sub.add_parser("person", help="Personen verwalten")
    p_person_sub = p_person.add_subparsers(dest="person_cmd", required=True)
    p_person_list = p_person_sub.add_parser("list", help="Personen auflisten")
    p_person_list.set_defaults(func=_cmd_person_list)
    p_person_create = p_person_sub.add_parser("create", help="Person anlegen (Passwort interaktiv)")
    p_person_create.add_argument("--email", required=True)
    p_person_create.add_argument("--display-name", required=True)
    p_person_create.add_argument("--partner", required=True, help="Short-Name")
    p_person_create.add_argument("--role", choices=["admin", "member"], default="member")
    p_person_create.set_defaults(func=_cmd_person_create)
    p_person_reset = p_person_sub.add_parser(
        "reset-password", help="Passwort interaktiv zurücksetzen"
    )
    p_person_reset.add_argument("--email", required=True)
    p_person_reset.set_defaults(func=_cmd_person_reset_password)
    p_person_role = p_person_sub.add_parser("set-role", help="Plattformrolle ändern")
    p_person_role.add_argument("--email", required=True)
    p_person_role.add_argument("--role", choices=["admin", "member"], required=True)
    p_person_role.set_defaults(func=_cmd_person_set_role)
    p_person_enable = p_person_sub.add_parser("enable", help="Login aktivieren")
    p_person_enable.add_argument("--email", required=True)
    p_person_enable.set_defaults(func=_cmd_person_enable)
    p_person_disable = p_person_sub.add_parser("disable", help="Login deaktivieren")
    p_person_disable.add_argument("--email", required=True)
    p_person_disable.set_defaults(func=_cmd_person_disable)

    # membership
    p_mem = sub.add_parser("membership", help="Mitgliedschaften verwalten")
    p_mem_sub = p_mem.add_subparsers(dest="membership_cmd", required=True)
    p_mem_add = p_mem_sub.add_parser("add", help="Mitgliedschaft anlegen")
    p_mem_add.add_argument("--person", required=True, help="E-Mail")
    p_mem_add.add_argument("--workpackage", required=True, help="WP-Code")
    p_mem_add.add_argument("--role", choices=["wp_lead", "wp_member"], required=True)
    p_mem_add.set_defaults(func=_cmd_membership_add)
    p_mem_remove = p_mem_sub.add_parser("remove", help="Mitgliedschaft entfernen")
    p_mem_remove.add_argument("--person", required=True, help="E-Mail")
    p_mem_remove.add_argument("--workpackage", required=True, help="WP-Code")
    p_mem_remove.set_defaults(func=_cmd_membership_remove)

    return parser


# ---------------------------------------------------------------------------
# Entry-Point
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 0
    func: Callable[[argparse.Namespace], int] = args.func
    try:
        return func(args)
    except (LookupError, PermissionError, ValueError) as exc:
        print(f"Fehler: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
