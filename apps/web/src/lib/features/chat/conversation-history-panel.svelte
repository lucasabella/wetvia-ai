<script lang="ts">
  import { tick } from "svelte";

  import { groupConversations } from "./conversation-history.svelte";
  import type { ConversationHistoryStore } from "./conversation-history.svelte";
  import type { ChatStore } from "./chat.svelte";

  let {
    chat,
    history,
    idPrefix = "",
    onNavigate = () => undefined,
  }: {
    chat: ChatStore;
    history: ConversationHistoryStore;
    idPrefix?: string;
    onNavigate?: () => void;
  } = $props();

  let editingId = $state<string | null>(null);
  let renameValue = $state("");
  let renameInput = $state<HTMLInputElement>();
  let newConversationButton = $state<HTMLButtonElement>();
  const groups = $derived(groupConversations(history.conversations));

  async function beginRename(id: string, title: string): Promise<void> {
    editingId = id;
    renameValue = title;
    await tick();
    renameInput?.focus();
    renameInput?.select();
  }

  async function saveRename(id: string): Promise<void> {
    if (await chat.renameConversation(id, renameValue)) {
      editingId = null;
      renameValue = "";
      await tick();
      document.getElementById(`${idFor(id)}-select`)?.focus();
    }
  }

  async function cancelRename(id: string): Promise<void> {
    editingId = null;
    renameValue = "";
    await tick();
    document.getElementById(`${idFor(id)}-select`)?.focus();
  }

  async function selectConversation(id: string): Promise<void> {
    await chat.openConversation(id);
    onNavigate();
  }

  async function deleteConversation(id: string): Promise<void> {
    await chat.deleteConversation(id);
    if (editingId === id) {
      editingId = null;
    }
    await tick();
    newConversationButton?.focus();
  }

  function startNewConversation(): void {
    chat.newConversation();
    onNavigate();
  }

  function idFor(value: string): string {
    return `${idPrefix}${value.replaceAll(/[^a-zA-Z0-9_-]/g, "-")}`;
  }
</script>

<section class="flex min-h-0 flex-1 flex-col gap-3" aria-label="Gesprekken">
  <button
    type="button"
    bind:this={newConversationButton}
    class="min-h-10 rounded-md border border-border px-3 text-left text-sm font-medium hover:bg-accent focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring disabled:opacity-50"
    onclick={startNewConversation}
    disabled={!history.ready}
  >
    + Nieuw gesprek
  </button>

  {#if history.storageError}
    <p class="text-xs text-destructive" role="status">{history.storageError}</p>
  {/if}
  {#if history.skippedRecords > 0}
    <p class="text-xs text-muted-foreground" role="status">
      Een of meer gesprekken konden niet worden geladen. Andere gesprekken zijn
      beschikbaar gebleven.
    </p>
  {/if}

  <nav
    class="min-h-0 flex-1 space-y-4 overflow-y-auto"
    aria-label="Gespreksgeschiedenis"
  >
    {#if !history.ready}
      <p class="text-sm text-muted-foreground" role="status">
        Gesprekken laden…
      </p>
    {:else if history.conversations.length === 0}
      <p class="text-sm text-muted-foreground">Nog geen gesprekken.</p>
    {:else}
      {#each groups as group (group.label)}
        <section
          aria-labelledby={`${idFor("history")}-${group.label.replaceAll(" ", "-")}`}
        >
          <h3
            id={`${idFor("history")}-${group.label.replaceAll(" ", "-")}`}
            class="mb-1 text-xs font-semibold text-muted-foreground"
          >
            {group.label}
          </h3>
          <ul class="space-y-1">
            {#each group.conversations as conversation (conversation.id)}
              <li
                class="rounded-md border border-transparent p-1 hover:border-border"
              >
                {#if editingId === conversation.id}
                  <form
                    class="space-y-2"
                    onsubmit={(event) => {
                      event.preventDefault();
                      void saveRename(conversation.id);
                    }}
                  >
                    <label
                      class="sr-only"
                      for={`${idFor(conversation.id)}-rename`}
                    >
                      Gesprek hernoemen
                    </label>
                    <input
                      id={`${idFor(conversation.id)}-rename`}
                      bind:this={renameInput}
                      bind:value={renameValue}
                      maxlength="60"
                      class="min-h-9 w-full rounded border border-input bg-background px-2 text-sm focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
                    />
                    <div class="flex gap-2">
                      <button
                        type="submit"
                        class="min-h-8 rounded bg-primary px-2 text-xs text-primary-foreground"
                      >
                        Opslaan
                      </button>
                      <button
                        type="button"
                        class="min-h-8 rounded px-2 text-xs underline"
                        onclick={() => void cancelRename(conversation.id)}
                      >
                        Annuleren
                      </button>
                    </div>
                  </form>
                {:else}
                  <button
                    type="button"
                    id={`${idFor(conversation.id)}-select`}
                    class={`w-full rounded px-2 py-1.5 text-left text-sm hover:bg-accent focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring ${chat.activeConversationId === conversation.id ? "bg-accent font-medium" : ""}`}
                    aria-current={chat.activeConversationId === conversation.id
                      ? "page"
                      : undefined}
                    onclick={() => void selectConversation(conversation.id)}
                  >
                    <span class="block truncate">{conversation.title}</span>
                    <span class="mt-0.5 block text-xs text-muted-foreground">
                      {conversation.mode === "local" ? "Lokaal" : "Cloud (EU)"}
                      · {conversation.messageCount}
                      {conversation.messageCount === 1 ? "vraag" : "vragen"}
                    </span>
                  </button>
                  <div class="flex justify-end gap-2 px-2 pb-1">
                    <button
                      type="button"
                      class="min-h-7 text-xs text-muted-foreground underline underline-offset-2 hover:text-foreground"
                      aria-label={`Hernoem ${conversation.title}`}
                      onclick={() =>
                        void beginRename(conversation.id, conversation.title)}
                    >
                      Hernoem
                    </button>
                    <button
                      type="button"
                      class="min-h-7 text-xs text-muted-foreground underline underline-offset-2 hover:text-destructive"
                      aria-label={`Verwijder ${conversation.title}`}
                      onclick={() => void deleteConversation(conversation.id)}
                    >
                      Verwijder
                    </button>
                  </div>
                {/if}
              </li>
            {/each}
          </ul>
        </section>
      {/each}
    {/if}
  </nav>
</section>
