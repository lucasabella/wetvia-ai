# ADR 0002: Modulaire monoliet

- Status: aangenomen (2026-10-30)
- Besluitnemer: Luca Sabella

## Context

Wetvia is één codebase voor een klein team, met een chat-API, batch-ingest en een aparte frontend. Een inference-workload (Ollama of een EU-cloudendpoint) heeft andere hardware dan de API. Microservices zouden tracing, een gateway en meerdere deploys vragen zonder een gemeten reden.

De volledige afweging en de bronnen staan in [docs/06-architectuur-structuur.md](../06-architectuur-structuur.md).

## Besluit

Geen microservices. Wetvia is een modulaire monoliet: één `wetvia`-pakket, met harde grenzen die `import-linter` controleert.

Processen uit die ene codebase:

| Proces | Wat |
| --- | --- |
| `web` | SvelteKit |
| `api` | FastAPI, pakket `wetvia` |
| `worker` | Hetzelfde pakket, via `cli.py` |
| `db` | Postgres 16 + pgvector |
| inference | Ollama op de host, of een OpenAI-compatibel endpoint. Geen eigen code |

Alleen `bootstrap.py` koppelt adapters. `nl_wetten_ingest` blijft een los Apache-2.0-pakket en kent `wetvia` niet. `training/` blijft buiten de uv-workspace.

## Pad naar afsplitsen

Alleen bij een gemeten reden, en zonder de module te herschrijven:

| Volgorde | Kandidaat | Trigger |
| --- | --- | --- |
| 0 | Inference | Al extern: andere adapter of `LLM_BASE_URL` |
| 1 | Embeddings | Het api-image wordt te zwaar, of de GPU moet gedeeld worden: een `Embedder`-adapter over HTTP |
| 2 | Documentparsing | Onvertrouwde of zware input: `documents` achter een port, adapter roept een sandbox aan |
| 3 | Ingest-worker | Eigen schema of schaal: het is al een apart proces; alleen het deploy-artefact splitsen |

`rules`, `citations`, `answer` en `retrieval` blijven in-process.

## Gevolgen

- Elke laag in het contract bestaat nu als lege module, met een korte `AGENTS.md`.
- `uv run lint-imports` hoort bij de api-checks en, zodra die er is, bij CI (issue #7).
- `docs/04-tech-stack.md` beschrijft dezelfde processen en mappen als docs/06.
