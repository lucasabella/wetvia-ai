# wetvia.ingest

Doel: schrijfpad, bronnen naar chunks. Bronclients blijven in `nl_wetten_ingest` (dat pakket importeert `wetvia` niet). Caching en opslag horen hier. Nu leeg.

Publieke API: wat `__init__.py` exporteert. Nu leeg.

Toegestane imports: `wetvia.embeddings`, `wetvia.db`, `wetvia.core`, `nl_wetten_ingest` en de standaardbibliotheek. Niet `wetvia.retrieval`, `wetvia.citations`, `wetvia.rules` of `wetvia.llm` (zelfde laag) en niets daarboven.

Test: `cd apps/api && uv run pytest && uv run lint-imports`
