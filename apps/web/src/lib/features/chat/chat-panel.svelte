<script lang="ts">
  import { ChatStore } from "./chat.svelte";

  const chat = new ChatStore();
</script>

<section
  class="flex h-full min-h-[40vh] flex-col"
  aria-labelledby="gesprek-kop"
>
  <h1 id="gesprek-kop" class="sr-only">Gesprek</h1>
  <p class="sr-only">{chat.messages.length} berichten</p>
</section>
