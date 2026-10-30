# wetvia.db

Doel: async engine, session factory, declarative base en Alembic. De URL komt van de aanroeper. `alembic/env.py` leest alleen de Alembic-config, niet `Settings`.

Publieke API: `Base`, `create_db_engine`, `create_session_factory`, `database_status`.

Toegestane imports: `wetvia.core`, SQLAlchemy, Alembic, psycopg en de standaardbibliotheek. Niet `wetvia.config`, `wetvia.embeddings` of een hogere laag.

Test: `cd apps/api && uv run pytest && uv run lint-imports`
