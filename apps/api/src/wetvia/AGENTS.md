# wetvia.bootstrap en wetvia.cli

Deze twee modules zijn bestanden, geen pakketten. Hogere lagen staan in de root-`AGENTS.md`. Lagere lagen hebben een eigen `AGENTS.md`.

## bootstrap.py

Doel: composition root. `build_app` is de enige plek die `Settings` (`wetvia.config`) aanmaakt. Het ASGI-object is `app` (lui).

Publieke API: `build_app`, `open_retriever`, `RetrieverRuntime`, `get_provider`, `get_chat_providers`, `get_ollama_provider`, `package_version`, `app`. `open_retriever` composeert de publieke retrieval-port plus embeddingconfiguratie voor consumers zoals `eval` en beheert de database-engine via een async contextmanager. `get_provider` bouwt een expliciet geselecteerde adapter voor bestaande consumers; `get_chat_providers` maakt de lokale en eventueel geconfigureerde Scaleway-provider. `build_app` injecteert aparte antwoordpipelines per modus; per request wordt er één gekozen en er is geen providerfallback.

Toegestane imports: `wetvia.config` en alle lagere lagen (`wetvia.api`, `wetvia.cli`, `wetvia.answer`, `wetvia.dossier`, `wetvia.documents`, `wetvia.retrieval`, `wetvia.ingest`, `wetvia.citations`, `wetvia.rules`, `wetvia.llm`, `wetvia.embeddings`, `wetvia.db`, `wetvia.core`). Andere modules importeren `wetvia.config` niet.

Test: `cd apps/api && uv run pytest && uv run lint-imports`

## cli.py

Doel: Typer-ingang voor batchwerk (`wetvia ingest`, `wetvia embed`). Dunne laag boven de modules. Nu leeg.

Publieke API: de module zelf. Nog geen commando's.

Toegestane imports: `wetvia.answer`, `wetvia.dossier`, `wetvia.documents` en alles daaronder. Niet `wetvia.api` (zelfde laag) en niet `wetvia.bootstrap` (hogere laag).

Test: `cd apps/api && uv run pytest && uv run lint-imports`
