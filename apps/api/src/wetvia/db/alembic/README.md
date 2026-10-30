Alembic scripts for `wetvia`. The first revision is empty.

`env.py` reads `sqlalchemy.url` from the Alembic config. It does not construct `Settings`.
The app engine is created in `wetvia.bootstrap`.
