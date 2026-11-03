<script lang="ts">
  import { matchesExpectation, type Attack, type Results } from "./attacks";

  let { attacks, results }: { attacks: Attack[]; results: Results } = $props();
  let running = $state<string | null>(null);
  let error = $state("");

  async function run(name: string) {
    running = name;
    error = "";
    try {
      const r = await fetch(`/attacks/${name}/run`, { method: "POST" });
      if (!r.ok) error = (await r.json()).detail ?? "The attack didn't run.";
    } catch {
      error = "The observer isn't reachable.";
    }
    running = null;
  }
</script>

<section>
  {#if error}<p class="error" role="alert">{error}</p>{/if}
  <ul>
    {#each attacks as a (a.name)}
      {@const r = results[a.name]}
      <li>
        <div class="text">
          <h2>{a.title}</h2>
          <p>{a.description}</p>
          <p class="meta">Target: <span class="data">{a.target}</span> · Expected with no layers: <b>{a.expected.all_off === "succeeds" ? "succeeds" : "blocked"}</b></p>
        </div>
        <div class="side">
          <button onclick={() => run(a.name)} disabled={running !== null} aria-label="Run attack: {a.title}">
            {running === a.name ? "Running…" : "Run attack"}
          </button>
          {#if r}
            <span class="chip {r.outcome}">
              <span aria-hidden="true">{r.outcome === "succeeds" ? "⚠" : "✓"}</span>
              {r.outcome === "succeeds" ? "Succeeded, nothing stopped it" : "Blocked"}
            </span>
            <span class="match">{matchesExpectation(r) ? "As expected" : "Not what the catalogue expects"}</span>
          {:else}
            <span class="chip none">Not run yet</span>
          {/if}
        </div>
      </li>
    {/each}
  </ul>
</section>

<style>
  section { display: grid; gap: 1rem; }
  .error { margin: 0; color: var(--deny); background: var(--deny-wash); padding: 0.5rem 0.9rem; border-radius: 10px; }
  ul { list-style: none; margin: 0; padding: 0; display: grid; gap: 0.9rem; }
  li { display: flex; justify-content: space-between; gap: 1.5rem; flex-wrap: wrap; background: var(--surface); border: 1px solid var(--rule); border-radius: var(--radius); padding: 1.1rem 1.4rem; }
  .text { flex: 1; min-width: 260px; }
  h2 { margin: 0; font-size: 1.2rem; }
  .text p { margin: 0.3rem 0 0; color: var(--ink-soft); }
  .meta { font-size: 0.9rem; }
  .side { display: grid; gap: 0.5rem; justify-items: start; align-content: start; min-width: 230px; }
  button { font: inherit; font-weight: 600; color: var(--ink); background: var(--surface-sunk); border: 1px solid var(--rule); border-radius: 99px; padding: 0.4rem 1.1rem; cursor: pointer; }
  button:hover:not(:disabled) { border-color: var(--credential); }
  button:disabled { opacity: 0.6; cursor: progress; }
  .chip { font-size: 0.9rem; font-weight: 600; padding: 0.2rem 0.7rem; border-radius: 99px; }
  .chip.succeeds { color: var(--expiry); background: color-mix(in srgb, var(--expiry-fill) 18%, var(--surface)); }
  .chip.blocked { color: var(--ok); background: var(--credential-wash); }
  .chip.none { color: var(--ink-soft); background: var(--surface-sunk); font-weight: 400; }
  .match { font-size: 0.85rem; color: var(--ink-soft); }
</style>
