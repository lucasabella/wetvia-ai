# apps/api

FastAPI-backend van Wetvia (AGPL-3.0-only), één pakket `wetvia`. Modulaire monoliet: zie `docs/06-architectuur-structuur.md`.

`GET /api/health` en de OpenAPI-UI op `/api/docs`. De factory is `wetvia.api.create_app`; het ASGI-object is `wetvia.bootstrap:app`. Alleen bootstrap leest `Settings`. Alembic: `uv run alembic upgrade head`.

## BWB-ingest

```bash
uv run wetvia ingest bwb --preset mvp
uv run wetvia ingest bwb --ids BWBR0041297 --ids BWBR0005537
uv run wetvia ingest sync
uv run wetvia embed --max-batches 100
```

The MVP preset is the seven regulation IDs in `docs/04-tech-stack.md`. An
ingest selects the state valid today and, when present, the nearest future
state. Sync uses `changed_since(yesterday)` to find changed MVP laws and laws
previously ingested with `--ids`, then reloads each changed law's complete
state history so predecessor validity dates stay current. For unchanged tracked
laws, sync reuses the stored full state history and existing chunks; it fetches
only a selected current or future state that is not materialized yet. Every
sync recalculates stored chunk statuses for the current date, even when SRU
reports no changes. XML downloads remain in `nl-wetten-ingest`; SQL upserts run
in transactions. `wetvia embed` fills only `NULL` vectors in bounded batches;
rerun it to resume after the configured batch limit or an interruption. The
model is loaded only when `embed` is invoked. Install the optional local
inference dependency with `uv sync --all-packages --all-groups --extra embeddings`
before running it.

The stored vector defaults to 1024 dimensions, matching the initial
`Vector(1024)` migration. The database records the active model ID and dimension,
and the job refuses to mix vector spaces. To switch models at the same
dimension, clear all existing vectors, run `wetvia embed` with the new
`EMBEDDING_MODEL`, then rebuild `ix_chunk_embedding_hnsw` (for example,
`UPDATE chunk SET embedding = NULL;` before the new run). To change dimensions,
add a schema migration that clears old vectors, changes `chunk.embedding` to
`vector(N)`, and rebuilds the HNSW index; then set `EMBEDDING_DIMENSION=N` and
the new `EMBEDDING_MODEL` before re-embedding. The runtime reads the migrated
PostgreSQL vector width, so supporting a new model dimension needs no application
code change.

The data schema requires PostgreSQL with pgvector. SQLite migration tests cover
Alembic URL selection only; CI runs migration, ingest, and embedding job
integration tests on its PostgreSQL+pgvector service.

Lagen, van hoog naar laag: `bootstrap`, `api` | `cli`, `answer` | `dossier` | `documents`, `retrieval` | `ingest` | `citations` | `rules` | `llm`, `embeddings` | `db`, `core`. Elke module heeft een `AGENTS.md`.

```bash
uv run ruff check
uv run ruff format --check
uv run mypy src
uv run pytest
uv run lint-imports
```
