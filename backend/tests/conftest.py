"""Gemeinsame Test-Fixtures für Sprint 1.

Jeder Test bekommt eine frische SQLite-Datei in einem ``tmp_path`` mit
angewendeter Alembic-Migration. ``settings`` enthält ein test-festes
Session-Secret. Auth-Fixtures stellen authentifizierte TestClients
bereit.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from alembic import command
from ref4ep.api.app import create_app
from ref4ep.api.config import Settings
from ref4ep.services.partner_service import PartnerService
from ref4ep.services.person_service import PersonService
from ref4ep.services.seed_service import SeedService

BACKEND_DIR = Path(__file__).resolve().parent.parent
ALEMBIC_INI = BACKEND_DIR / "alembic.ini"
ALEMBIC_DIR = BACKEND_DIR / "alembic"

TEST_SESSION_SECRET = "x" * 48  # >= 32 Zeichen, reicht für HMAC-Tests


def _apply_migrations(database_url: str) -> None:
    cfg = Config(str(ALEMBIC_INI))
    cfg.set_main_option("script_location", str(ALEMBIC_DIR))
    cfg.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(cfg, "head")


@pytest.fixture
def tmp_db_path(tmp_path: Path) -> Path:
    return tmp_path / "test_ref4ep.db"


@pytest.fixture
def settings(tmp_db_path: Path) -> Settings:
    return Settings(
        database_url=f"sqlite:///{tmp_db_path}",
        session_secret=TEST_SESSION_SECRET,
    )


@pytest.fixture
def migrated_db(settings: Settings) -> Settings:
    _apply_migrations(settings.database_url)
    return settings


@pytest.fixture
def app(migrated_db: Settings):
    return create_app(settings=migrated_db)


@pytest.fixture
def client(app) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def session(migrated_db: Settings) -> Iterator[Session]:
    engine = create_engine(migrated_db.database_url, future=True)
    factory = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
        future=True,
        expire_on_commit=False,
    )
    s = factory()
    try:
        yield s
    finally:
        s.rollback()
        s.close()


@pytest.fixture
def seeded_session(session: Session) -> Session:
    SeedService(session).apply_initial_seed(source="antrag")
    session.commit()
    return session


# ---- Personen-Fixtures ---------------------------------------------------

ADMIN_EMAIL = "admin@test.example"
ADMIN_PASSWORD = "Adm1nP4ssword!"
MEMBER_EMAIL = "member@test.example"
MEMBER_PASSWORD = "M3mberP4ssword!"


def _create_person(session: Session, email: str, password: str, role: str) -> str:
    partners = PartnerService(session, role="admin", person_id="test-fixture")
    persons = PersonService(session, role="admin", person_id="test-fixture")
    partner = partners.get_by_short_name("JLU")
    if partner is None:
        partner = partners.create(name="Test-JLU", short_name="JLU", country="DE")
    person = persons.create(
        email=email,
        display_name=f"Test {role}",
        partner_id=partner.id,
        password=password,
        platform_role=role,
    )
    # Damit Tests nicht beim ersten Login zu /portal/account umgeleitet werden:
    person.must_change_password = False
    session.commit()
    return person.id


@pytest.fixture
def admin_person_id(seeded_session: Session) -> str:
    return _create_person(seeded_session, ADMIN_EMAIL, ADMIN_PASSWORD, "admin")


@pytest.fixture
def member_person_id(seeded_session: Session) -> str:
    return _create_person(seeded_session, MEMBER_EMAIL, MEMBER_PASSWORD, "member")


@pytest.fixture
def admin_client(client: TestClient, admin_person_id: str) -> TestClient:
    response = client.post(
        "/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
    )
    assert response.status_code == 200, response.text
    return client


@pytest.fixture
def member_client(client: TestClient, member_person_id: str) -> TestClient:
    response = client.post(
        "/api/auth/login", json={"email": MEMBER_EMAIL, "password": MEMBER_PASSWORD}
    )
    assert response.status_code == 200, response.text
    return client
