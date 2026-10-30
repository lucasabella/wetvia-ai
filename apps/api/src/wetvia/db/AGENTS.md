# wetvia.db

Doel: engine, sessie, schema en Alembic. Eén database, tabellen per module. Nu leeg.

Publieke API: wat `__init__.py` exporteert. Nu leeg.

Toegestane imports: `wetvia.core` en de standaardbibliotheek. Niet `wetvia.embeddings` (zelfde laag) en niets daarboven.

Test: `cd apps/api && uv run pytest && uv run lint-imports`
