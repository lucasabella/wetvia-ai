# wetvia.api

Doel: HTTP-ingang. `app.py` is de factory, `routes/` de routers, `schemas/` de DTO's. Dit pakket leest geen `Settings` en geen env.

Publieke API: `create_app`; request-, response- en SSE-modellen uit
`wetvia.api.schemas`.

Toegestane imports: `wetvia.answer`, `wetvia.retrieval`, `wetvia.llm`,
`wetvia.dossier`, `wetvia.documents`, `wetvia.core`, `wetvia.db` en alles
daaronder, plus de standaardbibliotheek. Niet `wetvia.config`, `wetvia.cli` of
`wetvia.bootstrap`.

Test: `cd apps/api && uv run pytest && uv run lint-imports`
