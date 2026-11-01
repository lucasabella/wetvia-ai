# Dakkapel wizard

`dakkapel-wizard.svelte` is the five-step `/dossier/dakkapel` flow. It uses the
generated `@wetvia/api-client` request/response types and sends measurement
strings through `POST /api/rules/dakkapel`. `dakkapel-wizard-state.svelte.ts`
only normalizes user input and manages per-page state, debounce, cancellation,
and stale-response protection; legal thresholds remain in `wetvia.rules`.

Do not persist wizard input in IndexedDB. Address text is kept in this page and
is not part of the API request. The last step is a preview only; document
generation and downloads are outside this feature.
