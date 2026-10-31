<script lang="ts">
  import { citedSources, formatAnswerDate, type ChatTurn } from "./chat.svelte";

  let {
    turn,
    onSourceSelect,
  }: {
    turn: ChatTurn;
    onSourceSelect: (chunkId: string) => void;
  } = $props();

  const statusStyle = $derived.by(() => {
    if (turn.answer?.status === "onzeker") {
      return "border-dotted border-amber-700 bg-amber-50 text-amber-950";
    }
    if (turn.answer?.status === "buiten_scope") {
      return "border-border bg-muted text-foreground";
    }
    return "border-border bg-card text-foreground";
  });
</script>

{#if turn.answer}
  <section
    class={`space-y-4 rounded-xl border p-4 ${statusStyle}`}
    aria-label={turn.answer.status === "onzeker"
      ? "Onzeker antwoord"
      : turn.answer.status === "buiten_scope"
        ? "Vraag buiten onderwerp"
        : "Antwoord"}
  >
    {#if turn.answer.status === "onzeker"}
      <p class="font-semibold">Dit weet ik niet zeker.</p>
      <p class="text-sm leading-relaxed">
        Ik kan dit niet met zekerheid zeggen op basis van de bronnen die ik heb.
      </p>
    {:else if turn.answer.status === "buiten_scope"}
      <p class="font-semibold">Buiten onderwerp</p>
    {/if}

    <p class="leading-relaxed">{turn.answer.samenvatting}</p>

    {#if turn.answer.status === "buiten_scope"}
      <p class="text-sm leading-relaxed">
        Voor meer informatie kunt u het Omgevingsloket, uw gemeente of het
        Juridisch Loket raadplegen.
      </p>
    {/if}

    {#if turn.answer.punten.length > 0}
      <ul class="space-y-3">
        {#each turn.answer.punten as point, pointIndex (`${pointIndex}-${point.tekst}`)}
          <li
            class="flex flex-wrap items-start gap-x-2 gap-y-1 leading-relaxed"
          >
            <span aria-hidden="true" class="mt-0.5">•</span>
            <span class="min-w-0 flex-1">{point.tekst}</span>
            {#each citedSources(turn.sources, point.bron_ids) as source (source.chunk_id)}
              <button
                type="button"
                class="inline-flex min-h-7 items-center rounded-full border border-primary/50 bg-background px-2 text-xs font-semibold text-primary underline-offset-2 hover:bg-accent hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
                aria-label={`Toon bron ${source.label}`}
                onclick={() => onSourceSelect(source.chunk_id)}
              >
                {source.label}
              </button>
            {/each}
          </li>
        {/each}
      </ul>
    {/if}

    {#if turn.answer.voorbehouden.length > 0}
      <section aria-labelledby={`voorbehouden-${turn.id}`}>
        <h3 id={`voorbehouden-${turn.id}`} class="mb-1 text-sm font-semibold">
          Voorbehouden
        </h3>
        <ul class="list-disc space-y-1 pl-5 text-sm">
          {#each turn.answer.voorbehouden as caveat, caveatIndex (`${turn.id}-caveat-${caveatIndex}`)}
            <li>{caveat}</li>
          {/each}
        </ul>
      </section>
    {/if}

    {#if turn.answer.vervolgstappen.length > 0}
      <section aria-labelledby={`vervolgstappen-${turn.id}`}>
        <h3 id={`vervolgstappen-${turn.id}`} class="mb-1 text-sm font-semibold">
          Vervolgstappen
        </h3>
        <ul class="list-disc space-y-1 pl-5 text-sm">
          {#each turn.answer.vervolgstappen as step, stepIndex (`${turn.id}-step-${stepIndex}`)}
            <li>
              <!-- eslint-disable svelte/no-navigation-without-resolve -->
              <a
                href={step.url}
                target="_blank"
                rel="noopener noreferrer"
                class="font-medium text-primary underline underline-offset-2"
              >
                {step.tekst} <span aria-hidden="true">↗</span>
                <span class="sr-only"> (opent in een nieuw tabblad)</span>
              </a>
              <!-- eslint-enable svelte/no-navigation-without-resolve -->
            </li>
          {/each}
        </ul>
      </section>
    {/if}

    <p class="border-t border-current/15 pt-2 text-xs text-current/80">
      Peildatum: {formatAnswerDate(turn.answer.peildatum)}
    </p>
  </section>
{/if}
