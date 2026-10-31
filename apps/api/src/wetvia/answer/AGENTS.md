# wetvia.answer

Doel: de retrieval-to-answer pipeline, publiek Pydantic-schema `AnswerV1` en
packaged prompts. De pipeline krijgt de publieke `Retriever`- en `LLMProvider`-
ports geïnjecteerd en maakt zelf geen adapters of settings aan.

Publieke API: `AnswerPipeline`, `AnswerV1`, `VerifiedAnswer`, `AnswerPoint`,
`AnswerStatus`, `FollowUpStep`, `SourceTokenCounter`,
`Utf8ByteUpperBoundCounter`, `IncludedAnswerSource`, `IncludedSourcesHook`,
`MAX_HISTORY_CHARS`, `MAX_HISTORY_MESSAGES`, `DEFAULT_ABSTENTION_TAU`,
`AnswerDateMismatchError` en `UnknownSourceLabelError` uit `__init__.py`.

`AnswerV1` blijft het schema voor de modeloutput. `VerifiedAnswer` voegt
serverdiagnostiek (`verifier_notes`) na generatie toe; die diagnostiek is geen
LLM-invoer of modelgegenereerde inhoud. De retrieval-abstentiedrempel wordt via
bootstrap uit `ANSWER_ABSTENTION_TAU` geïnjecteerd.
`AnswerPipeline.answer` behoudt de bestaande positional arguments en accepteert
optionele keyword-only `history` en `on_sources`. De callback krijgt uitsluitend
de bronnen die na de promptbudgetfilter labels kregen en wordt vóór de provider
aangeroepen. Geschiedenis blijft beperkt tot 12 user-/assistant-berichten en
8.000 tekens.

Toegestane imports: `wetvia.retrieval`, `wetvia.ingest`, `wetvia.citations`, `wetvia.rules`, `wetvia.llm`, `wetvia.embeddings`, `wetvia.db`, `wetvia.core` en de standaardbibliotheek. Niet `wetvia.dossier` of `wetvia.documents` (zelfde laag) en niets daarboven (`api`, `cli`, `bootstrap`).

Test: `cd apps/api && uv run pytest && uv run lint-imports`. De live Ollama-test
is opt-in met `RUN_LLM_TESTS=1 pytest -m llm`; sla die niet over bij een expliciete
live-run en claim geen succesvolle live-acceptatie zonder geslaagde test.
