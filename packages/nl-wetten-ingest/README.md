# nl-wetten-ingest

Herbruikbaar pakket voor Nederlandse wet- en regelgeving-bronnen. Het pakket is Apache-2.0 en importeert `wetvia` niet.

## BWB SRU-client

`BwbSRUClient` haalt versiegegevens voor BWB-regelingen op bij het officiële SRU-endpoint. Het resultaat bevat alleen bronmetadata; het ophalen en parsen van de wetstekst valt buiten deze client.

```python
from datetime import date

from nl_wetten_ingest import BwbSRUClient, classify, select_toestand

with BwbSRUClient() as client:
    toestanden = client.search_toestanden("BWBR0041297")
    gewijzigd = client.changed_since(date(2026, 10, 1))

geldende = select_toestand(toestanden, date(2026, 10, 31))
print(geldende.titel, classify(geldende, date(2026, 10, 31)))
```

`Toestand` bevat `bwb_id`, `titel`, `geldig_vanaf`, `geldig_tot`, `toestand_url` en `modified`. Datums zijn `datetime.date`-waarden; `geldig_tot` is `None` als de SRU-respons geen einddatum bevat. Expliciete bronwaarden, waaronder `9999-12-31`, blijven ongewijzigd. De geldigheidsgrenzen zijn inclusief. `select_toestand` geeft alleen een resultaat als precies één toestand op de peildatum geldt; bij nul of meerdere resultaten volgt een `ValueError`.

De client gebruikt paginering via SRU `startRecord` en `maximumRecords`, een HTTP-timeout, maximaal drie pogingen met exponentiële backoff voor tijdelijke fouten, en de User-Agent `wetvia-ai/<pakketversie> (+https://github.com/lucasabella/wetvia-ai)`. `changed_since(datum)` zoekt met `dcterms.modified>=YYYY-MM-DD`. SRU-diagnoses worden als `SRUDiagnosticError` met code, details en bericht doorgegeven; ongeldige of onvolledige XML geeft `SRUProtocolError`.

Opgehaalde data wordt niet gecachet of opgeslagen. Dat hoort bij `wetvia.ingest`, niet bij dit bronpakket. De officiële BWB-metadata wordt als CC0 gepubliceerd. De fixtures en hun herkomst staan in [`tests/fixtures/README.md`](tests/fixtures/README.md).

## Checks

```bash
uv run ruff check
uv run ruff format --check
uv run mypy src
uv run pytest
```

Copyright (C) 2026 Luca Sabella. Licensed under the Apache License, Version 2.0. See [LICENSE](LICENSE).
