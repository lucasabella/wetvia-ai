# apps/api

FastAPI-backend van Wetvia (AGPL-3.0-only), één pakket `wetvia`. Modulaire monoliet: zie `docs/06-architectuur-structuur.md`.

`GET /api/health` en de OpenAPI-UI op `/api/docs`. De factory is `wetvia.api.create_app`; het ASGI-object is `wetvia.bootstrap:app`. Alleen bootstrap leest `Settings`. Alembic: `uv run alembic upgrade head`.

## BWB-ingest

```bash
uv run wetvia ingest bwb --preset mvp
uv run wetvia ingest bwb --ids BWBR0041297 --ids BWBR0005537
uv run wetvia ingest sync
```

The MVP preset is the seven regulation IDs in `docs/04-tech-stack.md`. An
ingest selects the state valid today and, when present, the nearest future
state. Sync uses `changed_since(yesterday)` to find changed MVP laws and laws
previously ingested with `--ids`, then reloads each changed law's complete
state history so predecessor validity dates stay current. Every sync also
recalculates stored chunk statuses for the current date, even when SRU reports
no changes. XML downloads remain in `nl-wetten-ingest`; SQL upserts run in
transactions. `embedding` remains `NULL` until the separate embedding issue.

The data schema requires PostgreSQL with pgvector. SQLite migration tests cover
Alembic URL selection only; CI runs the schema and upsert integration test on
its PostgreSQL+pgvector service.

Lagen, van hoog naar laag: `bootstrap`, `api` | `cli`, `answer` | `dossier` | `documents`, `retrieval` | `ingest` | `citations` | `rules` | `llm`, `embeddings` | `db`, `core`. Elke module heeft een `AGENTS.md`.

```bash
uv run ruff check
uv run ruff format --check
uv run mypy src
uv run pytest
uv run lint-imports
```
