# wetvia.embeddings

Doel: de `Embedder`-port. Adapters (sentence-transformers, later TEI/Infinity, fake) komen in een later issue. Nu leeg.

Publieke API: wat `__init__.py` exporteert. Nu leeg.

Toegestane imports: `wetvia.core` en de standaardbibliotheek. Niet `wetvia.db` (zelfde laag) en niets daarboven.

Test: `cd apps/api && uv run pytest && uv run lint-imports`
