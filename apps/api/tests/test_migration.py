"""The first Alembic revision applies. SQLite stands in for Postgres in this empty migration."""

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

_API_ROOT = Path(__file__).resolve().parents[1]


def _alembic_config(database_url: str) -> Config:
    config = Config(str(_API_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(_API_ROOT / "src" / "wetvia" / "db" / "alembic"))
    config.set_main_option("sqlalchemy.url", database_url)
    return config


def _applied_version(database_path: Path) -> str:
    engine = create_engine(f"sqlite:///{database_path}")
    with engine.connect() as connection:
        version = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
    return str(version)


def test_empty_migration_uses_ini_url_when_database_url_is_blank(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATABASE_URL", "")
    database_path = tmp_path / "from-ini.sqlite"

    command.upgrade(_alembic_config(f"sqlite:///{database_path}"), "head")

    assert _applied_version(database_path) == "0001_empty"


def test_database_url_overrides_ini_url(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from_env = tmp_path / "from-env.sqlite"
    from_ini = tmp_path / "from-ini.sqlite"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{from_env}")

    command.upgrade(_alembic_config(f"sqlite:///{from_ini}"), "head")

    assert _applied_version(from_env) == "0001_empty"
    assert not from_ini.exists()
