# wetvia.bootstrap en wetvia.cli

Deze twee modules zijn bestanden, geen pakketten. Hogere lagen staan in de root-`AGENTS.md`. Lagere lagen hebben een eigen `AGENTS.md`.

## bootstrap.py

Doel: composition root. `build_app` is de enige plek die `Settings` (`wetvia.config`) aanmaakt. Het ASGI-object is `app` (lui).

Publieke API: `build_app`, `get_provider`, `package_version`, `app`. `get_provider` kiest de LLM-adapter. `build_app` zet die op `app.state.llm`.

Toegestane imports: `wetvia.config` en alle lagere lagen (`wetvia.api`, `wetvia.cli`, `wetvia.answer`, `wetvia.dossier`, `wetvia.documents`, `wetvia.retrieval`, `wetvia.ingest`, `wetvia.citations`, `wetvia.rules`, `wetvia.llm`, `wetvia.embeddings`, `wetvia.db`, `wetvia.core`). Andere modules importeren `wetvia.config` niet.

Test: `cd apps/api && uv run pytest && uv run lint-imports`

## cli.py

Doel: Typer-ingang voor batchwerk (`wetvia ingest`, `wetvia embed`). Dunne laag boven de modules. Nu leeg.

Publieke API: de module zelf. Nog geen commando's.

Toegestane imports: `wetvia.answer`, `wetvia.dossier`, `wetvia.documents` en alles daaronder. Niet `wetvia.api` (zelfde laag) en niet `wetvia.bootstrap` (hogere laag).

Test: `cd apps/api && uv run pytest && uv run lint-imports`
