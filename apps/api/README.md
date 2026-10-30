# apps/api

FastAPI-backend van Wetvia (AGPL-3.0-only), één pakket `wetvia`. Modulaire monoliet: zie `docs/06-architectuur-structuur.md`.

`GET /api/health` en de OpenAPI-UI op `/api/docs`. De factory is `wetvia.api.create_app`; het ASGI-object is `wetvia.bootstrap:app`. Alleen bootstrap leest `Settings`. Alembic: `uv run alembic upgrade head` (eerste revisie is leeg).

Lagen, van hoog naar laag: `bootstrap`, `api` | `cli`, `answer` | `dossier` | `documents`, `retrieval` | `ingest` | `citations` | `rules` | `llm`, `embeddings` | `db`, `core`. Elke module heeft een `AGENTS.md`.

```bash
uv run ruff check
uv run ruff format --check
uv run mypy src
uv run pytest
uv run lint-imports
```
