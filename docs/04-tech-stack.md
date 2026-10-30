# 04. Tech stack en repostructuur

## Keuzes

| Laag | Keuze | Waarom | Alternatief (afgewezen) |
|---|---|---|---|
| Frontend | **SvelteKit 2 + Svelte 5 (runes), TypeScript** | Jouw wens; klein, snel, SSR/SPA | Next.js: zwaarder, en geen leerdoel |
| UI-kit | **Tailwind CSS 4 + shadcn-svelte** (bits-ui) | Toegankelijke primitives, geen lock-in | Skeleton UI |
| Chat-streaming | **SSE** (`text/event-stream`) van FastAPI → `fetch` + ReadableStream | Eenvoudiger dan WebSockets en werkt via proxies | WebSockets |
| Client-opslag | **IndexedDB** via `idb-keyval`/Dexie | Gesprekken blijven op het apparaat (privacy) | Server-DB per gebruiker (pas met accounts) |
| Backend | **Python 3.12 + FastAPI + Pydantic v2 + uvicorn** | Jouw wens; Pydantic → JSON Schema voor structured output | Django: te zwaar |
| Pakketbeheer | **uv** (Python), **pnpm** (JS) | Snel en reproduceerbaar (lockfiles) | poetry, npm |
| LLM-client | **`openai` Python SDK** tegen een OpenAI-compatibel endpoint (Ollama `/v1`, Scaleway, vLLM) + een dunne `LLMProvider`-interface voor Ollama-specifieke `format`/`think` | Eén codepad voor lokaal en cloud | LangChain / LlamaIndex: te veel abstractie, verbergt wat je wilt leren |
| Lokale inferentie | **Ollama** (3070 + M3); optioneel **llama.cpp server** | Eenvoudig, GGUF, structured outputs | LM Studio (niet scriptbaar in CI) |
| Database | **PostgreSQL 16 + pgvector** (Docker-image `pgvector/pgvector:pg16`) | Eén DB voor metadata, full-text (`dutch`) én vectoren; joins op geldigheidsdatum | Qdrant/Chroma: extra service, en filteren op datums is minder prettig |
| Migraties/ORM | **SQLAlchemy 2 + Alembic** (psycopg 3) | Standaard, typed | SQLModel |
| Embeddings | **sentence-transformers** met `intfloat/multilingual-e5-large-instruct` (1024 dims) | Zie 02 §1 | — |
| Ingest | **httpx** + **lxml** (BWB/CVDR XML), **Typer**-CLI (`wetvia ingest bwb --ids ...`) | Snel en testbaar | Scrapy |
| Documenten genereren | **docxtpl** (DOCX-template) + **WeasyPrint** (HTML → PDF) | Templates zijn editbaar in Word | python-docx van scratch |
| Documenten parsen (fase 2) | **Docling** (PDF/DOCX → structuur), [PyPI](https://pypi.org/project/docling/) | Lokaal, MIT, goede tabelherkenning | unstructured |
| Eval | **pytest** + eigen runner (`eval/run.py`) → JSON + Markdown-rapport | Transparant, geen black box | Ragas/DeepEval (kan later als vergelijking) |
| Fine-tuning (fase 3) | **Unsloth** + TRL, notebooks in `training/` | Zie 02 §7 | Axolotl |
| Lint/format | **ruff** + **mypy** (Python), **eslint + prettier + svelte-check** (TS) | | |
| Tests | **pytest**, **vitest**, **Playwright** (1-2 e2e-smoke-tests) | | |
| CI | **GitHub Actions**: lint + tests per PR; eval nightly/handmatig (met een Scaleway-key als repo-secret) | Gratis voor public repos | |
| Deploy | **Docker Compose** (`db`, `api`, `web`; Ollama draait op de host). Fase 2: een demo-VPS (EU) met cloudmodus | | Kubernetes: overkill |
| Licentie | **AGPL-3.0** (code), **CC BY 4.0** (docs + eval-set) | Zie README | |

### Security en privacy (basis)

- **Geheimen** alleen in `.env` (in `.gitignore`), met een `.env.example` met placeholders. Gebruik `pydantic-settings`. **Commit nooit een key.** Activeer GitHub secret scanning en push protection.
- **Rate limiting** (`slowapi`) op `/chat` en `/dossier` zodra er een publieke demo is.
- **Prompt-injectie:** bron-chunks gaan als data in de prompt (tussen duidelijke delimiters), en het systeem negeert instructies in geüploade documenten. Eval-categorie F test dit.
- **Logging:** standaard **geen** vragen loggen. Een debug-log alleen lokaal en opt-in. Geen analytics van derden.
- **Uploads (fase 2):** max. 10 MB, alleen PDF/DOCX, geparsed in een subprocess met timeout, na verwerking verwijderd, BSN-redactie (regex + 11-proef).
- **Afhankelijkheden:** Dependabot + `pip-audit`/`pnpm audit` in CI.

## Repostructuur (monorepo)

```
wetvia-ai/
├─ README.md
├─ LICENSE                      # AGPL-3.0
├─ LICENSE-docs                 # CC BY 4.0 (docs/, eval/data/)
├─ CONTRIBUTING.md              # incl. "agent-ready"-uitleg
├─ SECURITY.md
├─ docker-compose.yml           # db, api, web
├─ .env.example
├─ .github/
│  ├─ workflows/{ci.yml, eval.yml, drift-check.yml}
│  ├─ ISSUE_TEMPLATE/{agent-task.yml, bug.yml}
│  └─ pull_request_template.md
├─ docs/                        # dit plan + ADR's
│  └─ adr/0001-llm-provider-abstraction.md …
├─ apps/
│  ├─ web/                      # SvelteKit
│  │  ├─ src/lib/components/{chat, sources, dossier, ui}/
│  │  ├─ src/lib/stores/        # gesprekken (IndexedDB)
│  │  ├─ src/lib/api/           # typed client (gegenereerd uit OpenAPI)
│  │  └─ src/routes/{+page.svelte, dossier/, instellingen/, over/}
│  └─ api/                      # FastAPI
│     ├─ pyproject.toml
│     ├─ src/wetvia/
│     │  ├─ main.py             # app + routers
│     │  ├─ config.py           # pydantic-settings
│     │  ├─ llm/                # provider.py, ollama.py, openai_compat.py, prompts/
│     │  ├─ retrieval/          # hybrid.py, rrf.py, filters.py
│     │  ├─ rules/              # bbl_dakkapel.py (regels-als-code) + tests
│     │  ├─ answer/             # schema.py (AnswerV1), pipeline.py, verifier.py
│     │  ├─ dossier/            # schema.py, render_docx.py, templates/
│     │  ├─ db/                 # models.py, alembic/
│     │  └─ api/                # routes: chat.py, sources.py, dossier.py, health.py
│     └─ tests/
├─ packages/
│  └─ nl-wetten-ingest/         # los herbruikbaar pakket (Apache-2.0)
│     └─ src/nl_wetten_ingest/{bwb.py, cvdr.py, tk.py, dso.py, parse_bwb_xml.py, cli.py}
├─ eval/
│  ├─ data/v0.jsonl             # CC BY 4.0
│  ├─ rubrics/                  # judge-prompts
│  ├─ run.py                    # draait pipeline + metrics
│  └─ reports/                  # gegenereerde rapporten (per release)
└─ training/                    # fase 3
   ├─ DATA_CARD.md
   ├─ generate_sft.py
   └─ notebooks/qwen35_lora.ipynb
```

## Lokale ontwikkelomgeving

```bash
# eenmalig
ollama pull qwen3.5:9b && ollama pull qwen3.5:4b
cp .env.example .env            # vul alleen de waarden in die je nodig hebt
docker compose up -d db
cd apps/api && uv sync && uv run alembic upgrade head
uv run wetvia ingest bwb --preset mvp      # Omgevingswet-kern + Awb + BW5
uv run fastapi dev src/wetvia/main.py
cd ../web && pnpm i && pnpm dev
```

### MVP-corpus (`--preset mvp`)

| Regeling | BWB-ID (geverifieerd via SRU) |
|---|---|
| Omgevingswet | BWBR0037885 |
| Omgevingsbesluit | BWBR0041278 |
| Besluit bouwwerken leefomgeving (Bbl) | BWBR0041297 |
| Besluit activiteiten leefomgeving (Bal) | BWBR0041330 |
| Omgevingsregeling | BWBR0045528 |
| Algemene wet bestuursrecht (Awb) | BWBR0005537 |
| Burgerlijk Wetboek Boek 5 (o.a. art. 5:50 vensters/burenrecht) | BWBR0005288 |

### Bron-API's

| Bron | Endpoint | Licentie | Auth |
|---|---|---|---|
| BWB (wetten) | `https://zoekservice.overheid.nl/sru/Search?operation=searchRetrieve&version=2.0&x-connection=BWB&query=…` | CC0 | geen |
| CVDR (lokale regelingen) | idem, `x-connection=cvdr` | CC0 | geen |
| Officiële bekendmakingen | `https://repository.overheid.nl/sru/Search?x-connection=officielepublicaties&…` | CC0 | geen |
| Tweede Kamer | `https://gegevensmagazijn.tweedekamer.nl/OData/v4/2.0/Zaak?$filter=Soort eq 'Wetgeving'…` | CC0 | geen |
| DSO Toepasbare regels zoeken v2 | `https://service.omgevingswet.overheid.nl/publiek/toepasbare-regels/api/zoekinterface/v2/…` | CC BY 4.0 (vermelden: "Bron: DSO-LV") | gratis `x-api-key`, [aanvragen](https://developer.omgevingswet.overheid.nl/formulieren/api-key-aanvragen-0/) |
| DSO Omgevingsdocument presenteren v8 (fase 2) | zie [API-register](https://developer.omgevingswet.overheid.nl/api-register/beschikbare-api-services/) | CC BY 4.0 | idem |

> De DSO-key vervalt na een jaar zonder gebruik ([fair use](https://developer.omgevingswet.overheid.nl/services/fair-use-policy/)). Zet een ping in `drift-check.yml`.

## Kosten (per maand)

| Post | MVP | Met publieke demo |
|---|---|---|
| Lokale inferentie | €0 (eigen hardware) | — |
| Scaleway cloud-LLM + judge | €0-3 (1M gratis tokens) | €3-10 |
| GitHub (public repo, Actions) | €0 | €0 |
| VPS voor de demo (EU, 4 GB RAM; alleen cloudmodus, geen GPU) | — | ~€5-8 *(prijs zelf verifiëren)* |
| Domein (wetvia.nl, als het vrij is) | — | ~€1 |
| Fine-tune runs (fase 3, eenmalig) | — | €5-15 totaal |
| **Totaal** | **≤ €3** | **≤ €20** ✅ binnen €25 |
