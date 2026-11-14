# ADR 0003: Van vergunningsassistent naar benchmark en distillatie

- Status: aangenomen (2026-11-14)
- Besluitnemer: Luca Sabella

## Context

De repo is opgezet als lokale assistent voor vergunningvragen (dakkapel, conceptdossier, burgerchat). Het fundament staat: BWB-ingest, embeddings, hybride zoeken, een LLM-aansluiting. De onderzoeksvraag is verschoven. De vraag is nu of een klein lokaal model, geoefend op opgaven van een groot open model, zijn basismodel verslaat en in de buurt komt van dat grote model, op taken over de Tweede Kamer en de rijksoverheid.

De afweging, de fasen, de begrippen en het issuevoorstel staan in [docs/07-benchmark-en-distillatie-plan.md](../07-benchmark-en-distillatie-plan.md).

## Besluit

De monoliet uit [ADR 0002](0002-modulaire-monoliet.md) blijft. Geen microservices, geen extra laag in het import-linter-contract tot de map er is.

De nieuwe onderdelen zitten op deze plekken:

| Onderdeel | Plek |
|---|---|
| Bronclients | `packages/nl-wetten-ingest` |
| Opslag | `wetvia.ingest` |
| Zoek-baseline | `wetvia.retrieval` |
| Toets en overlapcheck | `packages/nl-overheid-benchmark` (importeert `wetvia` niet) |
| Oefenstof en LoRA | `training/`, buiten de uv-workspace |
| Scores | `eval/` |
| Demo | bestaand `apps/web`, pas nadat de tabel er is |

`wetvia.rules`, `wetvia.dossier` en `wetvia.documents` blijven leeg.

Oefendocumenten en toetsdocumenten zijn gescheiden op document, Kamerzaak en periode. De vraagzinnen van de toets schrijft een ander model dan de leraar. Het juiste antwoord komt uit het brondocument.

## Gevolgen

- [docs/01](../01-kritische-beoordeling.md) tot en met [docs/05](../05-mvp-ontwikkelplan.md) blijven staan als onderzoek van de oude assistent. Waar ze deze koers tegenspreken, wint docs/07.
- De demo van 6 december 2026 vervalt.
- Issues worden pas gesloten, herschreven of herlabeld na een menselijke review van de bijlage in docs/07. Deze ADR doet dat niet.
