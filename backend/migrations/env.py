from __future__ import annotations

from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

config = context.config
target_metadata = None

arguments = context.get_x_argument(as_dictionary=True)
if "db" in arguments:
    database_path = Path(arguments["db"]).resolve().as_posix()
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database_path}")


def run_migrations_offline() -> None:
    context.configure(url=config.get_main_option("sqlalchemy.url"), literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(config.get_section(config.config_ini_section), prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection)
        with context.begin_transaction():
            context.run_migrations()


run_migrations_offline() if context.is_offline_mode() else run_migrations_online()
