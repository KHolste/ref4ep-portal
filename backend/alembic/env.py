"""Alembic-Environment für das Ref4EP-Portal.

Liest die Datenbank-URL aus ``ref4ep.api.config.Settings`` (eine
Quelle der Wahrheit) und nutzt ``ref4ep.domain.base.Base.metadata``
als Autogenerate-Ziel.
"""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from ref4ep.api.config import get_settings
from ref4ep.domain.base import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Wenn die URL nicht bereits explizit in der Config gesetzt wurde
# (z. B. durch Tests, die einen tmp-DB-Pfad injizieren), aus den
# Settings übernehmen — eine Quelle der Wahrheit fürs CLI.
if not config.get_main_option("sqlalchemy.url"):
    config.set_main_option("sqlalchemy.url", get_settings().database_url)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=url.startswith("sqlite"),
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=connection.dialect.name == "sqlite",
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
