# wetvia.retrieval

Doel: date-aware leespad voor wetchunks, met lexicaal en semantisch zoeken.

Publieke API: `Retriever`, `ScoredChunk`, `SourceDocument` en `SourceMetadata` uit `__init__.py`. PostgreSQL en fake adapters implementeren de async port.

De pg-adapter combineert Dutch full-text search en pgvector in één parameterized CTE-query. Houd peildatumfiltering in beide kandidatenstromen, `artikel_status='vervallen'` uitgesloten, inclusieve geldigheidsgrenzen en stabiele UUID-tiebreaks. Query-invoer gebruikt de publieke Embedder-port; laad geen model in `retrieval/`.

Toegestane imports: `wetvia.embeddings`, `wetvia.db`, `wetvia.core` en de standaardbibliotheek. Niet `wetvia.ingest`, `wetvia.citations`, `wetvia.rules` of `wetvia.llm` (zelfde laag) en niets daarboven.

Test: `cd apps/api && uv run pytest && uv run lint-imports`; hybride zoekintegratie gebruikt de PostgreSQL+pgvector-testdatabase en offline BWB-fixtures.
