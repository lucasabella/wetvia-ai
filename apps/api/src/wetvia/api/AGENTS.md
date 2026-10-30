# wetvia.api

Doel: HTTP-ingang. Routes, DTO's en SSE-events. De app-factory komt later in `app.py`. Nu leeg.

Publieke API: wat `__init__.py` exporteert. Nu leeg.

Toegestane imports: `wetvia.answer`, `wetvia.dossier`, `wetvia.documents` en alles daaronder, plus de standaardbibliotheek. Niet `wetvia.cli` (zelfde laag) en niet `wetvia.bootstrap` (hogere laag).

Test: `cd apps/api && uv run pytest && uv run lint-imports`
