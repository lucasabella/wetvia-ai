# wetvia.api

Doel: HTTP-ingang. `app.py` is de factory, `routes/` de routers, `schemas/` de DTO's. Dit pakket leest geen `Settings` en geen env.

Publieke API: `create_app`.

Toegestane imports: `wetvia.answer`, `wetvia.dossier`, `wetvia.documents`, `wetvia.core`, `wetvia.db` en alles daaronder, plus de standaardbibliotheek. Niet `wetvia.config`, `wetvia.cli` of `wetvia.bootstrap`.

Test: `cd apps/api && uv run pytest && uv run lint-imports`
