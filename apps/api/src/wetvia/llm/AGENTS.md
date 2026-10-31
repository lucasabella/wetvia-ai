# wetvia.llm

Doel: de `LLMProvider`-port en de adapters (Ollama, OpenAI-compatibel, fake). De factory `get_provider` staat in `bootstrap.py`. Deze module leest geen `Settings` en geen env.

Publieke API: `LLMProvider` en `ChatMessage`. Adapters in `adapters/` zijn niet publiek.

Gestructureerde calls: Ollama stuurt `format` met het JSON-schema en altijd `think: false`. Een `error` in de body of stream is een fout, geen lege tekst. OpenAI-compatibel stuurt `json_schema` met `strict: true` en een schema waarin elk object `additionalProperties: false` heeft en alle velden required zijn (ook in `$defs`). Alleen HTTP 400 of 422 valt terug op `json_object`, met een systeeminstructie die JSON en het schema noemt. Die keuze geldt alleen voor de validatie-retry van die ene `chat()`-call; de volgende call begint weer met `json_schema`. 401, 403, 404 en 429 vallen niet terug. Beide valideren met Pydantic en proberen hoogstens één keer opnieuw. Streamen is alleen voor calls zonder schema. `openai_compat` zonder `LLM_API_KEY` faalt bij `get_provider`.

Toegestane imports: `wetvia.embeddings`, `wetvia.db`, `wetvia.core`, de standaardbibliotheek, `httpx`, `openai` en Pydantic. Niet `wetvia.config`, `wetvia.retrieval`, `wetvia.ingest`, `wetvia.citations`, `wetvia.rules` of een hogere laag.

Test: `cd apps/api && uv run pytest && uv run lint-imports`
