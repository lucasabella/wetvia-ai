# wetvia.db

Doel: async engine, session factory, declarative base en Alembic. De app-engine krijgt de URL van de aanroeper. `alembic/env.py` gebruikt `DATABASE_URL` als die gezet is, anders de URL uit `alembic.ini`. Het importeert `Settings` niet.

Publieke API: `Base`, `create_db_engine`, `create_session_factory`, `database_status`.

Toegestane imports: `wetvia.core`, SQLAlchemy, Alembic, psycopg en de standaardbibliotheek. Niet `wetvia.config`, `wetvia.embeddings` of een hogere laag.

Test: `cd apps/api && uv run pytest && uv run lint-imports`
