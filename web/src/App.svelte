<script lang="ts">
  import { onMount } from "svelte";
  import SvidCard from "./lib/SvidCard.svelte";
  import { reduce, type Cards, type Ev } from "./lib/identity";

  let cards = $state<Cards>({});
  let now = $state(Date.now());
  let live = $state(false);
  let theme = $state<"light" | "dark" | "system">("system");

  const list = $derived(Object.values(cards).sort((a, b) => a.workload.localeCompare(b.workload)));

  onMount(() => {
    try { theme = (localStorage.getItem("ztp-theme") as typeof theme) ?? "system"; } catch { /* storage blocked */ }
    const tick = setInterval(() => (now = Date.now()), 1000);
    const es = new EventSource("/events");
    es.onopen = () => (live = true);
    es.onerror = () => (live = false);
    es.onmessage = (m) => (cards = reduce(cards, JSON.parse(m.data) as Ev));
    return () => { clearInterval(tick); es.close(); };
  });

  $effect(() => {
    const root = document.documentElement;
    if (theme === "system") root.removeAttribute("data-theme");
    else root.setAttribute("data-theme", theme);
    try { localStorage.setItem("ztp-theme", theme); } catch { /* storage blocked */ }
  });

  const nextTheme = () => (theme = theme === "system" ? "dark" : theme === "dark" ? "light" : "system");
</script>

<main>
  <header>
    <div>
      <h1>Identity</h1>
      <p>Every workload gets a short-lived SPIFFE identity from SPIRE and swaps it for a fresh one before it runs out.</p>
    </div>
    <div class="controls">
      <span class="conn" class:live role="status">
        <span class="dot" aria-hidden="true"></span>{live ? "Receiving events" : "Observer not reachable"}
      </span>
      <button onclick={nextTheme} aria-label="Theme: {theme}. Switch theme">Theme: {theme}</button>
    </div>
  </header>

  {#if list.length === 0}
    <section class="empty">
      <h2>No identities yet</h2>
      <p>Run <code>make up &amp;&amp; make echo</code>, then <code>make observer</code>. Cards appear when a workload receives its first SVID.</p>
    </section>
  {:else}
    <div class="grid">
      {#each list as card (card.spiffeId)}
        <SvidCard {card} {now} />
      {/each}
    </div>
  {/if}
</main>

<style>
  main { max-width: 960px; margin: 0 auto; padding: 2rem 1rem 4rem; display: grid; gap: 1.5rem; }
  header { display: flex; justify-content: space-between; gap: 1.5rem; align-items: flex-start; flex-wrap: wrap; }
  h1 { margin: 0; font-size: 2.4rem; letter-spacing: -0.02em; line-height: 1.1; }
  header p { margin: 0.4rem 0 0; max-width: 46ch; color: var(--ink-soft); }
  .controls { display: flex; gap: 0.75rem; align-items: center; flex-wrap: wrap; }
  .conn { display: inline-flex; gap: 0.45rem; align-items: center; font-size: 0.9rem; color: var(--deny); }
  .conn.live { color: var(--ok); }
  .dot { width: 9px; height: 9px; border-radius: 50%; background: currentColor; }
  button { font: inherit; font-size: 0.9rem; color: var(--ink); background: var(--surface); border: 1px solid var(--rule); border-radius: 99px; padding: 0.35rem 0.9rem; cursor: pointer; }
  button:hover { border-color: var(--credential); }
  .grid { display: grid; gap: 1rem; }
  .empty { background: var(--surface); border: 1px dashed var(--rule); border-radius: var(--radius); padding: 2rem; }
  .empty h2 { margin: 0 0 0.4rem; }
  .empty p { margin: 0; color: var(--ink-soft); }
  code { font-family: var(--font-data); font-size: 0.9em; background: var(--surface-sunk); padding: 0.1rem 0.4rem; border-radius: 5px; }
</style>
