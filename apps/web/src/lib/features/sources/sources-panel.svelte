<script lang="ts">
  import { SourcesStore } from "./sources.svelte";

  let { labelledBy }: { labelledBy: string } = $props();

  const sources = new SourcesStore();
</script>

<div
  class="min-h-24 font-serif text-foreground"
  role="region"
  aria-labelledby={labelledBy}
>
  <p class="sr-only">{sources.items.length} bronnen</p>
</div>
