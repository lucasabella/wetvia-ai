Alembic scripts for `wetvia`. The first revision is empty.

`env.py` uses `DATABASE_URL` when that variable is non-empty, otherwise `sqlalchemy.url` from `alembic.ini`. It does not import `Settings`.
The app engine is created in `wetvia.bootstrap`.
