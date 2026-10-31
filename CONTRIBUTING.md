# Bijdragen aan Wetvia

Wetvia is een monorepo: `apps/api` (FastAPI, AGPL-3.0-only), `apps/web` (frontend, AGPL-3.0-only; SvelteKit volgt), `packages/api-client` (gegenereerde OpenAPI/TypeScript-client, AGPL-3.0-only), `packages/nl-wetten-ingest` (Apache-2.0) en `eval/` (de evaluatieset is CC BY 4.0).

Werk op een branch vanaf `main`. Push niet naar `main` en merge je eigen PR niet.

## Geen bron, geen claim

Verzin geen wetgeving, artikelnummers, ECLI's of citaten. Ontbreekt de officiële tekst in de repo of in het issue, schrijf die dan niet zelf. Zeg in de PR wat je niet kon verifiëren.

## Secrets

Commit geen `.env`, sleutels, `*.pem`, `*.key` of modelbestanden (`*.gguf`). Alleen `.env.example` met placeholders. Zet geen betaalde dienst aan.

## Label `agent-ready`

`agent-ready` betekent: een coding agent kan het issue zelfstandig oppakken. Het issue is dan compleet genoeg dat er geen extra product- of juridische keuzes meer in zitten.

Een issue is pas `agent-ready` als het deze secties heeft (het template `.github/ISSUE_TEMPLATE/agent-task.yml` vraagt ze):

| Sectie              | Wat erin staat                                           |
| ------------------- | -------------------------------------------------------- |
| Context             | Waarom de taak bestaat en welk deel van Wetvia hij raakt |
| Acceptatiecriteria  | Toetsbare checklist. Dit is de scope                     |
| Technische notities | Aanpak, paden, env-vars, bekende valkuilen               |
| Docs                | Welke bestanden in `docs/` de agent moet volgen          |

Een maintainer zet het label. Zet het niet zelf op een issue dat nog open vragen heeft. Agents voeren alleen de acceptatiecriteria uit en laten de rest liggen.

Issues zonder het label zijn nog niet klaar om op te pakken. Het label `needs-human` betekent dat Luca iets moet aanleveren of controleren (juridische inhoud, een account, een label).

## PR-checklist

Gebruik deze checklist in de PR-beschrijving:

- [ ] Acceptatiecriteria van het issue gehaald, en niets daarbuiten
- [ ] Tests toegevoegd of bijgewerkt
- [ ] Lint en typecheck lokaal groen (commando's hieronder)
- [ ] Docs bijgewerkt als gedrag of setup verandert
- [ ] Eval-impact vermeld: geen, of welke set en welk verwacht effect
- [ ] Geen secrets, `.env` of modelbestanden
- [ ] Geen verzonnen wetgeving of bronnen
- [ ] Licentie klopt: code AGPL-3.0-only, `docs/` en `eval/data/` CC BY 4.0, `packages/nl-wetten-ingest` Apache-2.0

## Commando's

```bash
uv sync --all-packages --all-groups
pnpm install

cd apps/api && uv run ruff check && uv run ruff format --check && uv run mypy src && uv run pytest && uv run lint-imports
cd ../../packages/nl-wetten-ingest && uv run ruff check && uv run ruff format --check && uv run mypy src && uv run pytest
cd ../../eval && uv run ruff check && uv run ruff format --check && uv run mypy src && uv run pytest
cd .. && pnpm lint && pnpm check && pnpm test && pnpm format:check
```

`uv run lint-imports` draait in de `api`-job van [`.github/workflows/ci.yml`](.github/workflows/ci.yml). Die job voert ook de OpenAPI-export-, gegenereerde-types-, typecheck- en clienttests uit en faalt bij een diff.

`pnpm test` draait vitest in `apps/web`. Python-tests zijn pytest in `apps/api`, `packages/nl-wetten-ingest` en `eval`. `training/` zit niet in de uv-workspace.

## OpenAPI en TypeScript-client

`packages/api-client/openapi.json` en `src/schema.d.ts` zijn gegenereerd; pas
deze bestanden niet met de hand aan. Na wijzigingen aan API-routes of schemas:

```bash
uv sync --all-packages --all-groups
pnpm install
pnpm --filter @wetvia/api-client generate
pnpm --filter @wetvia/api-client check:generated
pnpm --filter @wetvia/api-client typecheck
pnpm --filter @wetvia/api-client test
```

De exporter gebruikt `create_app` met een inert health-check-context. Hij start
geen server en roept `build_app`, databaseverbindingen, settings of modellen niet
aan. `createWetviaClient({ baseUrl, fetch })` accepteert `fetch` uit bijvoorbeeld
SvelteKit `load` voor requests binnen de gekozen runtime.
