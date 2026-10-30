<script lang="ts">
  import { SettingsStore } from "./settings.svelte";

  let { idPrefix = "" }: { idPrefix?: string } = $props();

  const settings = new SettingsStore();
  const headingId = $derived(`${idPrefix}instellingen-kop`);
</script>

<section aria-labelledby={headingId} class="mt-auto">
  <h2 id={headingId} class="text-sm font-medium">Instellingen</h2>
  <p class="sr-only">
    {settings.ready
      ? "Instellingen beschikbaar"
      : "Instellingen niet beschikbaar"}
  </p>
</section>
