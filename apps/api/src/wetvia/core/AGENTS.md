# wetvia.core

Doel: gedeelde types (`LlmProvider`, later `Peildatum` en `ChunkRef`) en fouten. Geen I/O.

Publieke API: `LlmProvider`.

Toegestane imports: de standaardbibliotheek. Geen andere `wetvia`-module. Verboden: `sqlalchemy`, `httpx`, `openai`, `fastapi`, `sentence_transformers`.

Test: `cd apps/api && uv run pytest && uv run lint-imports`
