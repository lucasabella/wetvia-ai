# wetvia.llm

Doel: de `LLMProvider`-port. Adapters komen later in `adapters/`. De factory hoort in `bootstrap.py`, niet hier. Nu leeg.

Publieke API: wat `__init__.py` exporteert. Nu leeg. `prompts/` is een lege placeholder; antwoordprompts horen later in `answer/prompts/`.

Toegestane imports: `wetvia.embeddings`, `wetvia.db`, `wetvia.core` en de standaardbibliotheek. Niet `wetvia.retrieval`, `wetvia.ingest`, `wetvia.citations` of `wetvia.rules` (zelfde laag) en niets daarboven.

Test: `cd apps/api && uv run pytest && uv run lint-imports`
