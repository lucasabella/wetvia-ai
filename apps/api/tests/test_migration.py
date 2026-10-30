"""The first Alembic revision applies. SQLite stands in for Postgres in this empty migration."""

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

_API_ROOT = Path(__file__).resolve().parents[1]


def test_empty_migration_upgrades(tmp_path: Path) -> None:
    database_path = tmp_path / "wetvia.sqlite"
    config = Config(str(_API_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(_API_ROOT / "src" / "wetvia" / "db" / "alembic"))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database_path}")

    command.upgrade(config, "head")

    engine = create_engine(f"sqlite:///{database_path}")
    with engine.connect() as connection:
        version = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
    assert version == "0001_empty"
