# Wetvia AI *(werknaam)*

> Een privacyvriendelijke, lokaal te draaien AI-assistent voor Nederlandse wet- en regelgeving. Elk antwoord verwijst naar een officiële bron, en hij zegt het eerlijk als hij iets niet zeker weet.

**Status:** concept / pre-MVP (november 2026). Er is nog geen werkende code. Deze repo bevat het onderzoek, het plan en de issues voor de MVP.

---

## Wat is Wetvia?

Wetvia is een chatassistent, vergelijkbaar met ChatGPT, maar dan:

- **specifiek voor Nederlands recht en overheidsprocessen:** wetten, AMvB's, gemeentelijke regels, wetsvoorstellen en vergunningsprocedures;
- **gebaseerd op bronnen:** elk juridisch antwoord komt uit een opgehaalde officiële tekst (wetten.overheid.nl, lokaleregelgeving.overheid.nl, officielebekendmakingen.nl, DSO/Omgevingsloket, Tweede Kamer) en citeert die met artikelnummer en geldigheidsdatum;
- **lokaal te draaien:** het model draait op je eigen machine (Ollama / llama.cpp / MLX), zodat geüploade documenten je computer niet verlaten. Wie dat wil, kan een EU-gehoste cloudmodus aanzetten;
- **eerlijk over onzekerheid:** zonder bron geeft Wetvia geen antwoord. Hij zegt dan dat hij het niet weet en verwijst naar de juiste instantie.

### MVP (eerste versie)

> **"Mag ik een dakkapel of uitbouw plaatsen, en wat moet ik indienen?"**

Een burger beschrijft zijn plan in gewone taal. Wetvia:

1. legt uit welke rijksregels gelden (Bbl, Omgevingsbesluit, Bal), met citaten en links;
2. zegt of het plan waarschijnlijk vergunningvrij, meldingsplichtig of vergunningplichtig is, met een duidelijk voorbehoud en een link naar de officiële [Vergunningcheck](https://omgevingswet.overheid.nl/checken);
3. maakt een **conceptdossier** (Markdown, DOCX of PDF) met projectomschrijving, checklist van indieningsvereisten, ontbrekende gegevens en bronnenlijst, klaar om in het Omgevingsloket over te nemen.

Zie [docs/05-mvp-ontwikkelplan.md](docs/05-mvp-ontwikkelplan.md) voor de afbakening.

## Documentatie

| # | Document | Inhoud |
|---|---|---|
| 01 | [Kritische beoordeling](docs/01-kritische-beoordeling.md) | Risico's, concurrenten, juridisch kader, wat wel en niet te doen |
| 02 | [AI-architectuur](docs/02-ai-architectuur.md) | Modelkeuze, RAG vs fine-tuning, structured output, evaluatie |
| 03 | [UI/UX](docs/03-ui-ux.md) | Designprincipes, schermen, kleuren, logo, toegankelijkheid |
| 04 | [Tech stack](docs/04-tech-stack.md) | SvelteKit, FastAPI, Postgres+pgvector, serving, security, repo-structuur |
| 05 | [MVP-ontwikkelplan](docs/05-mvp-ontwikkelplan.md) | Planning per week, latere fases, risico's, budget |

De issues voor de MVP staan op GitHub, met labels en milestones: [issues](https://github.com/lucasabella/wetvia-ai/issues) en [milestones](https://github.com/lucasabella/wetvia-ai/milestones). Ze zijn zo geschreven dat een coding agent (bijv. een Cursor cloud agent) ze zelfstandig kan oppakken.

## Architectuur in één oogopslag

```
SvelteKit (UI)  ──►  FastAPI (Python)  ──►  Retrieval: Postgres + pgvector + full-text (NL)
                          │                      ▲
                          │                      └── Ingest: BWB (SRU), CVDR, DSO, Tweede Kamer
                          ▼
              LLM-provider (OpenAI-compatibel):
              • lokaal: Ollama/llama.cpp → Qwen3.5-9B (Q4_K_M)  [RTX 3070 8 GB / M3 16 GB]
              • cloud:  Scaleway Generative APIs → Qwen3.8-27B (EU, Parijs)
```

## Belangrijke disclaimer

Wetvia AI is **geen juridisch advies** en geen vervanging van een advocaat, jurist of de gemeente. Antwoorden kunnen fouten bevatten. Gegenereerde documenten zijn **concepten** die je zelf moet controleren. Aan de uitkomst van een vergunningcheck kun je geen rechten ontlenen. Dat geldt zelfs voor de officiële Vergunningcheck ([ABRvS 22 februari 2023, ECLI:NL:RVS:2023:736](https://uitspraken.rechtspraak.nl/details?id=ECLI:NL:RVS:2023:736)). Het bevoegd gezag (meestal de gemeente) beslist. Je praat met een AI-systeem (AI-verordening, art. 50).

## Licentie: **AGPL-3.0** (code), **CC BY 4.0** (docs en evaluatieset)

De licentieteksten staan in [LICENSE](LICENSE) (AGPL-3.0, broncode) en [LICENSE-docs](LICENSE-docs) (CC BY 4.0, `docs/` en `eval/data/`).

Waarom AGPL-3.0 en niet Apache-2.0:

- **Het is een webapplicatie.** Onder Apache-2.0 kan iedereen Wetvia als gesloten SaaS aanbieden zonder iets terug te geven. AGPL verplicht wie een aangepaste versie via een netwerk aanbiedt om de broncode te delen. Dat past bij een project dat draait op publieke, CC0-gelicentieerde overheidsdata.
- **Overheden en open source:** de Rijksoverheid werkt met een "open, tenzij"-beleid voor broncode, en copyleft-licenties (EUPL/AGPL) zijn in de publieke sector gangbaar. **EUPL-1.2** is een prima alternatief als je overheidsgebruik wilt stimuleren. EUPL is compatibel met AGPL en juridisch in het Nederlands beschikbaar.
- **Portfolio:** voor werkgevers maakt de licentie niets uit. Ze kijken naar de code.
- **Nadeel:** bedrijven gebruiken AGPL-code minder snel als bibliotheek. Daarom krijgen losse, herbruikbare pakketten (bijv. `packages/nl-wetten-ingest`) **Apache-2.0**.
- **Data:** overheidsbronnen zijn CC0 (BWB, CVDR, Officiële bekendmakingen, Tweede Kamer) of CC BY 4.0 (DSO, verplicht naamsvermelding: zie [Bronnen en naamsvermelding](#bronnen-en-naamsvermelding)).

**Advies:** begin met AGPL-3.0. Die keuze is later nog om te zetten naar EUPL-1.2 zolang jij de enige auteur bent.

## Bronnen en naamsvermelding

- Wet- en regelgeving: [wetten.overheid.nl](https://wetten.overheid.nl) / KOOP, Basis Wetten Bestand (CC0 1.0)
- Lokale regelgeving: [lokaleregelgeving.overheid.nl](https://lokaleregelgeving.overheid.nl) / CVDR (CC0 1.0)
- Officiële bekendmakingen: [officielebekendmakingen.nl](https://www.officielebekendmakingen.nl) (CC0 1.0)
- Parlementaire informatie: [Tweede Kamer Open Data Portaal](https://opendata.tweedekamer.nl) (CC0 1.0)
- Omgevingswet: [Digitaal Stelsel Omgevingswet](https://developer.omgevingswet.overheid.nl) (CC BY 4.0, "Bron: DSO-LV")

## Bijdragen

Issues met het label `agent-ready` zijn compleet gespecificeerd, met acceptatiecriteria. Lees eerst `docs/04-tech-stack.md` (repo-structuur en conventies).
