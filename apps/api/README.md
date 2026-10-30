# apps/api

FastAPI-backend van Wetvia (AGPL-3.0-only), één pakket `wetvia`. Modulaire monoliet: zie `docs/06-architectuur-structuur.md`. Nog geen app, routes of adapters.

Lagen, van hoog naar laag: `bootstrap`, `api` | `cli`, `answer` | `dossier` | `documents`, `retrieval` | `ingest` | `citations` | `rules` | `llm`, `embeddings` | `db`, `core`. Elke module heeft een `AGENTS.md`.

```bash
uv run ruff check
uv run ruff format --check
uv run mypy src
uv run pytest
uv run lint-imports
```
