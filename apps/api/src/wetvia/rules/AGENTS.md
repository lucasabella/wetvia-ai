# wetvia.rules

Doel: regels-als-code, pure functies zonder I/O. De dakkapeltoets komt later. Nu leeg.

Publieke API: wat `__init__.py` exporteert. Nu leeg.

Toegestane imports: de standaardbibliotheek. Het lagencontract noemt ook `wetvia.embeddings`, `wetvia.db` en `wetvia.core`, maar deze module blijft puur en doet geen I/O. Verboden: `sqlalchemy`, `httpx`, `openai`, `fastapi`, `sentence_transformers`. Niet de andere modules in dezelfde laag (`retrieval`, `ingest`, `citations`, `llm`) en niets daarboven.

Test: `cd apps/api && uv run pytest && uv run lint-imports`
