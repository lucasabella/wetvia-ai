# Workflows

- `ci.yml` draait op elke pull request en op een push naar `main`. Geen secrets.
- `eval.yml` en `drift-check.yml` komen later. Een leeg workflow-bestand zou Actions laten falen.

## Jobs in `ci.yml`

| Job | Wat |
| --- | --- |
| `api` | `uv sync --locked`, ruff, mypy, `uv run lint-imports`, pytest. Postgres 16 + pgvector als service; de stap ervoor zet `CREATE EXTENSION vector` |
| `nl-wetten-ingest` | `uv sync --locked`, ruff, mypy, pytest. Eigen job, niet meegenomen in `api` |
| `web` | `pnpm install --frozen-lockfile`, `pnpm check`, `pnpm lint`, `pnpm format:check`, `pnpm test` (vitest) |

uv en pnpm gebruiken de Actions-cache.

`eval/` is nog geen uv-workspace-member. Die krijgt een eigen job zodra dat zo is (docs/06).

## #39 OpenAPI-check (nog niet)

`packages/api-client/openapi.json` bestaat nog niet. De plek staat in de `api`-job van `ci.yml`, gemarkeerd met `#39`. Zodra #39 de spec toevoegt: genereer die opnieuw vanuit de app-factory (geen server, geen database) en faal bij een diff. Geen aparte workflow.
