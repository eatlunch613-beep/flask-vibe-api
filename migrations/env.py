from logging.config import fileConfig
import os
from pathlib import Path

from alembic import context
from dotenv import load_dotenv
from sqlalchemy import engine_from_config
from sqlalchemy import pool

from extensions import db
import models  # noqa: F401

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# 目標 metadata 用 extensions.db.metadata
target_metadata = db.metadata


def get_database_url() -> str:
    url = os.getenv("DATABASE_URL")
    if not url or not url.strip():
        project_root = Path(__file__).resolve().parent.parent
        env_file = project_root / ".env"
        if env_file.exists():
            load_dotenv(dotenv_path=env_file)
            url = os.getenv("DATABASE_URL")

    if not url or not url.strip():
        raise RuntimeError("缺少環境變數 DATABASE_URL，請在環境變數或專案 .env 中設定 PostgreSQL 連線字串")

    clean_url = url.strip()
    if clean_url.startswith("postgres://"):
        clean_url = clean_url.replace("postgres://", "postgresql://", 1)

    return clean_url


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = get_database_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    database_url = get_database_url()
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = database_url

    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
