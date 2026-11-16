# nl-overheid-benchmark

Toetsitems en de automatische score. Apache-2.0. Het pakket importeert `wetvia` niet en roept geen model aan.

De vragen in `src/nl_overheid_benchmark/data/` zijn CC BY 4.0 en nog een concept. Zie [data/README.md](src/nl_overheid_benchmark/data/README.md).

```bash
uv run ruff check
uv run ruff format --check
uv run mypy src
uv run pytest
```
