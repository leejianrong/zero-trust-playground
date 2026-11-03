<script lang="ts">
  import { onMount } from "svelte";
  import { describe, type Link } from "./links";

  let links = $state<Link[]>([]);
  let failed = $state(false);

  async function refresh() {
    try {
      links = await (await fetch("/links")).json();
      failed = false;
    } catch {
      failed = true;
    }
  }
  onMount(() => {
    refresh();
    const t = setInterval(refresh, 5000);
    return () => clearInterval(t);
  });
</script>

<section>
  {#if failed}
    <p class="error" role="alert">The observer isn't reachable, so tool status is unknown. Start it with <code>make observer</code>.</p>
  {/if}
  <ul>
    {#each links as link (link.id)}
      {@const d = describe(link)}
      <li>
        <div class="text">
          <h2>{link.name}</h2>
          <p>{link.purpose}</p>
          <p class="meta data">{link.url}</p>
          {#if !link.up}<p class="start">{d.detail}</p>{/if}
        </div>
        <div class="side">
          <span class="chip {link.up ? 'up' : 'down'}"><span aria-hidden="true">{link.up ? "✓" : "✕"}</span> {d.label}</span>
          <a class="open" class:disabled={!link.up} href={link.url} target="_blank" rel="noreferrer" aria-label="Open {link.name}">Open</a>
        </div>
      </li>
    {/each}
  </ul>
</section>

<style>
  section { display: grid; gap: 1rem; }
  ul { list-style: none; margin: 0; padding: 0; display: grid; gap: 0.9rem; }
  li { display: flex; justify-content: space-between; gap: 1.5rem; flex-wrap: wrap; background: var(--surface); border: 1px solid var(--rule); border-radius: var(--radius); padding: 1.1rem 1.4rem; }
  .text { flex: 1; min-width: 260px; }
  h2 { margin: 0; font-size: 1.2rem; }
  .text p { margin: 0.3rem 0 0; color: var(--ink-soft); }
  .meta { font-size: 0.85rem; }
  .start { color: var(--expiry); font-size: 0.9rem; }
  .side { display: grid; gap: 0.6rem; justify-items: start; align-content: start; min-width: 120px; }
  .chip { font-size: 0.9rem; font-weight: 600; padding: 0.2rem 0.7rem; border-radius: 99px; }
  .chip.up { color: var(--ok); background: var(--credential-wash); }
  .chip.down { color: var(--deny); background: var(--deny-wash); }
  .open { font-weight: 600; color: var(--ink); text-decoration: none; border: 1px solid var(--rule); background: var(--surface-sunk); border-radius: 99px; padding: 0.35rem 1.1rem; }
  .open:hover { border-color: var(--credential); }
  .open.disabled { opacity: 0.5; }
  .error { margin: 0; color: var(--deny); background: var(--deny-wash); padding: 0.5rem 0.9rem; border-radius: 10px; }
  code { font-family: var(--font-data); font-size: 0.9em; }
</style>
