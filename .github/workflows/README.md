# Workflows

De map uit `docs/04` is gereserveerd voor `ci.yml`, `eval.yml` en `drift-check.yml`.
Een leeg workflow-bestand zou Actions laten falen, daarom staat hier alleen deze uitleg.

## Issue #7 (CI)

Er is nog geen `ci.yml`. Als die job er komt, hoort `uv run lint-imports` in de api-job, naast ruff, mypy en pytest (draaien vanuit `apps/api`, waar het lagencontract staat). Dezelfde job krijgt later de OpenAPI-diff-check uit docs/06. Geen aparte workflow voor die stap.
