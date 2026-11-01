<script lang="ts">
  import { resolve } from "$app/paths";
  import { page } from "$app/state";

  import { DossierStore } from "./dossier.svelte";

  let {
    idPrefix = "",
    onNavigate = () => undefined,
  }: { idPrefix?: string; onNavigate?: () => void } = $props();

  const dossier = new DossierStore();
  const headingId = $derived(`${idPrefix}dossiers-kop`);
</script>

<section aria-labelledby={headingId}>
  <h2 id={headingId} class="text-sm font-medium">Dossiers</h2>
  <p class="sr-only">{dossier.items.length} dossiers</p>
  <nav aria-label="Dossiers" class="mt-2">
    <a
      href={resolve("/dossier/dakkapel")}
      class="block min-h-10 rounded-md px-2 py-2 text-sm hover:bg-accent focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
      aria-current={page.url.pathname === "/dossier/dakkapel"
        ? "page"
        : undefined}
      onclick={onNavigate}
    >
      Dakkapeltoets
    </a>
  </nav>
</section>
