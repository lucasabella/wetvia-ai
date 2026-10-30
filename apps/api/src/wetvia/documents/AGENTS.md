# wetvia.documents

Doel: uploads (v0.2), achter een port. Docling is later een optionele extra en de eerste kandidaat om af te splitsen. Nu leeg.

Publieke API: wat `__init__.py` exporteert. Nu leeg.

Toegestane imports: `wetvia.retrieval`, `wetvia.ingest`, `wetvia.citations`, `wetvia.rules`, `wetvia.llm`, `wetvia.embeddings`, `wetvia.db`, `wetvia.core` en de standaardbibliotheek. Niet `wetvia.answer` of `wetvia.dossier` (zelfde laag) en niets daarboven.

Test: `cd apps/api && uv run pytest && uv run lint-imports`
