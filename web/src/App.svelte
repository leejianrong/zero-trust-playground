<script lang="ts">
  import { onMount } from "svelte";
  import Explore from "./lib/Explore.svelte";
  import { reduce, type Cards, type Ev } from "./lib/identity";
  import SvidCard from "./lib/SvidCard.svelte";

  const VIEWS = [
    { id: "explore", label: "Explore", blurb: "Every tool in the playground, what it is for, and whether it is running." },
    { id: "identity", label: "Identity", blurb: "Every workload gets a short-lived SPIFFE identity from SPIRE and swaps it for a fresh one before it runs out." },
  ] as const;
  type ViewId = (typeof VIEWS)[number]["id"];

  const fromHash = (): ViewId => (VIEWS.find((v) => `#${v.id}` === location.hash)?.id ?? "explore");
  let view = $state<ViewId>("explore");
  let cards = $state<Cards>({});
  let now = $state(Date.now());
  let offline = $state(false);
  let theme = $state<"light" | "dark" | "system">("system");

  const list = $derived(Object.values(cards).sort((a, b) => a.workload.localeCompare(b.workload)));
  const current = $derived(VIEWS.find((v) => v.id === view)!);

  onMount(() => {
    view = fromHash();
    try { theme = (localStorage.getItem("ztp-theme") as typeof theme) ?? "system"; } catch { /* storage blocked */ }
    const tick = setInterval(() => (now = Date.now()), 1000);
    const es = new EventSource("/events");
    es.onopen = () => (offline = false);
    es.onerror = () => (offline = true);
    es.onmessage = (m) => {
      const ev = JSON.parse(m.data) as Ev;
      cards = reduce(cards, ev);
    };
    const onHash = () => (view = fromHash());
    addEventListener("hashchange", onHash);
    return () => { clearInterval(tick); es.close(); removeEventListener("hashchange", onHash); };
  });

  $effect(() => {
    const root = document.documentElement;
    if (theme === "system") root.removeAttribute("data-theme");
    else root.setAttribute("data-theme", theme);
    try { localStorage.setItem("ztp-theme", theme); } catch { /* storage blocked */ }
  });

  const THEMES = [
    { id: "system", label: "System theme", icon: "M3 5h18v11H3zM8 20h8M12 16v4" },
    { id: "light", label: "Light theme", icon: "M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8zM12 2v2M12 20v2M2 12h2M20 12h2M5 5l1.5 1.5M17.5 17.5L19 19M5 19l1.5-1.5M17.5 6.5L19 5" },
    { id: "dark", label: "Dark theme", icon: "M20 14.5A8 8 0 0 1 9.5 4 8 8 0 1 0 20 14.5z" },
  ] as const;
</script>

<main>
  <header>
    <nav aria-label="Views">
      {#each VIEWS as v (v.id)}
        <a href="#{v.id}" aria-current={view === v.id ? "page" : undefined}>{v.label}</a>
      {/each}
    </nav>
    <div class="controls">
      <div class="themes" role="group" aria-label="Theme">
        {#each THEMES as t (t.id)}
          <button onclick={() => (theme = t.id)} aria-pressed={theme === t.id} aria-label={t.label} title={t.label}>
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d={t.icon} /></svg>
          </button>
        {/each}
      </div>
    </div>
  </header>

  <div class="title">
    <h1>{current.label}</h1>
    <p>{current.blurb}</p>
  </div>

  {#if view === "explore"}
    <Explore />
  {:else if view === "identity"}
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
  {/if}

  {#if offline}
    <p class="offline" role="status">Not live: the observer is not reachable. Run <code>make observer</code>.</p>
  {/if}
</main>

<style>
  main { max-width: 960px; margin: 0 auto; padding: 1.25rem 1rem 4rem; display: grid; gap: 1.25rem; }
  header { display: flex; justify-content: space-between; gap: 1rem; align-items: center; flex-wrap: wrap; }
  nav { display: flex; gap: 0.25rem; background: var(--surface); border: 1px solid var(--rule); border-radius: 99px; padding: 0.25rem; }
  nav a { color: var(--ink-soft); text-decoration: none; font-weight: 600; padding: 0.35rem 1rem; border-radius: 99px; }
  nav a:hover { color: var(--ink); }
  nav a[aria-current="page"] { background: var(--credential); color: #fff; }
  :global(:root[data-theme="dark"]) nav a[aria-current="page"] { color: #07121c; }
  .title h1 { margin: 0; font-size: 2.4rem; letter-spacing: -0.02em; line-height: 1.1; }
  .title p { margin: 0.4rem 0 0; max-width: 52ch; color: var(--ink-soft); }
  .controls { display: flex; gap: 0.75rem; align-items: center; flex-wrap: wrap; }
  .themes { display: flex; gap: 0.15rem; background: var(--surface); border: 1px solid var(--rule); border-radius: 99px; padding: 0.2rem; }
  .themes button { display: grid; place-content: center; width: 1.9rem; height: 1.9rem; padding: 0; color: var(--ink-soft); background: none; border: 0; border-radius: 50%; cursor: pointer; }
  .themes button:hover { color: var(--ink); }
  .themes button[aria-pressed="true"] { background: var(--credential-wash); color: var(--credential); }
  .themes svg { width: 1.1rem; height: 1.1rem; fill: none; stroke: currentColor; stroke-width: 1.8; stroke-linecap: round; stroke-linejoin: round; }
  .offline { margin: 0; font-size: 0.85rem; color: var(--deny); text-align: center; }
  .grid { display: grid; gap: 0.75rem; grid-template-columns: repeat(auto-fill, minmax(170px, 1fr)); }
  .empty { background: var(--surface); border: 1px dashed var(--rule); border-radius: var(--radius); padding: 2rem; }
  .empty h2 { margin: 0 0 0.4rem; }
  .empty p { margin: 0; color: var(--ink-soft); }
  code { font-family: var(--font-data); font-size: 0.9em; background: var(--surface-sunk); padding: 0.1rem 0.4rem; border-radius: 5px; }
</style>
