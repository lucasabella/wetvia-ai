Alembic scripts for `wetvia`. `0001_empty` preserves the initial baseline;
`0002_ingest_schema` creates the Postgres/pgvector ingestion tables and
`0003_embedding_config` records the one model identity used for stored vectors.
SQLite is used only by the URL-selection tests: Postgres-only schema migrations
are intentional no-ops there. The API integration tests run the full migration,
ingest, and embedding paths against the CI Postgres+pgvector service.

`env.py` uses `DATABASE_URL` when that variable is non-empty, otherwise `sqlalchemy.url` from `alembic.ini`. It does not import `Settings`.
The app engine is created in `wetvia.bootstrap`.
