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
  let consentDialog = $state<HTMLDialogElement>();
  let cloudConsentOpen = $state(false);
  let submitAfterConsent = $state(false);
  let consentConversationId = $state<string | null>(null);
  let consentConversationGeneration = $state<number | null>(null);

  $effect(() => {
    const currentConversationId = chat.activeConversationId;
    const currentGeneration = chat.conversationGeneration;
    if (
      cloudConsentOpen &&
      (currentConversationId !== consentConversationId ||
        currentGeneration !== consentConversationGeneration)
    ) {
      cancelCloudChoice();
    }
    if (cloudConsentOpen && consentDialog && !consentDialog.open) {
      consentDialog.showModal();
    } else if (!cloudConsentOpen && consentDialog?.open) {
      consentDialog.close();
    }
  });

  function submit(event: SubmitEvent): void {
    event.preventDefault();
    void submitQuestion();
  }

  function handleKeydown(event: KeyboardEvent): void {
    if (
      event.key === "Enter" &&
      !event.shiftKey &&
      !event.isComposing &&
      !chat.sending
    ) {
      event.preventDefault();
      void submitQuestion();
    }
  }

  async function submitQuestion(): Promise<void> {
    if (chat.activeMode === "cloud" && chat.cloudAvailable !== true) {
      await chat.submit();
      return;
    }
    if (chat.activeMode === "cloud" && chat.requiresCloudConsent) {
      if (chat.requestCloudConsent()) {
        openCloudConsent(true);
      }
      return;
    }
    await chat.submit();
  }

  async function chooseMode(mode: "local" | "cloud"): Promise<void> {
    const result = await chat.selectMode(mode);
    if (result === "consent-required") {
      openCloudConsent(false);
    }
  }

  async function confirmCloudChoice(): Promise<void> {
    if (!isConsentConversationCurrent()) {
      cancelCloudChoice();
      return;
    }
    const shouldSubmit = submitAfterConsent;
    const confirmed = await chat.confirmCloudConsent();
    if (!confirmed) {
      return;
    }
    if (!isConsentConversationCurrent()) {
      cancelCloudChoice();
      return;
    }
    cloudConsentOpen = false;
    chat.cancelCloudConsent();
    clearConsentTarget();
    if (shouldSubmit) {
      await chat.submit();
    }
  }

  function cancelCloudChoice(event?: Event): void {
    event?.preventDefault();
    cloudConsentOpen = false;
    submitAfterConsent = false;
    chat.cancelCloudConsent();
    clearConsentTarget();
  }

  function openCloudConsent(shouldSubmit: boolean): void {
    submitAfterConsent = shouldSubmit;
    consentConversationId = chat.activeConversationId;
    consentConversationGeneration = chat.conversationGeneration;
    cloudConsentOpen = true;
  }

  function isConsentConversationCurrent(): boolean {
    return (
      chat.activeConversationId === consentConversationId &&
      chat.conversationGeneration === consentConversationGeneration
    );
  }

  function clearConsentTarget(): void {
    consentConversationId = null;
    consentConversationGeneration = null;
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
    <div class="flex basis-full flex-wrap items-center gap-2 sm:basis-auto">
      <div
        class="inline-flex rounded-md border border-border p-1"
        role="group"
        aria-label="Verwerkingsmodus"
      >
        <button
          type="button"
          class={`min-h-9 rounded px-3 text-sm focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring ${chat.activeMode === "local" ? "bg-accent font-semibold" : ""}`}
          aria-pressed={chat.activeMode === "local"}
          aria-describedby={chat.localAvailable === false
            ? "local-status"
            : undefined}
          disabled={chat.localAvailable === false || chat.sending}
          onclick={() => void chooseMode("local")}
        >
          🔒 Lokaal
        </button>
        <button
          type="button"
          class={`min-h-9 rounded px-3 text-sm focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring disabled:cursor-not-allowed disabled:opacity-50 ${chat.activeMode === "cloud" ? "bg-accent font-semibold" : ""}`}
          aria-pressed={chat.activeMode === "cloud"}
          aria-describedby={chat.cloudAvailable !== true
            ? "cloud-status"
            : undefined}
          disabled={chat.cloudAvailable !== true || chat.sending}
          onclick={() => void chooseMode("cloud")}
        >
          ☁ Cloud (EU)
        </button>
      </div>
      {#if chat.localAvailable === false}
        <span
          id="local-status"
          class="text-xs text-muted-foreground"
          role="status"
        >
          Lokaal is niet geconfigureerd.
        </span>
      {/if}
      {#if chat.cloudAvailable !== true}
        <span
          id="cloud-status"
          class="text-xs text-muted-foreground"
          role="status"
        >
          {chat.modeAvailabilityStatus === "loading"
            ? "Beschikbaarheid van modi laden…"
            : chat.modeAvailabilityStatus === "error"
              ? "Beschikbaarheid van modi kon niet worden opgehaald."
              : "Cloud (EU) is niet geconfigureerd."}
        </span>
      {/if}
    </div>
  </header>

  <dialog
    bind:this={consentDialog}
    aria-labelledby="cloud-consent-title"
    aria-describedby="cloud-consent-copy"
    oncancel={cancelCloudChoice}
    class="w-[min(90vw,32rem)] rounded-xl border border-border bg-background p-0 text-foreground shadow-xl backdrop:bg-black/50"
  >
    <div class="space-y-5 p-5">
      <div class="space-y-2">
        <h2 id="cloud-consent-title" class="text-lg font-semibold">
          Cloud (EU) gebruiken?
        </h2>
        <p id="cloud-consent-copy" class="text-sm leading-6">
          Uw vraag en de gevonden bronnen worden verwerkt door Scaleway
          (Parijs). Geen uploads.
        </p>
      </div>
      <div class="flex flex-wrap justify-end gap-2">
        <button
          type="button"
          class="min-h-10 rounded-md border border-border px-4 text-sm hover:bg-accent focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
          onclick={() => cancelCloudChoice()}
        >
          Annuleren
        </button>
        <button
          type="button"
          class="min-h-10 rounded-md bg-primary px-4 text-sm text-primary-foreground focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
          onclick={() => void confirmCloudChoice()}
        >
          Akkoord en doorgaan
        </button>
      </div>
    </div>
  </dialog>

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
          disabled={!chat.ready ||
            chat.sending ||
            !chat.draft.trim() ||
            chat.activeModeAvailable === false ||
            (chat.activeMode === "cloud" && chat.cloudAvailable !== true)}
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
