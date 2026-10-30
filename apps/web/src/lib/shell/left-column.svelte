<script lang="ts">
  import { resolve } from "$app/paths";
  import DossierPanel from "$lib/features/dossier/dossier-panel.svelte";
  import SettingsPanel from "$lib/features/settings/settings-panel.svelte";

  let {
    showHistoryHeading = true,
    idPrefix = "",
  }: { showHistoryHeading?: boolean; idPrefix?: string } = $props();

  const historyHeadingId = $derived(`${idPrefix}geschiedenis-kop`);
</script>

<div class="flex h-full flex-col gap-6">
  <a
    href={resolve("/")}
    class="flex items-center gap-2 rounded-md font-semibold"
  >
    <img src="/logo.svg" width="36" height="36" alt="" />
    Wetvia
  </a>
  <section
    class="flex flex-1 flex-col gap-6"
    aria-labelledby={historyHeadingId}
  >
    <h2
      id={historyHeadingId}
      class={showHistoryHeading ? "text-sm font-medium" : "sr-only"}
    >
      Geschiedenis
    </h2>
    <DossierPanel {idPrefix} />
    <SettingsPanel {idPrefix} />
  </section>
</div>
