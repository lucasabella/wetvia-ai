# apps/api

FastAPI-backend van Wetvia (AGPL-3.0-only), één pakket `wetvia`. Modulaire monoliet: zie `docs/06-architectuur-structuur.md`.

`GET /api/health` en de OpenAPI-UI op `/api/docs`. De factory is `wetvia.api.create_app`; het ASGI-object is `wetvia.bootstrap:app`. Alleen bootstrap leest `Settings`. Alembic: `uv run alembic upgrade head`.

## BWB-ingest

```bash
uv run wetvia ingest bwb --preset mvp
uv run wetvia ingest bwb --ids BWBR0041297 --ids BWBR0005537
uv run wetvia ingest sync
uv run wetvia embed --max-batches 100
```

The MVP preset is the seven regulation IDs in `docs/04-tech-stack.md`. An
ingest selects the state valid today and, when present, the nearest future
state. Sync uses `changed_since(yesterday)` to find changed MVP laws and laws
previously ingested with `--ids`, then reloads each changed law's complete
state history so predecessor validity dates stay current. For unchanged tracked
laws, sync reuses the stored full state history and existing chunks; it fetches
only a selected current or future state that is not materialized yet. Every
sync recalculates stored chunk statuses for the current date, even when SRU
reports no changes. XML downloads remain in `nl-wetten-ingest`; SQL upserts run
in transactions. `wetvia embed` fills only `NULL` vectors in bounded batches;
rerun it to resume after the configured batch limit or an interruption. The
model is loaded only when `embed` is invoked. Install the optional local
inference dependency with `uv sync --all-packages --all-groups --extra embeddings`
before running it.

The stored vector defaults to 1024 dimensions, matching the initial
`Vector(1024)` migration. The database records the active model ID and dimension,
and the job refuses to mix vector spaces. To switch models at the same
dimension, clear all existing vectors, run `wetvia embed` with the new
`EMBEDDING_MODEL`, then rebuild `ix_chunk_embedding_hnsw` (for example,
`UPDATE chunk SET embedding = NULL;` before the new run). To change dimensions,
add a schema migration that clears old vectors, changes `chunk.embedding` to
`vector(N)`, and rebuilds the HNSW index; then set `EMBEDDING_DIMENSION=N` and
the new `EMBEDDING_MODEL` before re-embedding. The runtime reads the migrated
PostgreSQL vector width, so supporting a new model dimension needs no application
code change.

If a passage exceeds the model context, the adapter tokenizes it without
truncation, splits at paragraph/sentence/list punctuation where possible, and
uses overlapping windows (up to 32 tokens). It repeats the passage heading
when the context budget allows, then length-weights and normalizes the window
vectors into one chunk vector.

## Retrieval

`GET /api/search?q=...&peildatum=YYYY-MM-DD` returns up to eight ranked legal
chunks; `k` and `include_future=true` are optional. The pg adapter runs Dutch
full-text and cosine-vector candidates in one SQL statement, fuses them with
RRF, and validates that the query model matches the stored embedding-space
identity. Query embedding is formatted with the multilingual-E5 instruction and
run off the event loop. The model loads on the first search request, not during
API startup. `GET /api/sources/{chunk_id}` returns the chunk text and legal
provenance used for its citation.

Both candidate rankings apply inclusive validity dates in SQL and exclude
repealed articles. `include_future=true` also searches states whose start date
is after the requested date; returned legal status is calculated against that
requested date. An exact article reference receives a small `0.01` score nudge
only when its exact label already appears in the top-30 FTS or vector candidates;
it does not add same-numbered articles from unrelated regulations.

The data schema requires PostgreSQL with pgvector. SQLite migration tests cover
Alembic URL selection only; CI runs retrieval, migration, ingest, and embedding
job integration tests on its PostgreSQL+pgvector service.

The public `Retriever` port supports `fts`, `vector`, and `hybrid` search modes;
`hybrid` remains the default used by the API. FTS-only evaluation skips query
embedding and embedding-space validation, so lexical behavior can be measured
without loading the embedding model. FTS and vector modes rank only their own
candidate stream; the exact-article score boost applies only in hybrid mode.

## Answer pipeline

`wetvia.answer.AnswerPipeline` combines the public retriever and LLM provider
ports. It searches hybrid mode for up to eight chunks, sends schema-constrained
JSON at temperature `0.2`, validates the requested date, and converts only
returned labels such as `[1]` into the corresponding retrieved chunk UUIDs.
Empty retrieval returns a deterministic `onzeker` answer without calling the
provider. The packaged Dutch prompt is `wetvia.answer.prompts/answer_nl.md`.

Source context is limited to 8,000 budget units. Bootstrap currently injects a
UTF-8 byte-length upper bound, which may truncate earlier than the model's real
tokenizer; it is not reported as an exact token count. Deployments can inject a
counter for their generator tokenizer. No chat HTTP route is wired yet.

Lagen, van hoog naar laag: `bootstrap`, `api` | `cli`, `answer` | `dossier` | `documents`, `retrieval` | `ingest` | `citations` | `rules` | `llm`, `embeddings` | `db`, `core`. Elke module heeft een `AGENTS.md`.

```bash
uv run ruff check
uv run ruff format --check
uv run mypy src
uv run pytest
uv run lint-imports
```
