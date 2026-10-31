# BWB XML parser fixtures

These full official XML `Toestand` files were retrieved on 2026-10-31 from the
exact `Toestand.toestand_url` values returned by the public
`BwbSRUClient.search_toestanden` API. The tests select each version with
`select_toestand(..., date(2026, 10, 31))` using the saved official SRU pages
in `tests/fixtures/`. The bytes are kept as retrieved; the parser tests make no
live requests and do not modify or author law text.

The Basis Wetten Bestand is published as CC0. BWB law text is also not subject
to copyright under article 11 of the Dutch Copyright Act; see the repository's
source notes in `docs/01-kritische-beoordeling.md`.

| File | BWB ID and title | Selected validity | Modified | Official source URL | SHA-256 |
|---|---|---|---|---|---|
| `bbl-2026-09-24.xml` | `BWBR0041297`, Besluit bouwwerken leefomgeving | 2026-09-24 through 9999-12-31 | 2026-09-30 | <https://repository.officiele-overheidspublicaties.nl/bwb/BWBR0041297/2026-09-24_0/xml/BWBR0041297_2026-09-24_0.xml> | `52ef1dbbf8d109ba9c1e452193735ef32790d604dec0c8e03ede02245c6b7690` |
| `awb-2026-08-15.xml` | `BWBR0005537`, Algemene wet bestuursrecht | 2026-08-15 through 9999-12-31 | 2026-09-29 | <https://repository.officiele-overheidspublicaties.nl/bwb/BWBR0005537/2026-08-15_0/xml/BWBR0005537_2026-08-15_0.xml> | `5916d0e65a5f9bdfed69fd484f038c3cb4614289100cd92d70b4828030d7a871` |

The saved SRU metadata was requested from
`https://zoekservice.overheid.nl/sru/Search` with `x-connection=BWB` and the
query `dcterms.identifier==BWBR0041297` or `dcterms.identifier==BWBR0005537`.
The exact selected `Toestand` metadata was:

- Bbl: `geldig_vanaf=2026-09-24`, `geldig_tot=9999-12-31`,
  `modified=2026-09-30`.
- Awb: `geldig_vanaf=2026-08-15`, `geldig_tot=9999-12-31`,
  `modified=2026-09-29`.

Golden assertions were checked against these source files:

- Bbl article 2.29(b) contains the official measurements `1,75 m` and `0,5 m`.
- Awb article 6:5 has three official `<lid>` elements.
- Bbl article 2.10 is marked `vervallen` in the XML.
- Bbl article 3.8 includes official table 3.8, rendered to Markdown by tests.
