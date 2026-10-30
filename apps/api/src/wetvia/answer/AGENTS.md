# wetvia.answer

Doel: de RAG-use-case (pipeline, `AnswerV1`, prompts). Nu leeg.

Publieke API: wat `__init__.py` exporteert. Nu leeg.

Toegestane imports: `wetvia.retrieval`, `wetvia.ingest`, `wetvia.citations`, `wetvia.rules`, `wetvia.llm`, `wetvia.embeddings`, `wetvia.db`, `wetvia.core` en de standaardbibliotheek. Niet `wetvia.dossier` of `wetvia.documents` (zelfde laag) en niets daarboven (`api`, `cli`, `bootstrap`).

Test: `cd apps/api && uv run pytest && uv run lint-imports`
