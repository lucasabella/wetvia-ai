# apps/web

SvelteKit 2-frontend van Wetvia (Svelte 5, TypeScript, Tailwind 4, shadcn-svelte).

Features staan in `src/lib/features/<feature>/` (component, store, test). shadcn-componenten staan in `src/lib/ui/`. Het logo is `static/logo.svg`.

De chat gebruikt de gegenereerde `@wetvia/api-client` en diens SSE-stream helper. De chat en bronselectie leven alleen in de huidige shell; de webapp schrijft gesprekken niet naar browseropslag. Stel voor een deployment `PUBLIC_API_BASE_URL` in op dezelfde origin, of gebruik een reverse proxy die `/api` onder de web-origin aanbiedt. Een lege waarde gebruikt dezelfde origin; de Vite dev-server stuurt `/api` door naar `http://127.0.0.1:8000`.

De bronbadges volgen de API-status. De huidige API geeft `geldend`, `toekomstig` en `vervallen` terug. De UI kent ook een badge voor `Wetsvoorstel`, maar de huidige API kan die status niet leveren; er wordt geen voorstelstatus afgeleid uit andere bronvelden.

```bash
pnpm dev
pnpm lint
pnpm check
pnpm test
pnpm --filter @wetvia/web exec playwright install chromium
pnpm --filter @wetvia/web test:browser
```

De browser-suite draait Chromium op desktop- en mobiel formaat, gebruikt alleen synthetische interfacegegevens en voert axe uit op de chat-, bron- en statusweergaven in licht en donker.
