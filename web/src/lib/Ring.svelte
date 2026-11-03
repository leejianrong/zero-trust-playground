<script lang="ts">
  let { fraction, seconds, state }: { fraction: number; seconds: number; state: "valid" | "low" | "expired" } = $props();
  const R = 52;
  const C = 2 * Math.PI * R;
  const label = $derived(state === "expired" ? "expired" : `${seconds} seconds left`);
</script>

<figure class="ring {state}" aria-label={label}>
  <svg viewBox="0 0 120 120" aria-hidden="true">
    <circle class="track" cx="60" cy="60" r={R} />
    <circle class="arc" cx="60" cy="60" r={R} stroke-dasharray={C} stroke-dashoffset={C * (1 - fraction)} />
  </svg>
  <figcaption>
    {#if state === "expired"}
      <span class="big">0s</span><span class="sub">expired</span>
    {:else}
      <span class="big data">{seconds}s</span><span class="sub">left</span>
    {/if}
  </figcaption>
</figure>

<style>
  .ring { position: relative; margin: 0; width: 132px; height: 132px; flex: none; }
  svg { width: 100%; height: 100%; transform: rotate(-90deg); }
  circle { fill: none; stroke-width: 9; }
  .track { stroke: var(--surface-sunk); }
  .arc { stroke: var(--credential); stroke-linecap: round; transition: stroke-dashoffset 0.9s linear, stroke 0.3s; }
  .low .arc { stroke: var(--expiry-fill); }
  .expired .arc { stroke: var(--deny); }
  figcaption { position: absolute; inset: 0; display: grid; place-content: center; text-align: center; }
  .big { font-size: 1.6rem; font-weight: 700; line-height: 1; }
  .sub { font-size: 0.75rem; color: var(--ink-soft); margin-top: 0.2rem; }
  .low .big { color: var(--expiry); }
  .expired .big { color: var(--deny); }
</style>
