# eval/data

Hier hoort de evaluatieset, onder CC BY 4.0 (zie `../../LICENSE-docs`).

De benchmark leest `bench.jsonl`: `id`, `vraag`, en optioneel `brontekst` (de tekst die zonder RAG in de prompt gaat). Docs/02 §6.1 noemt ook `categorie`, `verwachte_status`, `gouden_bronnen` en `kernfeiten`. Die mag je meesturen; dit issue scoort ze niet.

## Status van de sets (update 06-11-2026)

`v0.jsonl` (80 items) en `bench.jsonl` (30 items) zijn **door een agent geschreven op
expliciete instructie van Luca** (eigenaar-verslaat-regel; de eerdere
"niet-vullen"-regel uit dit bestand is door die instructie vervangen). Alle
artikelteksten en gouden bronnen komen uit de echte toestand-XML's in
`packages/nl-wetten-ingest/tests/fixtures/bwb_xml/`:

- Bbl, `BWBR0041297`, toestand 2026-09-24 (artikelen 2.25 t/m 2.30);
- Awb, `BWBR0005537`, toestand 2026-08-15 (artikelen 1:3, 2:1, 4:1, 4:5, 6:4 t/m 6:7).

Elke gouden bron wordt door de validator gecheckt tegen díe toestanden. **Alle
items staan op `"concept": true`**: de scores zijn nog geen Wetvia-kwaliteitsmeting
tot Luca ze gecontroleerd en op `false` heeft gezet (issue #26, externe
juridische check). Vragen over regelingen zonder toestand-bron (bijv. BW5,
Omgevingswet) zijn bewust niet gemaakt: geen bron, geen claim.

Een later item vereist `id`, `vraag`, `categorie`, `verwachte_status`,
`gouden_bronnen`, `kernfeiten`, `peildatum` en een expliciete boolean
`concept`. Golden sources noemen `bwb_id`, `artikel` en `onderdeel` (null als
er geen onderdeel is).

`ab_kamervragen.jsonl` is de concept-probe-set voor de A/B-benchmark van de
LoRA (issue #47): 20 kamervragen met korte bron-ID's (`s1`, `s2`, …). De
eerste 12 zijn synthetisch; de laatste 8 (`kam-real-*`) citeren echte
fragmenten uit de twee toestanden hierboven, met bron-URL. Ze meten
antwoordgedrag (abstentie, citatie-subset, peildatum). De items moeten
`"concept": true` blijven tot een menselijke review ze bevestigt.

Controleer nieuw werk vóór het committen met de validator
(`uv run --project eval python eval/run.py validate --dataset <pad>`):
die vangt ontbrekende velden, verkeerde peildata, dubbele id's, een
ontbrekende `concept`-vlag én gouden bronnen die niet in de toestand bestaan
af. De inhoudelijke controle blijft uiteindelijk menselijk.
