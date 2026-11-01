# apps/web

SvelteKit 2-frontend van Wetvia (Svelte 5, TypeScript, Tailwind 4, shadcn-svelte).

Features staan in `src/lib/features/<feature>/` (component, store, test). shadcn-componenten staan in `src/lib/ui/`. Het logo is `static/logo.svg`.

De chat gebruikt de gegenereerde `@wetvia/api-client` en diens SSE-stream helper. Gesprekken worden per browser en origin in IndexedDB opgeslagen. De geschiedenis bevat vragen, antwoorden en de bronkaarten die bij antwoorden horen; Wetvia synchroniseert deze gegevens niet met een server. Bij het starten kan de browser `/api/health` aanroepen om te zien welke modi zijn geconfigureerd. Herstellen doet geen `/api/chat`-generatieaanroep en speelt geen vraag automatisch opnieuw af. Een expliciete vervolgvraag in een lokaal gesprek stuurt de begrensde geschiedenis van dat gesprek mee; in cloudmodus gaat alleen de huidige vraag mee. Nieuwe gesprekken starten lokaal. Cloudkeuze en toestemming worden per gesprek met toestemmingsversie en tijdstip opgeslagen; API-sleutels komen nooit in de browser. Oudere gesprekken met een onbepaalde backendmodus worden lokaal gemigreerd. Een oud cloudgesprek blijft cloud, maar vraagt opnieuw toestemming vóór het volgende cloudverzoek. Dossiers vallen buiten deze opslag.

IndexedDB is niet versleuteld door Wetvia en kan door browserinstellingen, privévensters, quota of het wissen van sitegegevens verdwijnen. Andere gebruikers met toegang tot hetzelfde browserprofiel kunnen de gesprekken bekijken. Verwijder gesprekken via Instellingen of wis de sitegegevens van de browser.

Stel voor een deployment `PUBLIC_API_BASE_URL` in op dezelfde origin, of gebruik een reverse proxy die `/api` onder de web-origin aanbiedt. Een lege waarde gebruikt dezelfde origin; de Vite dev-server stuurt `/api` door naar `http://127.0.0.1:8000`.

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
