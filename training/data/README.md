# Lokale trainingsdata

Zet een gereviewde `sft.jsonl` hier neer als die klaar is. JSONL-bestanden in deze map worden door `.gitignore` uitgesloten. Voeg nooit ruwe trainingsdata of persoonsgegevens toe aan Git.

Verwachte bestanden in deze map (allen lokaal, niet in Git):

- `bronnen.jsonl` — CC0-bronfragmenten; één JSON-object per regel met `id`, `tekst`, `bron_uri`, `peildatum`, `status` (`geldig` of `voorstel`), `documentsoort` en `licentie` (zie `../README.md`, "Dataflow").
- `sft-batch-requests.jsonl` — batch-requestregels voor de teacher (uit `--mode requests`).
- `sft-concept-*.jsonl` — nog NIET goedgekeurde kandidaten; nooit direct trainen.
- `review-steekproef-*.jsonl` — de menselijke steekproef (minimaal 100, issue #34).
- `sft.jsonl` — alleen de rijen die door review zijn gegaan; hier leest de trainer van.
