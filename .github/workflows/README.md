# Workflows

- `ci.yml` draait op elke pull request en op een push naar `main`. Geen secrets.
- `eval.yml` en `drift-check.yml` komen later. Een leeg workflow-bestand zou Actions laten falen.

## Jobs in `ci.yml`

| Job | Wat |
| --- | --- |
| `api` | `uv sync --locked`, generated OpenAPI/client diff check with pnpm, client typecheck/tests, ruff, mypy, `uv run lint-imports`, pytest. Postgres 16 + pgvector als service; the exporter itself uses no database or model |
| `nl-wetten-ingest` | `uv sync --locked`, ruff, mypy, pytest. Eigen job, niet meegenomen in `api` |
| `web` | `pnpm install --frozen-lockfile`, Chromium install, `pnpm check`, `pnpm lint`, `pnpm format:check`, `pnpm test` (vitest), Playwright/axe desktop and mobile checks |
| `eval` | `uv sync --locked`, ruff, mypy, pytest in `eval/`. Geen Ollama en geen modelgewichten |

uv en pnpm gebruiken de Actions-cache.

`eval/` is uv-member `wetvia-eval` en heeft een eigen job. De modelbenchmark draait niet in CI: daar is geen GPU en er zijn nog geen eval-vragen.

## OpenAPI-check

De `api`-job gebruikt Node/pnpm om `pnpm --filter @wetvia/api-client
check:generated` uit te voeren. Dat script exporteert de spec vanuit de
app-factory, genereert de TypeScript-schema's en faalt bij een diff. De exporter
gebruikt een inert health-context; er is geen server, databaseverbinding of
modelinitialisatie nodig. Dezelfde job typecheckt en test de client.
