# nl-wetten-ingest

Herbruikbaar pakket voor Nederlandse wet- en regelgeving-bronnen. Het pakket is Apache-2.0 en importeert `wetvia` niet.

## BWB SRU-client

`BwbSRUClient` haalt versiegegevens voor BWB-regelingen op bij het officiële SRU-endpoint. `parse_bwb_xml` verwerkt XML-bytes van de bijbehorende `Toestand` naar artikel- en lidchunks met geldigheidsdata, status en bronverwijzingen. De parser haalt zelf geen bestanden op en slaat niets op.

```python
from datetime import date

from nl_wetten_ingest import BwbSRUClient, classify, select_toestand

with BwbSRUClient() as client:
    toestanden = client.search_toestanden("BWBR0041297")
    gewijzigd = client.changed_since(date(2026, 10, 1))

geldende = select_toestand(toestanden, date(2026, 10, 31))
print(geldende.titel, classify(geldende, date(2026, 10, 31)))
```

Parseer de XML die bij de gekozen `Toestand` hoort en geef die metadata mee voor de herkomst van iedere chunk:

```python
from pathlib import Path

from nl_wetten_ingest import parse_bwb_xml

chunks = parse_bwb_xml(Path("BWBR0041297_2026-09-24_0.xml").read_bytes(), geldende)
for chunk in chunks:
    print(chunk.artikel, chunk.lid, chunk.onderdeel, chunk.tekst, chunk.bron_url)
```

De parser gebruikt `lxml.iterparse` met DTD- en externe-entiteitsresolutie uitgeschakeld. Lange artikelen worden op lid- of lijstonderdeelniveau gesplitst; een ondeelbare alinea of lijstitem blijft intact, ook als die groter is dan `max_chars` (standaard 4000). Tabellen worden als Markdown weergegeven; CALS-rowspan en -colspan blijven behouden door celinhoud te herhalen in alle bestreken Markdown-cellen. `Chunk` en `BWBXMLParseError` zijn ook publiek geëxporteerd.

`Toestand` bevat `bwb_id`, `titel`, `geldig_vanaf`, `geldig_tot`, `toestand_url` en `modified`. Datums zijn `datetime.date`-waarden; `geldig_tot` is `None` als de SRU-respons geen einddatum bevat. Expliciete bronwaarden, waaronder `9999-12-31`, blijven ongewijzigd. De geldigheidsgrenzen zijn inclusief. `select_toestand` geeft alleen een resultaat als precies één toestand op de peildatum geldt; bij nul of meerdere resultaten volgt een `ValueError`.

De client gebruikt paginering via SRU `startRecord` en `maximumRecords`, een HTTP-timeout, maximaal drie pogingen met exponentiële backoff voor tijdelijke fouten, en de User-Agent `wetvia-ai/<pakketversie> (+https://github.com/lucasabella/wetvia-ai)`. `changed_since(datum)` zoekt met `dcterms.modified>=YYYY-MM-DD`. SRU-diagnoses worden als `SRUDiagnosticError` met code, details en bericht doorgegeven; ongeldige of onvolledige XML geeft `SRUProtocolError`.

Opgehaalde data wordt niet gecachet of opgeslagen. Dat hoort bij `wetvia.ingest`, niet bij dit bronpakket. De officiële BWB-data is CC0. De SRU-metadatafixtures staan beschreven in [`tests/fixtures/README.md`](tests/fixtures/README.md); de volledige XML-toestanden en hun bronmetadata staan in [`tests/fixtures/bwb_xml/README.md`](tests/fixtures/bwb_xml/README.md). Tests gebruiken deze offline fixtures.

## Checks

```bash
uv run ruff check
uv run ruff format --check
uv run mypy src
uv run pytest
```

Copyright (C) 2026 Luca Sabella. Licensed under the Apache License, Version 2.0. See [LICENSE](LICENSE).
