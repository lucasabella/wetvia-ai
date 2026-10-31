<script lang="ts">
  import { resolve } from "$app/paths";
  import { env } from "$env/dynamic/public";
  import { createWetviaClient, streamChatEvents } from "@wetvia/api-client";
  import LibraryIcon from "@lucide/svelte/icons/library";
  import MenuIcon from "@lucide/svelte/icons/menu";
  import ChatPanel from "$lib/features/chat/chat-panel.svelte";
  import { ChatStore } from "$lib/features/chat/chat.svelte";
  import { SourcesStore } from "$lib/features/sources/sources.svelte";
  import SourcesPanel from "$lib/features/sources/sources-panel.svelte";
  import LeftColumn from "$lib/shell/left-column.svelte";
  import { DESKTOP_MEDIA_QUERY, sheetStaysOpen } from "$lib/shell/sheets";
  import { Button } from "$lib/ui/button/index.js";
  import * as Sheet from "$lib/ui/sheet/index.js";

  let historyOpen = $state(false);
  let sourcesOpen = $state(false);
  const sources = new SourcesStore();
  const apiClient = createWetviaClient({
    baseUrl: env.PUBLIC_API_BASE_URL?.trim() || "",
  });
  const chat = new ChatStore(
    (request, options) => streamChatEvents(apiClient, request, options),
    sources,
  );

  function selectSource(turnId: string, chunkId: string): void {
    if (
      chat.selectSource(turnId, chunkId) &&
      window.matchMedia("(max-width: 767px)").matches
    ) {
      sourcesOpen = true;
    }
  }

  $effect(() => {
    const media = window.matchMedia(DESKTOP_MEDIA_QUERY);
    const closeOnDesktop = () => {
      historyOpen = sheetStaysOpen(historyOpen, media.matches);
      sourcesOpen = sheetStaysOpen(sourcesOpen, media.matches);
    };
    closeOnDesktop();
    media.addEventListener("change", closeOnDesktop);
    return () => media.removeEventListener("change", closeOnDesktop);
  });
</script>

<div class="flex h-dvh flex-col overflow-hidden bg-background text-foreground">
  <a
    href="#inhoud"
    class="sr-only bg-background text-foreground focus:not-sr-only focus:absolute focus:top-3 focus:left-3 focus:z-50 focus:rounded-md focus:px-3 focus:py-2 focus:ring-2 focus:ring-ring"
  >
    Ga naar de inhoud
  </a>

  <header
    class="flex items-center gap-2 border-b border-border px-3 py-2 md:hidden"
  >
    <Button
      variant="outline"
      size="icon"
      aria-expanded={historyOpen}
      aria-controls="geschiedenis-sheet"
      onclick={() => (historyOpen = true)}
    >
      <MenuIcon />
      <span class="sr-only">Geschiedenis</span>
    </Button>
    <a href={resolve("/")} class="flex items-center gap-2 font-semibold">
      <img src="/logo.svg" width="32" height="32" alt="" />
      Wetvia
    </a>
    <Button
      variant="outline"
      class="ml-auto"
      aria-expanded={sourcesOpen}
      aria-controls="bronnen-sheet"
      onclick={() => (sourcesOpen = true)}
    >
      <LibraryIcon />
      Bronnen
    </Button>
  </header>

  <div
    class="grid min-h-0 flex-1 md:grid-cols-[16rem_minmax(0,1fr)_18rem] lg:grid-cols-[18rem_minmax(0,1fr)_22rem]"
  >
    <aside
      class="hidden flex-col gap-2 border-r border-border p-4 md:flex"
      aria-label="Zijbalk"
    >
      <LeftColumn />
    </aside>
    <main id="inhoud" class="min-h-0 min-w-0 p-3 md:p-4">
      <ChatPanel {chat} onSourceSelect={selectSource} />
    </main>
    <aside
      class="hidden min-h-0 flex-col border-l border-border p-4 md:flex"
      aria-labelledby="bronnen-kop"
    >
      <h2 id="bronnen-kop" class="mb-3 shrink-0 text-sm font-medium">
        Bronnen
      </h2>
      <SourcesPanel {sources} labelledBy="bronnen-kop" idPrefix="desktop-" />
    </aside>
  </div>
</div>

<Sheet.Root bind:open={historyOpen}>
  <Sheet.Content
    id="geschiedenis-sheet"
    side="left"
    class="w-[min(100%,20rem)] md:hidden"
  >
    <Sheet.Header>
      <Sheet.Title>Geschiedenis</Sheet.Title>
    </Sheet.Header>
    <LeftColumn showHistoryHeading={false} idPrefix="drawer-" />
  </Sheet.Content>
</Sheet.Root>

<Sheet.Root bind:open={sourcesOpen}>
  <Sheet.Content
    id="bronnen-sheet"
    side="bottom"
    class="max-h-[70vh] md:hidden"
  >
    <Sheet.Header>
      <Sheet.Title id="bronnen-sheet-kop">Bronnen</Sheet.Title>
    </Sheet.Header>
    <SourcesPanel {sources} labelledBy="bronnen-sheet-kop" idPrefix="mobile-" />
  </Sheet.Content>
</Sheet.Root>
