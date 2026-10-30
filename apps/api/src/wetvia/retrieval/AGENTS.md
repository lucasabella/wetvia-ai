# wetvia.retrieval

Doel: leespad, hybride zoeken. De `Retriever`-port en de pg-adapter komen later. Nu leeg.

Publieke API: wat `__init__.py` exporteert. Nu leeg.

Toegestane imports: `wetvia.embeddings`, `wetvia.db`, `wetvia.core` en de standaardbibliotheek. Niet `wetvia.ingest`, `wetvia.citations`, `wetvia.rules` of `wetvia.llm` (zelfde laag) en niets daarboven.

Test: `cd apps/api && uv run pytest && uv run lint-imports`
