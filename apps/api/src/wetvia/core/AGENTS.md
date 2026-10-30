# wetvia.core

Doel: gedeelde types (`Peildatum`, `ChunkRef`) en fouten. Geen I/O.

Publieke API: wat `__init__.py` exporteert. Nu leeg.

Toegestane imports: de standaardbibliotheek. Geen andere `wetvia`-module. Verboden: `sqlalchemy`, `httpx`, `openai`, `fastapi`, `sentence_transformers`.

Test: `cd apps/api && uv run pytest && uv run lint-imports`
