# wetvia.llm

Doel: de `LLMProvider`-port en de adapters (Ollama, OpenAI-compatibel, fake). De factory `get_provider` staat in `bootstrap.py`. Deze module leest geen `Settings` en geen env.

Publieke API: `LLMProvider` en `ChatMessage`. Adapters in `adapters/` zijn niet publiek.

Gestructureerde calls: Ollama stuurt `format` met het JSON-schema en altijd `think: false`. OpenAI-compatibel probeert `response_format.type = json_schema` en valt terug op `json_object` als de server dat weigert. Beide valideren met Pydantic en proberen hoogstens één keer opnieuw, met de validatiefout in het bericht. Streamen is alleen voor calls zonder schema.

Toegestane imports: `wetvia.embeddings`, `wetvia.db`, `wetvia.core`, de standaardbibliotheek, `httpx`, `openai` en Pydantic. Niet `wetvia.config`, `wetvia.retrieval`, `wetvia.ingest`, `wetvia.citations`, `wetvia.rules` of een hogere laag.

Test: `cd apps/api && uv run pytest && uv run lint-imports`
