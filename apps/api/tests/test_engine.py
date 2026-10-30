"""Unreachable databases report error and do not echo the URL."""

import asyncio
import logging

import pytest

from wetvia.db.engine import create_db_engine, database_status

_PASSWORD = "s3cret-db-password"
_URL = f"postgresql+psycopg://wetvia:{_PASSWORD}@127.0.0.1:1/wetvia?connect_timeout=1"


def test_database_status_unreachable_does_not_leak_url(
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    engine = create_db_engine(_URL)

    async def check() -> str:
        try:
            return await database_status(engine)
        finally:
            await engine.dispose()

    status = asyncio.run(check())
    captured = capsys.readouterr()
    leaked = captured.out + captured.err + caplog.text

    assert status == "error"
    assert _PASSWORD not in status
    assert _PASSWORD not in leaked
    assert _URL not in leaked
