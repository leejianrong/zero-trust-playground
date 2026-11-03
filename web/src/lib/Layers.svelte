<script lang="ts">
  import { onMount } from "svelte";
  import { fetchModes, LAYERS, MODES, setMode, type Mode, type Modes } from "./layers";

  let modes = $state<Modes>({});
  let unreachable = $state(false);
  let refusal = $state<{ layer: string; reason: string } | null>(null);

  async function refresh() {
    try {
      modes = await fetchModes();
      unreachable = false;
    } catch {
      unreachable = true;
    }
  }

  async function choose(layer: string, mode: Mode) {
    const result = await setMode(layer, mode);
    if (result.ok) {
      modes = result.modes;
      refusal = null;
    } else {
      refusal = { layer, reason: result.reason };
    }
  }

  onMount(() => {
    refresh();
    const t = setInterval(refresh, 3000);
    return () => clearInterval(t);
  });
</script>

<section>
  {#if unreachable}
    <p class="error" role="alert">The observer isn't reachable, so the modes are unknown. Start it with <code>make observer</code>.</p>
  {/if}
  <ul>
    {#each LAYERS as layer (layer.id)}
      {@const current = modes[layer.id]}
      <li>
        <div class="head">
          <div>
            <h2>{layer.name}</h2>
            <p>{layer.what}</p>
          </div>
          <div class="switch" role="radiogroup" aria-label="{layer.name} mode">
            {#each MODES as m (m.id)}
              <button role="radio" aria-checked={current === m.id} class:on={current === m.id} onclick={() => choose(layer.id, m.id)}>{m.label}</button>
            {/each}
          </div>
        </div>
        {#if current}
          <p class="now"><b>{MODES.find((m) => m.id === current)?.label}:</b> {layer.modes[current]}</p>
        {/if}
        {#if refusal?.layer === layer.id}
          <p class="error" role="alert">Not changed. {refusal.reason}.</p>
        {/if}
      </li>
    {/each}
  </ul>
  <p class="hint">A change reaches the services within a few seconds. Then run <code>make attack</code> to see the difference.</p>
</section>

<style>
  section { display: grid; gap: 1rem; }
  ul { list-style: none; margin: 0; padding: 0; display: grid; gap: 0.9rem; }
  li { background: var(--surface); border: 1px solid var(--rule); border-radius: var(--radius); padding: 1.1rem 1.4rem; display: grid; gap: 0.7rem; }
  .head { display: flex; justify-content: space-between; gap: 1.5rem; flex-wrap: wrap; align-items: flex-start; }
  h2 { margin: 0; font-size: 1.2rem; }
  .head p { margin: 0.3rem 0 0; color: var(--ink-soft); max-width: 46ch; }
  .switch { display: flex; gap: 0.15rem; background: var(--surface-sunk); border: 1px solid var(--rule); border-radius: 99px; padding: 0.2rem; }
  .switch button { font: inherit; font-weight: 600; color: var(--ink-soft); background: none; border: 0; border-radius: 99px; padding: 0.35rem 1rem; cursor: pointer; }
  .switch button:hover { color: var(--ink); }
  .switch button.on { background: var(--credential); color: #fff; }
  :global(:root[data-theme="dark"]) .switch button.on { color: #07121c; }
  .now { margin: 0; }
  .hint { margin: 0; color: var(--ink-soft); font-size: 0.9rem; }
  .error { margin: 0; color: var(--deny); background: var(--deny-wash); padding: 0.5rem 0.9rem; border-radius: 10px; }
  code { font-family: var(--font-data); font-size: 0.9em; }
</style>
