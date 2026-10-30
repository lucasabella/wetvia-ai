<script lang="ts">
  import { DossierStore } from "./dossier.svelte";

  let { idPrefix = "" }: { idPrefix?: string } = $props();

  const dossier = new DossierStore();
  const headingId = $derived(`${idPrefix}dossiers-kop`);
</script>

<section aria-labelledby={headingId}>
  <h2 id={headingId} class="text-sm font-medium">Dossiers</h2>
  <p class="sr-only">{dossier.items.length} dossiers</p>
</section>
