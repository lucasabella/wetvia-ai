# wetvia.dossier

Doel: gestructureerde conceptdossiers en hun DOCX/PDF/Markdown-renderers. De service gebruikt uitsluitend de publieke API van `wetvia.rules`; de geïnjecteerde lokale LLM-provider kopieert de deterministisch samengestelde projectomschrijving exact; afwijkingen worden afgewezen.

Publieke API: `DossierV1`, placeholder-, checklist- en projectomschrijvingschema's, `DakkapelDossierService`, `DossierAttachment` en `DossierFormat` uit `__init__.py`.

Toegestane imports: `wetvia.retrieval`, `wetvia.ingest`, `wetvia.citations`, `wetvia.rules`, `wetvia.llm`, `wetvia.embeddings`, `wetvia.db`, `wetvia.core`, `docxtpl`, `jinja2`, `pypdf`, `weasyprint`, `python-docx` (template authoring/tests) en de standaardbibliotheek. Niet `wetvia.answer` of `wetvia.documents` (zelfde laag) en niets daarboven.

Templates live in the packaged `templates/` resource package. PDF rendering must disable resource fetching; templates must autoescape all interpolated content. Applicant fields are fixed placeholders, and a checklist is empty with `not_retrieved` status until the separate DSO issue supplies verified source data.

Test: `cd apps/api && uv run pytest tests/test_dossier.py tests/test_dossier_renderers.py && uv run lint-imports`
