# AGENTS.md

Wetvia is een modulaire monoliet, geen microservices. Het besluit en het afsplitspad staan in `docs/06-architectuur-structuur.md` en `docs/adr/0002-modulaire-monoliet.md`.

Lees de dichtstbijzijnde `AGENTS.md` in de module waar je werkt. Die wint van dit bestand voor die map.

## Commando's

```bash
uv sync --all-packages --all-groups
pnpm install

cd apps/api && uv run ruff check && uv run ruff format --check && uv run mypy src && uv run pytest && uv run lint-imports
cd packages/nl-wetten-ingest && uv run ruff check && uv run ruff format --check && uv run mypy src && uv run pytest
pnpm lint && pnpm check && pnpm test && pnpm format:check

cp .env.example .env
docker compose up -d db
```

`docker compose up` start alleen `db`. `api` en `web` hebben een profiel zolang hun Dockerfile er niet is. `worker` heeft profiel `ingest`. `ollama` heeft profiel `gpu-linux`.

`uv run lint-imports` hoort in de api-job van CI. Die workflow is er nog niet; de stap staat in `.github/workflows/README.md` voor issue #7.

## Grenzen

- Eén Python-pakket `wetvia` (`apps/api`). Processen: `web` (SvelteKit), `api` (FastAPI), `worker` (hetzelfde pakket via `cli.py`), `db` (Postgres 16 + pgvector). Het profiel `gpu-linux` start alleen het officiële Ollama-image; dat is geen Wetvia-code. Standaard blijft Ollama op de host.
- Lagen en het verbod op I/O in de kern staan in `apps/api/pyproject.toml`. Hoger mag lager importeren. Modules in dezelfde laag, gescheiden door `|`, importeren elkaar niet.
- De publieke API van een module is wat `__init__.py` exporteert. `_internal` en `adapters/` zijn niet publiek.
- Alleen `bootstrap.py` leest straks settings en kiest adapters. Andere modules krijgen dependencies geïnjecteerd en lezen de env niet zelf.
- `packages/nl-wetten-ingest` is Apache-2.0 en importeert `wetvia` niet. Bronclients horen daar; opslag hoort in `wetvia.ingest`.
- `training/` zit buiten de uv-workspace (torch/Unsloth tegen één gedeelde lockfile).
- `packages/api-client` hoort niet in dit issue.

## Verboden

- Geen secrets, `.env`, `*.pem`, `*.key` of modelbestanden (`*.gguf`). Alleen `.env.example` met placeholders.
- Geen verzonnen wetgeving, artikelnummers of citaten. Geen bron, geen claim.
- Geen microservices, gateway, queue of service mesh.
- `wetvia.rules`, `wetvia.citations` en `wetvia.core` importeren geen `sqlalchemy`, `httpx`, `openai`, `fastapi` of `sentence_transformers`.
- Geen featurecode in een lege module. Vul alleen de module van het issue dat je oppakt.
