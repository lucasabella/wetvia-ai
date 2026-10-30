"""Compose-afspraken uit issue #2. Geen Docker-daemon nodig."""

from __future__ import annotations

from pathlib import Path


def _root() -> Path:
    return Path(__file__).resolve().parents[3]


def test_init_sql_creates_vector_extension() -> None:
    sql = (_root() / "docker" / "postgres" / "init" / "01-vector.sql").read_text(encoding="utf-8")
    assert "CREATE EXTENSION vector;" in sql


def test_compose_starts_only_db_by_default() -> None:
    text = (_root() / "docker-compose.yml").read_text(encoding="utf-8")
    services = _service_blocks(text)

    assert set(services) == {"db", "api", "web", "worker", "ollama"}
    assert "profiles:" not in services["db"]
    assert "profiles: [api]" in services["api"]
    assert "profiles: [web]" in services["web"]
    assert "profiles: [ingest]" in services["worker"]
    assert "profiles: [gpu-linux]" in services["ollama"]


def test_db_is_pg16_pgvector_on_localhost() -> None:
    db = _service_blocks((_root() / "docker-compose.yml").read_text(encoding="utf-8"))["db"]
    assert "image: pgvector/pgvector:pg16" in db
    assert '"127.0.0.1:5432:5432"' in db
    assert "0.0.0.0" not in db
    assert "/docker-entrypoint-initdb.d" in db
    assert "pg_isready" in db
    assert "POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:?Set POSTGRES_PASSWORD in .env}" in db
    assert "change-me" not in db


def test_worker_shares_api_image_and_llm_base_url() -> None:
    text = (_root() / "docker-compose.yml").read_text(encoding="utf-8")
    services = _service_blocks(text)
    assert "image: wetvia-api:local" in text
    assert "OLLAMA_BASE_URL:" not in text
    assert "LLM_BASE_URL: http://host.docker.internal:11434" in text
    assert 'command: ["sh", "-c", "wetvia ingest sync && wetvia embed"]' in services["worker"]
    assert "<<: *api-image" in services["api"]
    assert "<<: *api-image" in services["worker"]
    assert "host.docker.internal:host-gateway" in text


def test_ollama_profile_uses_official_image_on_localhost() -> None:
    ollama = _service_blocks((_root() / "docker-compose.yml").read_text(encoding="utf-8"))["ollama"]
    assert "image: ollama/ollama" in ollama
    assert '"127.0.0.1:11434:11434"' in ollama
    assert "driver: nvidia" in ollama


def _service_blocks(text: str) -> dict[str, str]:
    """Split top-level `services:` entries. Enough for this file, not a YAML parser."""
    lines = text.splitlines()
    start = lines.index("services:")
    blocks: dict[str, str] = {}
    name: str | None = None
    buf: list[str] = []
    for line in lines[start + 1 :]:
        if line.startswith("volumes:"):
            break
        if line and not line.startswith(" ") and not line.startswith("#"):
            break
        if line.startswith("  ") and not line.startswith("   ") and line.endswith(":"):
            if name is not None:
                blocks[name] = "\n".join(buf)
            name = line.strip()[:-1]
            buf = [line]
            continue
        if name is not None:
            buf.append(line)
    if name is not None:
        blocks[name] = "\n".join(buf)
    return blocks
