<script lang="ts">
  import { STARTER_QUESTIONS, type ChatStore } from "./chat.svelte";
  import AnswerCard from "./answer-card.svelte";

  let {
    chat,
    onSourceSelect,
  }: {
    chat: ChatStore;
    onSourceSelect: (turnId: string, chunkId: string) => void;
  } = $props();

  let textarea = $state<HTMLTextAreaElement>();
  let transcript = $state<HTMLDivElement>();

  function submit(event: SubmitEvent): void {
    event.preventDefault();
    void chat.submit();
  }

  function handleKeydown(event: KeyboardEvent): void {
    if (
      event.key === "Enter" &&
      !event.shiftKey &&
      !event.isComposing &&
      !chat.sending
    ) {
      event.preventDefault();
      void chat.submit();
    }
  }

  function useStarter(question: string): void {
    chat.draft = question;
    textarea?.focus();
  }

  $effect(() => {
    void chat.turns.length;
    const latest = chat.turns.at(-1);
    void latest?.answer;
    void latest?.status;
    if (transcript) {
      const reducedMotion = window.matchMedia(
        "(prefers-reduced-motion: reduce)",
      ).matches;
      transcript.scrollTo({
        top: transcript.scrollHeight,
        behavior: reducedMotion ? "auto" : "smooth",
      });
    }
  });
</script>

<section class="flex h-full min-h-0 flex-col" aria-labelledby="gesprek-kop">
  <header
    class="mb-4 flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1"
  >
    <h1 id="gesprek-kop" class="text-lg font-semibold">Gesprek</h1>
    <p class="text-sm text-muted-foreground">
      Peildatum: {chat.peildatum.split("-").reverse().join("-")}
    </p>
  </header>

  {#if chat.turns.length === 0}
    <div
      class="flex min-h-0 flex-1 flex-col items-center justify-center gap-6 px-2 py-8 text-center"
    >
      <div class="max-w-xl space-y-3">
        <p class="text-2xl font-semibold tracking-tight">
          Vraag het aan Wetvia
        </p>
        <p class="text-muted-foreground">
          Vraag naar regels voor verbouwen. Wetvia zoekt in officiële bronnen en
          laat zien waar het staat.
        </p>
      </div>
      <div class="grid w-full max-w-2xl gap-3 sm:grid-cols-3">
        {#each STARTER_QUESTIONS as question (question)}
          <button
            type="button"
            class="min-h-20 rounded-lg border border-border bg-card px-4 py-3 text-left text-sm font-medium hover:bg-accent focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
            onclick={() => useStarter(question)}
          >
            {question}
          </button>
        {/each}
      </div>
    </div>
  {:else}
    <div
      bind:this={transcript}
      class="min-h-0 flex-1 space-y-6 overflow-y-auto px-1 py-2"
      role="log"
      aria-label="Gesprek"
      aria-live="polite"
      aria-relevant="additions text"
    >
      {#each chat.turns as turn (turn.id)}
        <article
          class="mx-auto w-full max-w-3xl space-y-4"
          aria-labelledby={`vraag-${turn.id}`}
        >
          <div class="flex justify-end">
            <div
              class="max-w-[90%] rounded-2xl rounded-br-sm bg-accent px-4 py-3 sm:max-w-[80%]"
            >
              <h2 id={`vraag-${turn.id}`} class="sr-only">Uw vraag</h2>
              <p class="break-words whitespace-pre-wrap">{turn.question}</p>
            </div>
          </div>

          {#if turn.status === "pending"}
            <p class="px-1 text-sm text-muted-foreground" role="status">
              Bronnen worden gezocht…
            </p>
          {:else if turn.errorMessage}
            <p
              class="rounded-lg border border-destructive/50 bg-background px-4 py-3 text-sm"
              role="alert"
            >
              {turn.errorMessage}
            </p>
          {:else if turn.answer}
            <AnswerCard
              {turn}
              onSourceSelect={(chunkId) => onSourceSelect(turn.id, chunkId)}
            />
          {/if}
        </article>
      {/each}
    </div>
  {/if}

  {#if chat.notice}
    <p
      class="mx-auto mt-2 w-full max-w-3xl text-sm text-destructive"
      role="alert"
    >
      {chat.notice}
    </p>
  {/if}

  <form
    class="mx-auto mt-3 w-full max-w-3xl rounded-xl border border-border bg-card p-3 shadow-sm"
    onsubmit={submit}
    aria-label="Stel een vraag"
    aria-busy={!chat.ready}
  >
    <label class="sr-only" for="vraag-invoer">Stel een vraag</label>
    <textarea
      bind:this={textarea}
      id="vraag-invoer"
      bind:value={chat.draft}
      rows="2"
      maxlength="2000"
      placeholder="Stel een vraag…"
      class="block min-h-16 w-full resize-y bg-transparent px-1 py-2 text-base outline-none placeholder:text-muted-foreground"
      aria-describedby="vraag-hint wetvia-voetnoot"
      onkeydown={handleKeydown}></textarea>
    <div
      class="flex flex-wrap items-center justify-between gap-2 border-t border-border pt-2"
    >
      <p id="vraag-hint" class="text-xs text-muted-foreground">
        Enter verstuurt · Shift+Enter maakt een nieuwe regel
      </p>
      <div class="flex items-center gap-2">
        {#if chat.sending}
          <button
            type="button"
            class="min-h-9 rounded-md px-3 text-sm font-medium text-muted-foreground underline underline-offset-4 hover:text-foreground"
            onclick={() => chat.cancel()}
          >
            Stop
          </button>
        {/if}
        <button
          type="submit"
          class="min-h-10 rounded-md bg-primary px-4 text-sm font-semibold text-primary-foreground hover:bg-primary/90 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring disabled:cursor-not-allowed disabled:opacity-50"
          disabled={!chat.ready || chat.sending || !chat.draft.trim()}
        >
          Verstuur
        </button>
      </div>
    </div>
    <p
      id="wetvia-voetnoot"
      class="mt-2 text-xs leading-relaxed text-muted-foreground"
    >
      Wetvia geeft juridische informatie, geen advies. Controleer altijd de
      bron. U praat met een AI-systeem.
    </p>
  </form>
</section>
