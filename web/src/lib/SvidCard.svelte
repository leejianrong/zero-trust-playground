<script lang="ts">
  import { isExpired, lifeLeft, parseSpiffeId, secondsLeft, type Card } from "./identity";
  import Ring from "./Ring.svelte";

  let { card, now }: { card: Card; now: number } = $props();
  let dialog: HTMLDialogElement;
  const current = $derived(card.history[0]);
  const id = $derived(parseSpiffeId(card.spiffeId));
  const expired = $derived(isExpired(current, now));
  const fraction = $derived(lifeLeft(current, now));
  const state = $derived(expired ? "expired" : fraction < 0.25 ? "low" : "valid");
  const status = $derived(
    card.registrationRemoved ? "Registration removed" : expired ? "Identity expired" : "Identity valid",
  );
  const bad = $derived(card.registrationRemoved || expired);
  const clock = (ms: number) => new Date(ms).toLocaleTimeString([], { hour12: false });
  const gap = (i: number) =>
    i + 1 < card.history.length ? `${Math.round((card.history[i].notBefore - card.history[i + 1].notBefore) / 1000)}s after previous` : "first seen";
</script>

<article class="card" class:stale={bad}>
  <button class="face" onclick={() => dialog.showModal()} aria-haspopup="dialog">
    <span class="top">
      <h2>{card.workload}</h2>
      <span class="mark" class:bad role="img" aria-label={status} title={status}>{bad ? "✕" : "✓"}</span>
    </span>
    {#key current.serial}
      <span class="pulse"><Ring {fraction} seconds={secondsLeft(current, now)} {state} /></span>
    {/key}
    <span class="ns data">{id?.namespace ?? ""}</span>
  </button>

  <dialog bind:this={dialog} aria-label="{card.workload} identity" onclick={(e) => e.target === dialog && dialog.close()}>
    <header>
      <h2>{card.workload}</h2>
      <button class="close" onclick={() => dialog.close()} aria-label="Close">✕</button>
    </header>
    <p class="status" class:bad>{bad ? "✕" : "✓"} {status}</p>
    <p class="spiffe data" aria-label="SPIFFE ID {card.spiffeId}">
      <span class="scheme">spiffe://</span><span class="td">{id?.trustDomain ?? card.spiffeId}</span>{#if id}<span class="seg">/ns/<b>{id.namespace}</b></span><span class="seg">/sa/<b>{id.serviceAccount}</b></span>{/if}
    </p>
    <dl>
      <div><dt>Serial</dt><dd class="data" title={current.serial}>{current.serial.slice(0, 12)}…</dd></div>
      <div><dt>Issued</dt><dd class="data">{clock(current.notBefore)}</dd></div>
      <div><dt>Expires</dt><dd class="data">{clock(current.notAfter)}</dd></div>
      <div><dt>Left</dt><dd class="data">{expired ? "expired" : `${secondsLeft(current, now)}s`}</dd></div>
    </dl>
    <h3>Rotation history <span class="count">{card.history.length}</span></h3>
    <ol>
      {#each card.history as svid, i (svid.serial)}
        <li class:now={i === 0}>
          <span class="data">{svid.serial.slice(0, 8)}</span>
          <span class="data">{clock(svid.notBefore)}</span>
          <span class="gap">{i === 0 ? "current · " : ""}{gap(i)}</span>
        </li>
      {/each}
    </ol>
  </dialog>
</article>

<style>
  .card { background: var(--surface); border: 1px solid var(--rule); border-radius: var(--radius); }
  .card:hover { border-color: var(--credential); }
  .card.stale { border-color: var(--deny); }
  .face { all: unset; box-sizing: border-box; width: 100%; padding: 0.9rem 1rem; display: grid; gap: 0.5rem; justify-items: center; cursor: pointer; border-radius: var(--radius); }
  .face:focus-visible { outline: 2px solid var(--credential); outline-offset: 2px; }
  .top { display: flex; justify-content: space-between; align-items: center; gap: 0.5rem; width: 100%; }
  h2 { margin: 0; font-size: 1rem; font-weight: 700; letter-spacing: -0.01em; overflow-wrap: anywhere; }
  .mark { flex: none; width: 1.3rem; height: 1.3rem; border-radius: 50%; display: grid; place-content: center; font-size: 0.75rem; font-weight: 700; color: var(--ok); background: var(--credential-wash); }
  .mark.bad { color: var(--deny); background: var(--deny-wash); }
  .pulse { display: block; animation: pulse 0.9s ease-out; border-radius: 50%; }
  @keyframes pulse { 0% { box-shadow: 0 0 0 0 var(--credential); } 100% { box-shadow: 0 0 0 14px transparent; } }
  .ns { font-size: 0.8rem; color: var(--ink-soft); }

  dialog { width: min(34rem, calc(100vw - 2rem)); max-height: calc(100vh - 3rem); padding: 1.25rem 1.5rem; color: var(--ink); background: var(--surface); border: 1px solid var(--rule); border-radius: var(--radius); }
  dialog::backdrop { background: rgb(0 0 0 / 0.5); }
  dialog header { display: flex; justify-content: space-between; align-items: center; }
  dialog h2 { font-size: 1.35rem; }
  .close { font: inherit; color: var(--ink-soft); background: none; border: 0; cursor: pointer; font-size: 1rem; padding: 0.25rem 0.5rem; }
  .close:hover { color: var(--ink); }
  .status { margin: 0.5rem 0 0; font-weight: 600; color: var(--ok); }
  .status.bad { color: var(--deny); }
  .spiffe { margin: 0.8rem 0 0; color: var(--ink-soft); word-break: break-all; }
  .scheme { opacity: 0.6; }
  .td { color: var(--credential); font-weight: 600; }
  .seg b { color: var(--ink); }
  dl { margin: 0.9rem 0 0; display: grid; gap: 0.35rem; }
  dl div { display: flex; justify-content: space-between; gap: 1rem; }
  dt { color: var(--ink-soft); }
  dd { margin: 0; }
  h3 { margin: 1.1rem 0 0; font-size: 0.9rem; color: var(--ink-soft); font-weight: 600; }
  .count { font-weight: 400; margin-left: 0.3rem; }
  ol { list-style: none; margin: 0.4rem 0 0; padding: 0; display: grid; gap: 0.3rem; }
  li { display: grid; grid-template-columns: 7rem 7rem 1fr; gap: 0.5rem; color: var(--ink-soft); }
  li.now { color: var(--ink); }
  .gap { font-size: 0.85rem; }
</style>
