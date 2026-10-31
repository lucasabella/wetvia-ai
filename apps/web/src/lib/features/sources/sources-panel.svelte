<script lang="ts">
  import { SourcesStore, formatValidity, sourceBadge } from "./sources.svelte";

  let {
    sources,
    labelledBy,
    idPrefix = "",
  }: {
    sources: SourcesStore;
    labelledBy: string;
    idPrefix?: string;
  } = $props();

  $effect(() => {
    void sources.selectionRevision;
    const chunkId = sources.selectedChunkId;
    if (!chunkId) {
      return;
    }

    const item = document.getElementById(sourceElementId(idPrefix, chunkId));
    if (!item) {
      return;
    }

    const reducedMotion = window.matchMedia(
      "(prefers-reduced-motion: reduce)",
    ).matches;
    item.scrollIntoView({
      behavior: reducedMotion ? "auto" : "smooth",
      block: "nearest",
    });
    item.focus({ preventScroll: true });
  });

  function sourceElementId(prefix: string, chunkId: string): string {
    return `${prefix}bron-${chunkId}`;
  }
</script>

<div
  class="min-h-0 flex-1 space-y-3 overflow-y-auto"
  role="region"
  aria-labelledby={labelledBy}
>
  <p class="sr-only" aria-live="polite">
    {sources.items.length}
    {sources.items.length === 1 ? "bron" : "bronnen"}
  </p>

  {#if sources.items.length === 0}
    <p class="text-sm text-muted-foreground">
      Er zijn nog geen bronnen bij dit antwoord.
    </p>
  {:else}
    {#each sources.items as source (source.chunk_id)}
      {@const badge = sourceBadge(source.metadata)}
      {@const selected = sources.selectedChunkId === source.chunk_id}
      <article
        id={sourceElementId(idPrefix, source.chunk_id)}
        tabindex="-1"
        aria-current={selected ? "true" : undefined}
        aria-labelledby={`${idPrefix}bron-kop-${source.chunk_id}`}
        class={`space-y-2 rounded-lg border p-3 outline-none focus-visible:ring-2 focus-visible:ring-ring ${
          selected
            ? "border-primary bg-accent ring-2 ring-primary/50"
            : "border-border bg-card"
        }`}
      >
        <div class="flex flex-wrap items-start justify-between gap-2">
          <div class="min-w-0">
            <h3
              id={`${idPrefix}bron-kop-${source.chunk_id}`}
              class="text-sm font-semibold break-words"
            >
              {source.metadata.regeling_titel}
            </h3>
            <p class="mt-0.5 text-xs text-muted-foreground">
              Artikel {source.metadata.artikel}
              {#if source.metadata.lid}
                · lid {source.metadata.lid}
              {/if}
              {#if source.metadata.onderdeel}
                · onderdeel {source.metadata.onderdeel}
              {/if}
            </p>
          </div>
          <span
            class={`shrink-0 rounded-full px-2 py-1 text-xs font-semibold ${badge.className}`}
          >
            {badge.label}
          </span>
        </div>

        {#if source.metadata.kop_pad}
          <p class="text-xs text-muted-foreground">{source.metadata.kop_pad}</p>
        {/if}
        <blockquote
          class="max-h-48 overflow-y-auto border-l-2 border-primary/40 pl-3 font-serif text-sm leading-relaxed whitespace-pre-wrap"
        >
          {source.tekst}
        </blockquote>
        <p class="text-xs text-muted-foreground">
          {formatValidity(source.metadata)}
        </p>
        <!-- eslint-disable svelte/no-navigation-without-resolve -->
        <a
          href={source.metadata.bron_url}
          target="_blank"
          rel="noopener noreferrer"
          class="inline-flex min-h-8 items-center font-medium text-primary underline underline-offset-2"
        >
          Bekijk op wetten.overheid.nl <span class="ml-1" aria-hidden="true"
            >↗</span
          >
          <span class="sr-only"> (opent in een nieuw tabblad)</span>
        </a>
        <!-- eslint-enable svelte/no-navigation-without-resolve -->
      </article>
    {/each}
  {/if}
</div>
