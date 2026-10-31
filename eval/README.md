# eval

Benchmark- en eval-harness (`wetvia-eval`, AGPL-3.0-only). De vragen in `data/` zijn CC BY 4.0. Die set is nog leeg: geen bron, geen claim.

`eval/bench_models.py` meet lokale Ollama-modellen (issue #6): tijd tot het eerste token, tokens/s, schema-validiteit op een dummy-`AnswerV1`, en piek-VRAM via `nvidia-smi` als dat er is. Chat loopt via de publieke `wetvia.llm`-port, aangemaakt door `wetvia.bootstrap.get_ollama_provider`; de `AnswerV1` JSON Schema wordt tijdens het streamen aan Ollama meegegeven. De volledige JSON wordt na de stream lokaal gevalideerd. Alleen het ophalen van geïnstalleerde tags gebruikt `GET /api/tags` rechtstreeks; de benchmark heeft geen eigen Ollama-chatclient.

`eval/run.py retrieval` vergelijkt de publieke retriever in `fts`, `vector` en
`hybrid`-modus en schrijft Markdown- en JSON-auditrapporten naar
`eval/reports/`. Het datasetpad is verplicht expliciet, zodat een ontbrekende
of onbedoelde dataset niet voor de gecontroleerde set kan doorgaan. Rapporten
bevatten de SHA-256 van de dataset, het geconfigureerde querymodel en dimensie, peildata en
gerangschikte hits.

FTS gebruikt de lexicale rangschikking zonder embeddingmodel. Vector sorteert
op cosine similarity; hybrid combineert beide stromen met RRF en de exacte
artikelboost.

## Evaluatieset

De 30 vragen horen in `eval/data/bench.jsonl`, één JSON-object per regel:

```json
{"id": "…", "vraag": "…", "brontekst": "…", "categorie": "A", "peildatum": "YYYY-MM-DD"}
```

`brontekst` is de gegeven bron in de prompt (nog zonder RAG). Velden uit docs/02 §6.1 (`gouden_bronnen`, `kernfeiten`, `verwachte_status`) mag je meegeven; de benchmark scoort ze nog niet. Verzin geen vragen of artikelteksten. Zonder dit bestand schrijft het script een rapport met `niet gemeten` en roept het geen model aan.

Retrieval-evaluatie gebruikt een apart JSONL-bestand. Elke regel vereist
`id`, `vraag`, `categorie` (`A`–`F`), ISO `peildatum`, `verwachte_status`,
`kernfeiten`, `gouden_bronnen` (met `bwb_id`, `artikel`, `onderdeel`, waarbij
`onderdeel` null mag zijn) en een expliciete boolean `concept`. Zet
`concept: true` op ieder ongereviewd item; zet het pas op false na menselijke
controle. Er is nog geen gecontroleerde retrieval-dataset in de repo: issue
#13 wacht op menselijke juridische review. Conceptfixtures testen alleen de
harness en zijn geen Wetvia-kwaliteitsmeting.

## Draaien

Vanuit de repo-root, met Ollama op de host (`LLM_BASE_URL`, default `http://127.0.0.1:11434`). Controleer de tags eerst met `ollama list`. De defaults komen uit het issue en zijn hier niet tegen een draaiende Ollama gecontroleerd: `qwen3.5:9b`, `qwen3.5:4b`, `gemma4:12b`, `ministral-3:8b`. Ontbreekt een tag, dan slaat het script dat model over.

```bash
uv sync --all-packages --all-groups
ollama list
uv run python eval/bench_models.py
uv run python eval/run.py retrieval --dataset /path/to/reviewed-v0.jsonl
```

Andere tags: `uv run python eval/bench_models.py qwen3.5:9b`. Het rapport komt in `eval/reports/bench-<datum>.md`. Een sjabloon zonder cijfers staat in `eval/reports/bench-template.md`.

Retrieval kan na het schrijven van beide rapporten een drempel toepassen op
overall hybrid recall@8:

```bash
uv run python eval/run.py retrieval --dataset /path/to/reviewed-v0.jsonl --fail-under 0.85
```

De runner stopt met een nonzero exitcode als de drempel niet gehaald wordt of
er geen scorebare items zijn. D/F en items zonder gouden artikelen tellen niet
mee in metric-noemers; de rapporten tonen de aantallen apart. Recall@k telt
distincte `(bwb_id, artikel)`-sleutels binnen de eerste `k` ruwe chunks. MRR
gebruikt de oorspronkelijke chunk-rang van de eerste gouden artikelmatch.

Context staat vast op `num_ctx=16384` en `think` staat uit. Per model gaat er eerst een warm-up-call uit die niet meetelt voor TTFT of tokens/s; VRAM wordt ook tijdens die generatie bemonsterd. De laatste vraag stuurt `keep_alive: 0` zodat Ollama het model ontlaadt na de generatie. `nvidia-smi` wordt tijdens elke generatie iedere 0,1 seconde bevraagd, plus vlak ervoor en erna. Zo blijft de gemeten piek staan, ook als het model na de laatste generatie wordt ontladen. Elke modelrun houdt zijn eigen steekproeven bij. Schema-validiteit telt alleen antwoorden; HTTP-fouten staan apart. Valt alles weg, dan is de status `mislukt`.

### RTX 3070 (8 GB)

Ollama native, niet de Docker-GPU-service. `nvidia-smi` levert de VRAM-kolom (MiB in gebruik op de hele GPU, inclusief andere processen). Docs/02 zet het 9B-model krap in 8 GB bij deze context; past een model niet, dan faalt of skipt Ollama en blijft de rij zonder verzonnen snelheid.

### MacBook Air M3 (16 GB)

Ollama via Metal. `nvidia-smi` is er niet, dus piek-VRAM blijft `niet beschikbaar`. Het script praat alleen met de Ollama HTTP-API, niet met MLX.

## Checks

```bash
cd eval && uv run ruff check && uv run ruff format --check && uv run mypy src && uv run pytest
```

CI draait die checks zonder Ollama en zonder modelgewichten.
