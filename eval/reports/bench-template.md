# Modelbenchmark (sjabloon)

Dit is geen meetrapport. `eval/bench_models.py` vult een `bench-<datum>.md` met cijfers uit die run. Tot die run blijft elke cel `niet gemeten` of `niet beschikbaar`.

## Methode

- Ollama `POST /api/chat`, streaming, `num_ctx=16384`, `think` uit.
- Dummy-`AnswerV1` uit docs/02 §4. De client is lokaal in `wetvia_eval` tot issue #5 de `wetvia.llm`-port levert.
- Tijd tot eerste token, tokens/s uit `eval_count` en `eval_duration` (nanoseconden), schema-validiteit, piek-VRAM via `nvidia-smi` als die binary er is.
- Geen vragen in `eval/data/bench.jsonl` betekent geen meting.

## Resultaten

| Model          | Status       | Items | Tijd tot eerste token (s) | tokens/s     | Schema-validiteit (%) | Piek-VRAM (MiB)  | Opmerking                |
| -------------- | ------------ | ----- | ------------------------- | ------------ | --------------------- | ---------------- | ------------------------ |
| qwen3.5:9b     | niet gemeten | 0     | niet gemeten              | niet gemeten | niet gemeten          | niet beschikbaar | script nog niet gedraaid |
| qwen3.5:4b     | niet gemeten | 0     | niet gemeten              | niet gemeten | niet gemeten          | niet beschikbaar | script nog niet gedraaid |
| gemma4:12b     | niet gemeten | 0     | niet gemeten              | niet gemeten | niet gemeten          | niet beschikbaar | script nog niet gedraaid |
| ministral-3:8b | niet gemeten | 0     | niet gemeten              | niet gemeten | niet gemeten          | niet beschikbaar | script nog niet gedraaid |
