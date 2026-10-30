# apps/api

FastAPI-backend van Wetvia (AGPL-3.0-only). Dit issue zet alleen het pakket en de mappen neer.

```
src/wetvia/
  llm/            provider, prompts
  retrieval/
  rules/
  answer/
  dossier/        inclusief templates/
  db/             inclusief alembic/
  api/            routes
tests/
```

Er is nog geen app, config, database of route. `uv run ruff check` en `uv run mypy src` horen hier te slagen.

```bash
uv run ruff check
uv run ruff format --check
uv run mypy src
uv run pytest
```
