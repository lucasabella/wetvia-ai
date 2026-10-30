<script lang="ts">
  import "./layout.css";
  import type { Snippet } from "svelte";

  let { children }: { children: Snippet } = $props();

  $effect(() => {
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const apply = () => {
      document.documentElement.classList.toggle("dark", media.matches);
    };
    apply();
    media.addEventListener("change", apply);
    return () => media.removeEventListener("change", apply);
  });
</script>

<svelte:head>
  <title>Wetvia</title>
  <link rel="icon" href="/logo.svg" type="image/svg+xml" />
</svelte:head>

{@render children()}
