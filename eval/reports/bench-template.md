# Modelbenchmark (sjabloon)

Dit is geen meetrapport. `eval/bench_models.py` vult een `bench-<datum>.md` met cijfers uit die run. Tot die run blijft elke cel `niet gemeten` of `niet beschikbaar`.

## Methode

- Publieke `wetvia.llm`-provider via `wetvia.bootstrap.get_ollama_provider`, streaming, `num_ctx=16384`, `think` uit.
- Dummy-`AnswerV1` uit docs/02 §4 staat in de prompt en wordt lokaal gevalideerd. Tijd tot eerste token na een warm-up die niet meetelt; tokens/s uit `StreamMetrics` van `eval_count` en `eval_duration` (nanoseconden).
- VRAM via `nvidia-smi` (hele GPU) als die binary er is. Elke generatie wordt ongeveer elke 0,1 seconde bemonsterd, ook de warm-up; elke modelrun houdt eigen steekproeven bij. De laatste vraag per model stuurt `keep_alive: 0` na de generatie.
- Geen vragen in `eval/data/bench.jsonl` betekent geen meting.

## Resultaten

| Model          | Status       | Items | Tijd tot eerste token (s) | tokens/s     | Schema-validiteit (%) | Piek-VRAM (MiB)  | Opmerking                |
| -------------- | ------------ | ----- | ------------------------- | ------------ | --------------------- | ---------------- | ------------------------ |
| qwen3.5:9b     | niet gemeten | 0     | niet gemeten              | niet gemeten | niet gemeten          | niet beschikbaar | script nog niet gedraaid |
| qwen3.5:4b     | niet gemeten | 0     | niet gemeten              | niet gemeten | niet gemeten          | niet beschikbaar | script nog niet gedraaid |
| gemma4:12b     | niet gemeten | 0     | niet gemeten              | niet gemeten | niet gemeten          | niet beschikbaar | script nog niet gedraaid |
| ministral-3:8b | niet gemeten | 0     | niet gemeten              | niet gemeten | niet gemeten          | niet beschikbaar | script nog niet gedraaid |
