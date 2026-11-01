# Dakkapel wizard

`dakkapel-wizard.svelte` is the five-step `/dossier/dakkapel` flow. It uses the
generated `@wetvia/api-client` request/response types and sends measurement
strings through `POST /api/rules/dakkapel`. `dakkapel-wizard-state.svelte.ts`
only normalizes user input and manages per-page state, debounce, cancellation,
and stale-response protection; legal thresholds remain in `wetvia.rules`.

Do not persist wizard input in IndexedDB. Address text is kept in page memory
and is not sent to the rules endpoint or the local project-description prompt.
It is included in the explicitly requested dossier-generation API call so it
can appear in the file. The API uses only the configured local provider for the
description and does not send the address to a chat-cloud provider. The last
step offers DOCX/PDF/Markdown concept downloads; applicant details remain
placeholders, and the DSO checklist stays empty and marked unverified until
issue #24 supplies official data.
