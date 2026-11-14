# Wetvia AI *(werknaam)*

> Kan een klein model op je eigen computer, na oefenen op opgaven van een groot open model, een vaste toets over de Tweede Kamer en de rijksoverheid beter maken dan zonder die oefening? En komt het in de buurt van het grote model?

**Status:** koerswijziging (14 november 2026). Het fundament staat: BWB-ingest, embeddings, hybride zoeken, een LLM-aansluiting, CI. De toets, de oefenstof en de vergelijking moeten nog gebouwd worden. Het plan staat in [docs/07-benchmark-en-distillatie-plan.md](docs/07-benchmark-en-distillatie-plan.md).

De eerdere vergunningsassistent (dakkapel, conceptdossier, burgerchat) is niet meer het doel. Die plannen blijven in docs/01 tot en met docs/05 staan als onderbouwing van het fundament.

---

## Wat deze repo meet

De toets komt uit openbare stukken: [officielebekendmakingen.nl](https://www.officielebekendmakingen.nl), de [Tweede Kamer open data](https://opendata.tweedekamer.nl) en [wetten.overheid.nl](https://wetten.overheid.nl). Elke vraag wijst naar een bron. Het juiste antwoord komt uit dat document. Een groot model schrijft de oefenopgaven. Een ander model schrijft de vraagzinnen van de toets. Oefendocumenten en toetsdocumenten komen uit een andere periode.

Daarna oefent een klein model (orde 1 tot 8 miljard parameters) met een dun extra bestand, een LoRA. De tabel vergelijkt vier rijen: het kleine model zonder oefening, hetzelfde model met zoekfunctie, het grote model, en het kleine model na het oefenen. Ook de onderdelen waar het kleine model slechter is, komen in de tabel.

Uitleg van die woorden, de fasen, het geld en de uren: [docs/07](docs/07-benchmark-en-distillatie-plan.md).

## Documentatie

| # | Document | Inhoud |
|---|---|---|
| 07 | [Benchmark en distillatie](docs/07-benchmark-en-distillatie-plan.md) | De koers: begrippen, pijplijn, fasen, grenzen, licenties, issuevoorstel |
| 06 | [Architectuur en structuur](docs/06-architectuur-structuur.md) | Modulaire monoliet, import-linter, waar de nieuwe onderdelen landen |
| 04 | [Tech stack](docs/04-tech-stack.md) | SvelteKit, FastAPI, Postgres+pgvector, bron-API's |
| 02 | [AI-architectuur](docs/02-ai-architectuur.md) | Modelmaten, zoeken, prijzen. Geschreven voor de oude assistent; de maten en de prijs blijven bruikbaar |
| 01 | [Kritische beoordeling](docs/01-kritische-beoordeling.md) | Onderzoek van 30 oktober 2026 naar de oude assistent |
| 03 | [UI/UX](docs/03-ui-ux.md) | Schermen van de oude assistent. De demo wacht tot de tabel er is |
| 05 | [MVP-ontwikkelplan](docs/05-mvp-ontwikkelplan.md) | Oude weekplanning. De demo van 6 december 2026 vervalt |

Architectuurbesluiten: [ADR 0002](docs/adr/0002-modulaire-monoliet.md) (monoliet) en [ADR 0003](docs/adr/0003-benchmark-en-distillatie.md) (deze koers).

Issues: [issues](https://github.com/lucasabella/wetvia-ai/issues). Het voorstel welke open issues sluiten, bevriezen of herschrijven staat in de bijlage van docs/07. Deze README wijzigt geen issues.

## Architectuur in één oogopslag

```
Bronnen (BWB, Tweede Kamer, officiële bekendmakingen)
        │
        ▼
nl-wetten-ingest  →  wetvia.ingest  →  Postgres
        │                              │
        │                              ▼
        │                     wetvia.retrieval   (zoek-baseline)
        ▼
export: oefendocumenten │ toetsdocumenten
        │                      │
        ▼                      ▼
training/ (leraar, LoRA)   nl-overheid-benchmark
        │                      │
        └──────────┬───────────┘
                   ▼
              eval/  →  tabel van vier rijen
```

Het import-linter-contract in `apps/api/pyproject.toml` blijft zoals het is. Het toetspakket en `training/` zitten buiten het pakket `wetvia`. Details: [docs/06](docs/06-architectuur-structuur.md) en [docs/07](docs/07-benchmark-en-distillatie-plan.md).

## Belangrijke disclaimer

Antwoorden van een model in deze repo zijn **geen juridisch advies** en geen vervanging van een advocaat, jurist of de overheid. Een score op de toets zegt niets over een echte vergunning of een echt Kamerstuk buiten de vraag. De toets citeert alleen tekst die in een openbaar document staat.

## Licentie: **AGPL-3.0** (code), **CC BY 4.0** (docs en evaluatieset)

De licentieteksten staan in [LICENSE](LICENSE) (AGPL-3.0, broncode) en [LICENSE-docs](LICENSE-docs) (CC BY 4.0, `docs/` en `eval/data/`).

Waarom AGPL-3.0 en niet Apache-2.0:

- **Het is een webapplicatie.** Onder Apache-2.0 kan iedereen Wetvia als gesloten SaaS aanbieden zonder iets terug te geven. AGPL verplicht wie een aangepaste versie via een netwerk aanbiedt om de broncode te delen. Dat past bij een project dat draait op publieke, CC0-gelicentieerde overheidsdata.
- **Overheden en open source:** de Rijksoverheid werkt met een "open, tenzij"-beleid voor broncode, en copyleft-licenties (EUPL/AGPL) zijn in de publieke sector gangbaar. **EUPL-1.2** is een prima alternatief als je overheidsgebruik wilt stimuleren. EUPL is compatibel met AGPL en juridisch in het Nederlands beschikbaar.
- **Nadeel:** bedrijven gebruiken AGPL-code minder snel als bibliotheek. Daarom krijgen losse, herbruikbare pakketten (bijv. `packages/nl-wetten-ingest` en straks `packages/nl-overheid-benchmark`) **Apache-2.0**. De vragen zelf blijven CC BY 4.0.
- **Data:** overheidsbronnen zijn CC0 (BWB, CVDR, Officiële bekendmakingen, Tweede Kamer) of CC BY 4.0 (DSO, verplicht naamsvermelding: zie [Bronnen en naamsvermelding](#bronnen-en-naamsvermelding)).

**Advies:** begin met AGPL-3.0. Die keuze is later nog om te zetten naar EUPL-1.2 zolang jij de enige auteur bent.

## Bronnen en naamsvermelding

- Wet- en regelgeving: [wetten.overheid.nl](https://wetten.overheid.nl) / KOOP, Basis Wetten Bestand (CC0 1.0)
- Lokale regelgeving: [lokaleregelgeving.overheid.nl](https://lokaleregelgeving.overheid.nl) / CVDR (CC0 1.0)
- Officiële bekendmakingen: [officielebekendmakingen.nl](https://www.officielebekendmakingen.nl) (CC0 1.0)
- Parlementaire informatie: [Tweede Kamer Open Data Portaal](https://opendata.tweedekamer.nl) (CC0 1.0)
- Omgevingswet: [Digitaal Stelsel Omgevingswet](https://developer.omgevingswet.overheid.nl) (CC BY 4.0, "Bron: DSO-LV")

## Bijdragen

Issues met het label `agent-ready` zijn compleet gespecificeerd, met acceptatiecriteria. Lees eerst [docs/07](docs/07-benchmark-en-distillatie-plan.md) (koers) en [docs/04](docs/04-tech-stack.md) (repo-structuur en conventies). Het label op een oud vergunningsissue betekent niet dat die koers nog geldt. De bijlage van docs/07 stelt voor dat label eerst af te halen. Deze repo doet dat niet zelf.

## Skelet en tooling

Python 3.12 met uv (`apps/api`, `packages/nl-wetten-ingest`, `eval`) en pnpm (`apps/web`). Lint en types: ruff, mypy, eslint, svelte-check en TypeScript. De SvelteKit-shell staat in `apps/web`.

## Modelbenchmark

`eval/bench_models.py` meet via Ollama tijd tot het eerste token, tokens/s, schema-validiteit en, als `nvidia-smi` er is, piek-VRAM. Zonder `eval/data/bench.jsonl` schrijft het script een rapport met `niet gemeten` en downloadt het geen modellen. Docs/07 stelt voor om issue #6 te herschrijven tot een hardwarecheck van het 4B-leerlingmodel. Tot die herschrijving blijft dit script een snelheidsmeting, geen kwaliteitsscore.

```bash
ollama list
uv run python eval/bench_models.py
```

Op een RTX 3070 komt VRAM uit `nvidia-smi`. Op een M3 (Ollama via Metal) blijft die kolom `niet beschikbaar`. Tags en de rest van de methode: [eval/README.md](eval/README.md).

```bash
uv sync --all-packages --all-groups
pnpm install

cd apps/api
uv run ruff check
uv run ruff format --check
uv run mypy src
uv run pytest
uv run lint-imports

cd ../../packages/nl-wetten-ingest
uv run ruff check
uv run ruff format --check
uv run mypy src
uv run pytest

cd ../..
pnpm lint
pnpm check
pnpm test
pnpm format:check
```

Het label `agent-ready`, de PR-checklist en dezelfde commando's staan in [CONTRIBUTING.md](CONTRIBUTING.md). Kopieer [`.env.example`](.env.example) naar `.env` als je lokale waarden nodig hebt. Commit nooit `.env`.

## Docker Compose

`docker compose up` start alleen `db`: Postgres 16 met pgvector (`pgvector/pgvector:pg16`). De poort is `127.0.0.1:5432`. Het wachtwoord komt uit `.env` (`POSTGRES_PASSWORD`), niet uit het Compose-bestand. Bij de eerste initialisatie van het volume draait `docker/postgres/init/01-vector.sql` (`CREATE EXTENSION vector`).

```bash
cp .env.example .env
docker compose up -d db
docker compose exec db psql -U wetvia -c "select extversion from pg_extension where extname='vector'"
```

Op een koude start kan `exec` eerder zijn dan Postgres. `docker compose up -d --wait db` wacht op de healthcheck.

`api` en `web` staan in het bestand als build-context, onder de profielen `api` en `web`. Er is nog geen Dockerfile; issue #3 bouwt het FastAPI-skelet parallel. Daarom start een kale `up` ze niet. `worker` (profiel `ingest`) gebruikt hetzelfde image als `api` en het commando `wetvia ingest sync && wetvia embed`. `ollama` (profiel `gpu-linux`) is optioneel. Standaard draait Ollama op de host.

`api` en `worker` krijgen `LLM_BASE_URL=http://host.docker.internal:11434`, met `extra_hosts` zodat die naam op Linux naar de host wijst. Processen op de host houden `LLM_BASE_URL` uit `.env` (`http://127.0.0.1:11434`). Voor het `gpu-linux`-profiel zet je de container-URL op `http://ollama:11434`. Dat profiel gebruikt het officiële image `ollama/ollama` en de NVIDIA Container Toolkit ([Ollama Docker](https://docs.ollama.com/docker)); de poort blijft `127.0.0.1:11434`. Op een Mac draait Ollama op de host, niet in Compose ([docs/06](docs/06-architectuur-structuur.md)).

```bash
docker compose --profile ingest up worker
docker compose --profile gpu-linux up ollama
```

`--profile ingest` en `--profile api` falen bij de build tot `apps/api/Dockerfile` er is. Hetzelfde geldt voor `--profile web` en `apps/web/Dockerfile`.

## training

`training/` valt buiten de uv-workspace. Torch en Unsloth botsen met de dependencies van de API, en een workspace deelt één lockfile. Fine-tuning krijgt later een eigen pyproject en venv. De leden zijn alleen `apps/api` en `packages/nl-wetten-ingest`.
