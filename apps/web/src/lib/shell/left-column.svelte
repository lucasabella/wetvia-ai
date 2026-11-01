<script lang="ts">
  import { resolve } from "$app/paths";
  import type { ChatStore } from "$lib/features/chat/chat.svelte";
  import ConversationHistoryPanel from "$lib/features/chat/conversation-history-panel.svelte";
  import type { ConversationHistoryStore } from "$lib/features/chat/conversation-history.svelte";
  import DossierPanel from "$lib/features/dossier/dossier-panel.svelte";
  import SettingsPanel from "$lib/features/settings/settings-panel.svelte";

  let {
    showHistoryHeading = true,
    idPrefix = "",
    chat,
    history,
    onNavigate = () => undefined,
  }: {
    showHistoryHeading?: boolean;
    idPrefix?: string;
    chat: ChatStore;
    history: ConversationHistoryStore;
    onNavigate?: () => void;
  } = $props();

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
    <ConversationHistoryPanel {chat} {history} {idPrefix} {onNavigate} />
    <DossierPanel {idPrefix} {onNavigate} />
    <SettingsPanel {idPrefix} onClearAll={() => chat.clearAllConversations()} />
  </section>
</div>
