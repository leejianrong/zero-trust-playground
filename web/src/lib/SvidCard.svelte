<script lang="ts">
  import { isExpired, lifeLeft, parseSpiffeId, secondsLeft, type Card } from "./identity";
  import Ring from "./Ring.svelte";

  let { card, now }: { card: Card; now: number } = $props();
  const current = $derived(card.history[0]);
  const id = $derived(parseSpiffeId(card.spiffeId));
  const expired = $derived(isExpired(current, now));
  const fraction = $derived(lifeLeft(current, now));
  const state = $derived(expired ? "expired" : fraction < 0.25 ? "low" : "valid");
  const clock = (ms: number) => new Date(ms).toLocaleTimeString([], { hour12: false });
  const gap = (i: number) =>
    i + 1 < card.history.length ? `${Math.round((card.history[i].notBefore - card.history[i + 1].notBefore) / 1000)}s after previous` : "first seen";
</script>

<article class="card" class:stale={expired}>
  <header>
    <h2>{card.workload}</h2>
    {#if card.registrationRemoved}
      <span class="badge deny"><span aria-hidden="true">✕</span> Registration removed</span>
    {:else if expired}
      <span class="badge deny"><span aria-hidden="true">✕</span> Identity expired</span>
    {:else}
      <span class="badge ok"><span aria-hidden="true">✓</span> Identity valid</span>
    {/if}
  </header>

  <div class="body">
    {#key current.serial}
      <div class="pulse"><Ring {fraction} seconds={secondsLeft(current, now)} {state} /></div>
    {/key}
    <div class="facts">
      <p class="spiffe data" aria-label="SPIFFE ID {card.spiffeId}">
        <span class="scheme">spiffe://</span><span class="td">{id?.trustDomain ?? card.spiffeId}</span>{#if id}<span class="seg">/ns/<b>{id.namespace}</b></span><span class="seg">/sa/<b>{id.serviceAccount}</b></span>{/if}
      </p>
      <dl>
        <div><dt>Serial</dt><dd class="data" title={current.serial}>{current.serial.slice(0, 12)}…</dd></div>
        <div><dt>Issued</dt><dd class="data">{clock(current.notBefore)}</dd></div>
        <div><dt>Expires</dt><dd class="data">{clock(current.notAfter)}</dd></div>
      </dl>
    </div>
  </div>

  <details open>
    <summary>Rotation history <span class="count">{card.history.length}</span></summary>
    <ol>
      {#each card.history as svid, i (svid.serial)}
        <li class:now={i === 0}>
          <span class="data">{svid.serial.slice(0, 8)}</span>
          <span class="data">{clock(svid.notBefore)}</span>
          <span class="gap">{i === 0 ? "current · " : ""}{gap(i)}</span>
        </li>
      {/each}
    </ol>
  </details>
</article>

<style>
  .card { background: var(--surface); border: 1px solid var(--rule); border-radius: var(--radius); padding: 1.25rem 1.5rem; display: grid; gap: 1rem; }
  .card.stale { border-color: var(--deny); }
  header { display: flex; justify-content: space-between; align-items: center; gap: 1rem; flex-wrap: wrap; }
  h2 { margin: 0; font-size: 1.35rem; font-weight: 700; letter-spacing: -0.01em; }
  .badge { font-size: 0.85rem; font-weight: 600; padding: 0.2rem 0.7rem; border-radius: 99px; }
  .badge.ok { color: var(--ok); background: var(--credential-wash); }
  .badge.deny { color: var(--deny); background: var(--deny-wash); }
  .body { display: flex; gap: 1.5rem; align-items: center; flex-wrap: wrap; }
  .pulse { animation: pulse 0.9s ease-out; border-radius: 50%; }
  @keyframes pulse { 0% { box-shadow: 0 0 0 0 var(--credential); } 100% { box-shadow: 0 0 0 18px transparent; } }
  .facts { flex: 1; min-width: 260px; display: grid; gap: 0.9rem; }
  .spiffe { margin: 0; color: var(--ink-soft); word-break: break-all; }
  .scheme { opacity: 0.6; }
  .td { color: var(--credential); font-weight: 600; }
  .seg b { color: var(--ink); }
  dl { margin: 0; display: flex; gap: 2rem; flex-wrap: wrap; }
  dt { font-size: 0.8rem; color: var(--ink-soft); }
  dd { margin: 0; }
  details { border-top: 1px solid var(--rule); padding-top: 0.75rem; }
  summary { cursor: pointer; font-weight: 600; }
  .count { color: var(--ink-soft); font-weight: 400; margin-left: 0.4rem; }
  ol { list-style: none; margin: 0.6rem 0 0; padding: 0; display: grid; gap: 0.25rem; }
  li { display: grid; grid-template-columns: 7rem 7rem 1fr; gap: 0.5rem; color: var(--ink-soft); }
  li.now { color: var(--ink); }
  .gap { font-size: 0.85rem; }
</style>
