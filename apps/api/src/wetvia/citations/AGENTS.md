# wetvia.citations

Doel: citatie-verifier en abstentie. Pure functies zonder I/O.

Publieke API: `CitationClaim`, `CitationSource`, `VerificationResult`,
`VerifiedClaim`, `extract_measurements`, `parse_iso_date`,
`extract_quantities`, `retrieval_score_below_tau` en `verify_citations`;
`__init__.py` is de
publieke exportgrens.

De hoeveelheidscontrole vergelijkt expliciete getal/eenheid-paren en een
allowlist van kale aantallen/tijdsduurwoorden. Dit is geen semantische
gevolgtrekking of juridische juistheidscontrole. Houd de module stdlib-only en
geef alle beslissingen terug als zuivere data/diagnostiek.

Toegestane imports: de standaardbibliotheek. Het lagencontract noemt ook `wetvia.embeddings`, `wetvia.db` en `wetvia.core`, maar deze module blijft puur en doet geen I/O. Verboden: `sqlalchemy`, `httpx`, `openai`, `fastapi`, `sentence_transformers`. Niet de andere modules in dezelfde laag (`retrieval`, `ingest`, `rules`, `llm`) en niets daarboven.

Test: `cd apps/api && uv run pytest && uv run lint-imports`
