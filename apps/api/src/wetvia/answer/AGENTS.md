# wetvia.answer

Doel: de retrieval-to-answer pipeline, publiek Pydantic-schema `AnswerV1` en
packaged prompts. De pipeline krijgt de publieke `Retriever`- en `LLMProvider`-
ports geïnjecteerd en maakt zelf geen adapters of settings aan.

Publieke API: `AnswerPipeline`, `AnswerV1`, `AnswerPoint`, `AnswerStatus`,
`FollowUpStep`, `SourceTokenCounter`, `Utf8ByteUpperBoundCounter` en
`AnswerDateMismatchError` uit `__init__.py`.

Toegestane imports: `wetvia.retrieval`, `wetvia.ingest`, `wetvia.citations`, `wetvia.rules`, `wetvia.llm`, `wetvia.embeddings`, `wetvia.db`, `wetvia.core` en de standaardbibliotheek. Niet `wetvia.dossier` of `wetvia.documents` (zelfde laag) en niets daarboven (`api`, `cli`, `bootstrap`).

Test: `cd apps/api && uv run pytest && uv run lint-imports`. De live Ollama-test
is opt-in met `RUN_LLM_TESTS=1 pytest -m llm`; sla die niet over bij een expliciete
live-run en claim geen succesvolle live-acceptatie zonder geslaagde test.
