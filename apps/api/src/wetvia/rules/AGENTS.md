# wetvia.rules

Doel: regels-als-code als pure functies zonder I/O. `bbl_dakkapel.py` bevat de
deterministische toets voor Bbl-artikelen 2.27, 2.29(b) en 2.30. Grenzen worden
als `Decimal`-constanten met artikelnummer opgeslagen; onbekende feiten leveren
`None` per eis op.

Publieke API: input-, enum-, bron- en resultaattypen, drempelconstanten en
`toets` uit `__init__.py`.

Toegestane imports: de standaardbibliotheek. Het lagencontract noemt ook `wetvia.embeddings`, `wetvia.db` en `wetvia.core`, maar deze module blijft puur en doet geen I/O. Verboden: `sqlalchemy`, `httpx`, `openai`, `fastapi`, `sentence_transformers`. Niet de andere modules in dezelfde laag (`retrieval`, `ingest`, `citations`, `llm`) en niets daarboven.

Test: `cd apps/api && uv run pytest tests/test_bbl_dakkapel.py && uv run lint-imports`
