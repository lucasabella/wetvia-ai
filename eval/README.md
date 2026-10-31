# eval

Benchmark- en eval-harness (`wetvia-eval`, AGPL-3.0-only). De vragen in `data/` zijn CC BY 4.0. Die set is nog leeg: geen bron, geen claim.

`eval/bench_models.py` meet lokale Ollama-modellen (issue #6): tijd tot het eerste token, tokens/s, schema-validiteit op een dummy-`AnswerV1`, en piek-VRAM via `nvidia-smi` als dat er is. De client `OllamaProvider` staat in dit pakket. Issue #5 bouwt de `wetvia.llm`-port; deze benchmark hangt daar nog niet aan.

Er is nog geen `run.py`. Dat is de latere eval-runner, niet deze bake-off.

## Evaluatieset

De 30 vragen horen in `eval/data/bench.jsonl`, één JSON-object per regel:

```json
{"id": "…", "vraag": "…", "brontekst": "…", "categorie": "A", "peildatum": "YYYY-MM-DD"}
```

`brontekst` is de gegeven bron in de prompt (nog zonder RAG). Velden uit docs/02 §6.1 (`gouden_bronnen`, `kernfeiten`, `verwachte_status`) mag je meegeven; de benchmark scoort ze nog niet. Verzin geen vragen of artikelteksten. Zonder dit bestand schrijft het script een rapport met `niet gemeten` en roept het geen model aan.

## Draaien

Vanuit de repo-root, met Ollama op de host (`LLM_BASE_URL`, default `http://127.0.0.1:11434`). Controleer de tags eerst met `ollama list`. De defaults komen uit het issue en zijn hier niet tegen een draaiende Ollama gecontroleerd: `qwen3.5:9b`, `qwen3.5:4b`, `gemma4:12b`, `ministral-3:8b`. Ontbreekt een tag, dan slaat het script dat model over.

```bash
uv sync --all-packages --all-groups
ollama list
uv run python eval/bench_models.py
```

Andere tags: `uv run python eval/bench_models.py qwen3.5:9b`. Het rapport komt in `eval/reports/bench-<datum>.md`. Een sjabloon zonder cijfers staat in `eval/reports/bench-template.md`.

Context staat vast op `num_ctx=16384` en `think` staat uit. Per model gaat er eerst een warm-up-call uit die niet meetelt. De laatste vraag stuurt `keep_alive: 0` zodat Ollama het model ontladt. Schema-validiteit telt alleen antwoorden; HTTP-fouten staan apart. Valt alles weg, dan is de status `mislukt`.

### RTX 3070 (8 GB)

Ollama native, niet de Docker-GPU-service. `nvidia-smi` levert de VRAM-kolom (MiB in gebruik op de hele GPU, steekproef voor en na elke vraag). Docs/02 zet het 9B-model krap in 8 GB bij deze context; past een model niet, dan faalt of skipt Ollama en blijft de rij zonder verzonnen snelheid.

### MacBook Air M3 (16 GB)

Ollama via Metal. `nvidia-smi` is er niet, dus piek-VRAM blijft `niet beschikbaar`. Het script praat alleen met de Ollama HTTP-API, niet met MLX.

## Checks

```bash
cd eval && uv run ruff check && uv run ruff format --check && uv run mypy src && uv run pytest
```

CI draait die checks zonder Ollama en zonder modelgewichten.
