# BWB SRU test fixtures

These response bodies were fetched from the official BWB SRU endpoint on
2026-10-31. The XML contents are preserved; redundant blank lines after each
document were removed. The service publishes BWB metadata under CC0. No law
text or metadata was authored for the fixtures.

Endpoint: `https://zoekservice.overheid.nl/sru/Search`

All requests used `operation=searchRetrieve`, `version=2.0`,
`x-connection=BWB`, `Accept: application/xml`, and the repository User-Agent.
Page files are ordered exactly as returned by the service:

| Fixture | Query | `startRecord` pages | `maximumRecords` | `numberOfRecords` |
|---|---|---:|---:|---:|
| `bbl-page-1.xml` through `bbl-page-3.xml` | `dcterms.identifier==BWBR0041297` | 1, 6, 11 | 5 | 11 |
| `awb-page-1.xml` through `awb-page-3.xml` | `dcterms.identifier==BWBR0005537` | 1, 101, 201 | 100 | 236 |
| `changed-since-9999-12-31.xml` | `dcterms.modified>=9999-12-31` | 1 | 100 | 0 |
| `diagnostic-invalid-query.xml` | `wetvia.invalidField==nonesuch` | 1 | 5 | SRU diagnostic 1/16 |

The saved pages exercise the SRU `nextRecordPosition` values used for
pagination. Tests use `httpx.MockTransport`; CI makes no calls to the live
endpoint.
