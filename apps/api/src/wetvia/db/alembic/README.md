Alembic scripts for `wetvia`. `0001_empty` preserves the initial baseline;
`0002_ingest_schema` creates the Postgres/pgvector ingestion tables. SQLite is
used only by the URL-selection tests: the Postgres-only schema migration is an
intentional no-op there. The API integration tests run the full migration and
ingest path against the CI Postgres+pgvector service.

`env.py` uses `DATABASE_URL` when that variable is non-empty, otherwise `sqlalchemy.url` from `alembic.ini`. It does not import `Settings`.
The app engine is created in `wetvia.bootstrap`.
