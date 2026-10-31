<script lang="ts">
  import { SettingsStore } from "./settings.svelte";

  let {
    idPrefix = "",
    onClearAll,
  }: { idPrefix?: string; onClearAll: () => Promise<void> } = $props();

  const settings = new SettingsStore();
  const headingId = $derived(`${idPrefix}instellingen-kop`);
  let clearDialog = $state<HTMLDialogElement>();

  function openClearDialog(): void {
    clearDialog?.showModal();
  }

  async function confirmClearAll(): Promise<void> {
    await onClearAll();
    clearDialog?.close();
  }
</script>

<section aria-labelledby={headingId} class="mt-auto">
  <h2 id={headingId} class="text-sm font-medium">Instellingen</h2>
  <p class="sr-only">
    {settings.ready
      ? "Instellingen beschikbaar"
      : "Instellingen niet beschikbaar"}
  </p>
  <button
    type="button"
    class="mt-2 min-h-9 text-left text-sm text-muted-foreground underline underline-offset-2 hover:text-destructive focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
    onclick={openClearDialog}
  >
    Wis alle gesprekken
  </button>

  <dialog
    bind:this={clearDialog}
    class="m-auto w-[min(90vw,28rem)] rounded-xl border border-border bg-background p-0 text-foreground shadow-xl backdrop:bg-black/40"
    aria-labelledby={`${headingId}-wis-kop`}
    aria-describedby={`${headingId}-wis-uitleg`}
  >
    <div class="space-y-4 p-5">
      <h3 id={`${headingId}-wis-kop`} class="text-base font-semibold">
        Alle gesprekken wissen?
      </h3>
      <p id={`${headingId}-wis-uitleg`} class="text-sm leading-relaxed">
        Dit verwijdert alle gesprekken uit deze browser. Dit kan niet ongedaan
        worden gemaakt.
      </p>
      <div class="flex justify-end gap-2">
        <button
          type="button"
          class="min-h-10 rounded-md border border-border px-3 text-sm font-medium hover:bg-accent focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
          onclick={() => clearDialog?.close()}
        >
          Annuleren
        </button>
        <button
          type="button"
          class="min-h-10 rounded-md border border-destructive bg-background px-3 text-sm font-semibold text-foreground hover:bg-destructive/10 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
          onclick={() => void confirmClearAll()}
        >
          Wis alles
        </button>
      </div>
    </div>
  </dialog>
</section>
