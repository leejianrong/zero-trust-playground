<script lang="ts">
  import { onMount } from "svelte";
  import { EDGES, NODES, PATTERN_LAYERS, lineFor, status, type Node } from "./architecture";
  import { fetchModes, type Modes } from "./layers";

  let modes = $state<Modes>({});
  let unreachable = $state(false);
  const W = 120, H = 40;
  const line = $derived(lineFor(modes.mtls as never));
  const identityOn = $derived(modes.identity === "audit" || modes.identity === "enforce");
  const byId = (id: string) => NODES.find((n) => n.id === id) as Node;
  const mid = (n: Node) => ({ x: n.x + W / 2, y: n.y + H / 2 });

  // Draw from the edge of one box to the edge of the other, along the line between their centres.
  function ends(a: Node, b: Node) {
    const p = mid(a), q = mid(b);
    const clip = (c: { x: number; y: number }, d: { x: number; y: number }) => {
      const dx = d.x - c.x, dy = d.y - c.y;
      const t = Math.min(dx ? (W / 2) / Math.abs(dx) : Infinity, dy ? (H / 2) / Math.abs(dy) : Infinity);
      return { x: c.x + dx * t, y: c.y + dy * t };
    };
    return [clip(p, q), clip(q, p)];
  }

  async function refresh() {
    try { modes = await fetchModes(); unreachable = false; } catch { unreachable = true; }
  }
  onMount(() => {
    refresh();
    const t = setInterval(refresh, 3000);
    return () => clearInterval(t);
  });

  const LABEL: Record<string, string> = { off: "Off", audit: "Audit", enforce: "Enforce", planned: "Not built yet" };
</script>

<section>
  {#if unreachable}
    <p class="error" role="alert">The observer isn't reachable, so the modes are unknown. Start it with <code>make observer</code>.</p>
  {/if}

  <figure>
    <svg viewBox="0 0 820 290" role="img" aria-label="The clinic's call paths. Lines between services are drawn according to the mutual TLS mode: {line.label}.">
      <defs>
        <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
          <path d="M0 0L10 5L0 10z" fill="context-stroke" />
        </marker>
      </defs>
      {#each EDGES as e (e.from + e.to)}
        {@const [a, b] = ends(byId(e.from), byId(e.to))}
        <line x1={a.x} y1={a.y} x2={b.x} y2={b.y} marker-end="url(#arrow)"
          stroke={e.guarded ? line.color : "var(--rule)"} stroke-width={e.guarded ? line.width : 2}
          stroke-dasharray={e.guarded ? line.dash : "2 6"} stroke-linecap="round" />
      {/each}
      {#each NODES as n (n.id)}
        <g transform="translate({n.x} {n.y})">
          <rect width={W} height={H} rx="10" fill="var(--surface)" stroke="var(--rule)" />
          <text x={W / 2} y={H / 2 + 5} text-anchor="middle" class="node">{n.label}</text>
          {#if n.workload && identityOn}
            <g transform="translate({W - 14} -8)"><circle r="9" fill="var(--credential)" /><text y="3.5" text-anchor="middle" class="badge">ID</text></g>
          {/if}
        </g>
      {/each}
    </svg>
    <figcaption>
      <span><b>Lines between services:</b> {line.label}.</span>
      <span><b>ID badge:</b> the service holds and uses its identity{identityOn ? "" : " (identity is off, so no badge)"}.</span>
      <span><b>Dotted grey lines</b> (browser to web, records-api to Postgres) are not covered by mutual TLS. Network policy and short-lived secrets answer those later.</span>
    </figcaption>
  </figure>

  <ul>
    {#each PATTERN_LAYERS as layer (layer.id)}
      {@const s = status(layer, modes)}
      <li class:planned={s === "planned"}>
        <div>
          <h2>{layer.name}</h2>
          <p class="comp">Pattern component: <b>{layer.component}</b></p>
          <p>{layer.protects}</p>
        </div>
        <span class="chip {s}" aria-label="{layer.name}: {LABEL[s]}">{LABEL[s]}{s === "planned" ? ` (${layer.slice})` : ""}</span>
      </li>
    {/each}
  </ul>
</section>

<style>
  section { display: grid; gap: 1.25rem; }
  figure { margin: 0; background: var(--surface); border: 1px solid var(--rule); border-radius: var(--radius); padding: 1rem 1.2rem; display: grid; gap: 0.8rem; }
  svg { width: 100%; height: auto; }
  .node { font: 600 14px var(--font-body); fill: var(--ink); }
  .badge { font: 700 9px var(--font-data); fill: #fff; }
  :global(:root[data-theme="dark"]) .badge { fill: #07121c; }
  figcaption { display: grid; gap: 0.25rem; color: var(--ink-soft); font-size: 0.9rem; }
  ul { list-style: none; margin: 0; padding: 0; display: grid; gap: 0.7rem; }
  li { display: flex; justify-content: space-between; gap: 1.5rem; flex-wrap: wrap; background: var(--surface); border: 1px solid var(--rule); border-radius: var(--radius); padding: 0.9rem 1.3rem; }
  li.planned { background: transparent; border-style: dashed; }
  h2 { margin: 0; font-size: 1.1rem; }
  li p { margin: 0.25rem 0 0; color: var(--ink-soft); max-width: 60ch; }
  .comp b { color: var(--ink); font-weight: 600; }
  .chip { align-self: flex-start; font-size: 0.9rem; font-weight: 600; padding: 0.2rem 0.8rem; border-radius: 99px; background: var(--surface-sunk); color: var(--ink-soft); white-space: nowrap; }
  .chip.audit { background: var(--expiry-fill); color: #1a1000; }
  .chip.enforce { background: var(--credential); color: #fff; }
  :global(:root[data-theme="dark"]) .chip.enforce { color: #07121c; }
  .error { margin: 0; color: var(--deny); background: var(--deny-wash); padding: 0.5rem 0.9rem; border-radius: 10px; }
  code { font-family: var(--font-data); font-size: 0.9em; }
</style>
