# eval/data

Hier hoort de handmatig gecontroleerde evaluatieset, onder CC BY 4.0 (zie `../../LICENSE-docs`).

De benchmark leest `bench.jsonl`: `id`, `vraag`, en optioneel `brontekst` (de tekst die zonder RAG in de prompt gaat). Docs/02 §6.1 noemt ook `categorie`, `verwachte_status`, `gouden_bronnen` en `kernfeiten`. Die mag je meesturen; dit issue scoort ze niet.

Deze map bevat nog geen retrieval-vragen. Issue #13 staat nog op `needs-human`;
maak of vul `v0.jsonl` niet met agent-gegenereerde juridische vragen of bronnen.
Een later item vereist `id`, `vraag`, `categorie`, `verwachte_status`,
`gouden_bronnen`, `kernfeiten`, `peildatum` en een expliciete boolean
`concept`. Golden sources noemen `bwb_id`, `artikel` en `onderdeel` (null als
er geen onderdeel is). Conceptfixtures horen buiten deze map of moeten
`"concept": true` markeren. Hun scores zijn geen Wetvia-kwaliteitsmeting.
