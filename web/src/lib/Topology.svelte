<script lang="ts">
  import { ageSeconds, clip, layout, type Graph } from "./graph";

  let { graph, now }: { graph: Graph; now: number } = $props();
  let busy = $state(false);
  let note = $state("");

  const names = $derived(Object.keys(graph.nodes));
  const pos = $derived(layout(names));
  const edges = $derived(Object.values(graph.edges).sort((a, b) => b.lastTs - a.lastTs));
  const W = 900, H = 520, NW = 150, NH = 54;

  type Pt = { x: number; y: number };
  // Quadratic curve between the box edges; the control point is pushed sideways so two-way and crossing paths separate.
  const curve = (a: Pt, b: Pt) => {
    const { start, end } = clip(a, b, NW / 2, NH / 2);
    const dx = end.x - start.x, dy = end.y - start.y, len = Math.hypot(dx, dy) || 1;
    const c = { x: (start.x + end.x) / 2 - (dy / len) * 30, y: (start.y + end.y) / 2 + (dx / len) * 30 };
    return { d: `M${start.x},${start.y} Q${c.x},${c.y} ${end.x},${end.y}`,
             label: { x: 0.25 * start.x + 0.5 * c.x + 0.25 * end.x, y: 0.25 * start.y + 0.5 * c.y + 0.25 * end.y } };
  };
  const intrusion = (e: { src: string; verdict: string }) => e.src === "attacker" && e.verdict === "allow";
  const wording = (e: { src: string; verdict: string }) =>
    e.verdict === "deny" ? "denied" : intrusion(e) ? "allowed, nothing stopped it" : e.verdict;

  async function useApp() {
    busy = true;
    note = "";
    try {
      const r = await fetch("/app/use", { method: "POST" });
      note = r.ok ? "Sent one visit through web." : "The app didn't answer. Is `make clinic` deployed?";
    } catch {
      note = "The observer isn't reachable.";
    }
    busy = false;
  }
</script>

<section>
  <div class="bar">
    <div>
      <button class="primary" onclick={useApp} disabled={busy}>Use the app</button>
      <span class="note" role="status">{note}</span>
    </div>
  </div>

  {#if names.length === 0}
    <div class="empty">
      <h2>No traffic yet</h2>
      <p>Press <b>Use the app</b>. A visit goes web → records-api and billing → Postgres, and each hop appears here.</p>
    </div>
  {:else}
    <svg viewBox="0 0 {W} {H}" role="img" aria-label="Service topology. {edges.length} observed paths, listed below.">
      <defs>
        {#each ["allow", "deny", "info", "intrusion"] as k}
          <marker id="arrow-{k}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
            <path d="M0,0 L10,5 L0,10 z" class="head {k}" />
          </marker>
        {/each}
      </defs>
      {#each edges as e (e.src + e.dst)}
        {#if pos[e.src] && pos[e.dst]}
          {@const kind = intrusion(e) ? "intrusion" : e.verdict}
          {@const c = curve(pos[e.src], pos[e.dst])}
          <g style="opacity:{ageSeconds(e, now) > 60 ? 0.3 : 1}">
            <path d={c.d} class="edge {kind}" marker-end="url(#arrow-{kind})" />
            <text x={c.label.x} y={c.label.y} class="elabel {kind}" text-anchor="middle">
              {e.verdict === "deny" ? "✕ " : intrusion(e) ? "⚠ " : ""}{e.count}
            </text>
          </g>
        {/if}
      {/each}
      {#each names as n (n)}
        {@const p = pos[n]}
        <g class="node" class:adversary={n === "attacker"} transform="translate({p.x - NW / 2},{p.y - NH / 2})">
          <rect width={NW} height={NH} rx="10" />
          <text x={NW / 2} y="22" text-anchor="middle" class="nname">{n}</text>
          <text x={NW / 2} y="40" text-anchor="middle" class="nsub">
            {#if graph.registered[n]}registered, unused{:else if n === "attacker"}no identity{:else if n === "user"}browser{:else}no registration{/if}
          </text>
        </g>
      {/each}
    </svg>

    <h2>Observed paths</h2>
    <ul class="paths">
      {#each edges as e (e.src + e.dst)}
        <li class:alert={intrusion(e)} class:deny={e.verdict === "deny"}>
          <span class="route data">{e.src} → {e.dst}</span>
          <span class="verdict">{wording(e)}</span>
          <span>{e.count} {e.count === 1 ? "call" : "calls"}</span>
          <span class="age">{ageSeconds(e, now)}s ago</span>
        </li>
      {/each}
    </ul>
    <h2>Registered identities</h2>
    <p class="hint">SPIRE has issued a registration for these workloads, but nothing here uses it yet. The next slice puts it to work.</p>
    <ul class="ids">
      {#each names.filter((n) => graph.registered[n]) as n (n)}
        <li class="data">{graph.registered[n]}</li>
      {/each}
    </ul>
  {/if}
</section>

<style>
  section { display: grid; gap: 1rem; }
  .bar { display: flex; justify-content: flex-end; align-items: center; gap: 1rem; flex-wrap: wrap; }
  .note { margin-left: 0.75rem; color: var(--ink-soft); font-size: 0.9rem; }
  button.primary { font: inherit; font-weight: 600; color: #fff; background: var(--credential); border: 0; border-radius: 99px; padding: 0.5rem 1.2rem; cursor: pointer; }
  :global(:root[data-theme="dark"]) button.primary { color: #07121c; }
  button.primary:disabled { opacity: 0.6; cursor: progress; }
  svg { width: 100%; height: auto; background: var(--surface); border: 1px solid var(--rule); border-radius: var(--radius); }
  .edge { fill: none; stroke-width: 2.5; transition: opacity 0.4s; }
  .edge.allow { stroke: var(--credential); }
  .edge.info { stroke: var(--ink-soft); }
  .edge.deny { stroke: var(--deny); stroke-dasharray: 7 5; }
  .edge.intrusion { stroke: var(--expiry-fill); stroke-width: 3.5; }
  .head.allow { fill: var(--credential); } .head.info { fill: var(--ink-soft); }
  .head.deny { fill: var(--deny); } .head.intrusion { fill: var(--expiry-fill); }
  .elabel { font: 600 13px var(--font-data); paint-order: stroke; stroke: var(--surface); stroke-width: 5px; fill: var(--ink); }
  .elabel.deny { fill: var(--deny); } .elabel.intrusion { fill: var(--expiry); }
  .node rect { fill: var(--surface-sunk); stroke: var(--rule); stroke-width: 1.5; }
  .node.adversary rect { stroke: var(--expiry-fill); stroke-width: 2.5; }
  .nname { font: 700 16px var(--font-body); fill: var(--ink); }
  .nsub { font: 12px var(--font-body); fill: var(--ink-soft); }
  h2 { margin: 0.5rem 0 0; font-size: 1.1rem; }
  .paths, .ids { list-style: none; margin: 0; padding: 0; display: grid; gap: 0.35rem; }
  .paths li { display: grid; grid-template-columns: minmax(12rem, 1.2fr) 2fr 6rem 5rem; gap: 0.75rem; background: var(--surface); border: 1px solid var(--rule); border-radius: 10px; padding: 0.5rem 0.9rem; }
  .paths li.alert { border-color: var(--expiry-fill); }
  .paths li.alert .verdict { color: var(--expiry); font-weight: 600; }
  .paths li.deny .verdict { color: var(--deny); font-weight: 600; }
  .age { color: var(--ink-soft); text-align: right; }
  .hint { margin: 0; color: var(--ink-soft); }
  .ids li { color: var(--ink-soft); }
  .empty { background: var(--surface); border: 1px dashed var(--rule); border-radius: var(--radius); padding: 2rem; }
  .empty h2 { margin: 0 0 0.4rem; } .empty p { margin: 0; color: var(--ink-soft); }
  @media (max-width: 640px) { .paths li { grid-template-columns: 1fr 1fr; } }
</style>
