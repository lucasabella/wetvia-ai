# wetvia.dossier

Doel: documenten genereren. Renderers komen later in `renderers/`. Gebruik straks alleen de publieke API van `wetvia.rules`. Nu leeg.

Publieke API: wat `__init__.py` exporteert. Nu leeg.

Toegestane imports: `wetvia.retrieval`, `wetvia.ingest`, `wetvia.citations`, `wetvia.rules`, `wetvia.llm`, `wetvia.embeddings`, `wetvia.db`, `wetvia.core` en de standaardbibliotheek. Niet `wetvia.answer` of `wetvia.documents` (zelfde laag) en niets daarboven.

Test: `cd apps/api && uv run pytest && uv run lint-imports`
