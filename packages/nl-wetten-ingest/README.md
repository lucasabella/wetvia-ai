# nl-wetten-ingest

Herbruikbaar pakket voor Nederlandse wet- en regelgevingsbronnen. Apache-2.0, ook als de rest van Wetvia AGPL-3.0-only is.

Copyright (C) 2026 Luca Sabella.

Licensed under the Apache License, Version 2.0. See [LICENSE](LICENSE).

De clients staan nog niet in deze tree. Gepland, zonder implementatie in het skelet:

- `bwb.py`
- `cvdr.py`
- `tk.py`
- `dso.py`
- `parse_bwb_xml.py`
- `cli.py`

```bash
uv run ruff check
uv run ruff format --check
uv run mypy src
uv run pytest
```
