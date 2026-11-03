<script lang="ts">
  import { onMount } from "svelte";
  import AttackLab from "./lib/AttackLab.svelte";
  import { reduceResults, type Attack, type Results } from "./lib/attacks";
  import { emptyGraph, reduceGraph, type Graph } from "./lib/graph";
  import { reduce, type Cards, type Ev } from "./lib/identity";
  import SvidCard from "./lib/SvidCard.svelte";
  import Topology from "./lib/Topology.svelte";

  const VIEWS = [
    { id: "identity", label: "Identity", blurb: "Every workload gets a short-lived SPIFFE identity from SPIRE and swaps it for a fresh one before it runs out." },
    { id: "topology", label: "Topology", blurb: "Who talks to whom right now. Lines fade when a path goes quiet." },
    { id: "attacks", label: "Attack lab", blurb: "Each attack runs from the attacker pod. With every layer off, all of them should get through. That is the baseline the next slices take apart." },
  ] as const;
  type ViewId = (typeof VIEWS)[number]["id"];

  const fromHash = (): ViewId => (VIEWS.find((v) => `#${v.id}` === location.hash)?.id ?? "identity");
  let view = $state<ViewId>("identity");
  let cards = $state<Cards>({});
  let graph = $state<Graph>(emptyGraph());
  let results = $state<Results>({});
  let attacks = $state<Attack[]>([]);
  let now = $state(Date.now());
  let live = $state(false);
  let theme = $state<"light" | "dark" | "system">("system");

  const list = $derived(Object.values(cards).sort((a, b) => a.workload.localeCompare(b.workload)));
  const current = $derived(VIEWS.find((v) => v.id === view)!);

  onMount(() => {
    view = fromHash();
    try { theme = (localStorage.getItem("ztp-theme") as typeof theme) ?? "system"; } catch { /* storage blocked */ }
    const tick = setInterval(() => (now = Date.now()), 1000);
    const es = new EventSource("/events");
    es.onopen = () => (live = true);
    es.onerror = () => (live = false);
    es.onmessage = (m) => {
      const ev = JSON.parse(m.data) as Ev;
      cards = reduce(cards, ev);
      graph = reduceGraph(graph, ev);
      results = reduceResults(results, ev);
    };
    fetch("/attacks").then((r) => r.json()).then((a) => (attacks = a)).catch(() => {});
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

  const nextTheme = () => (theme = theme === "system" ? "dark" : theme === "dark" ? "light" : "system");
</script>

<main>
  <header>
    <nav aria-label="Views">
      {#each VIEWS as v (v.id)}
        <a href="#{v.id}" aria-current={view === v.id ? "page" : undefined}>{v.label}</a>
      {/each}
    </nav>
    <div class="controls">
      <span class="conn" class:live role="status">
        <span class="dot" aria-hidden="true"></span>{live ? "Receiving events" : "Observer not reachable"}
      </span>
      <button onclick={nextTheme} aria-label="Theme: {theme}. Switch theme">Theme: {theme}</button>
    </div>
  </header>

  <div class="title">
    <h1>{current.label}</h1>
    <p>{current.blurb}</p>
  </div>

  {#if view === "identity"}
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
  {:else if view === "topology"}
    <Topology {graph} {now} />
  {:else}
    <AttackLab {attacks} {results} />
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
