<script lang="ts">
  import { isExpired, secondsLeft, type Credentials } from "./secrets";

  let { creds, now }: { creds: Credentials; now: number } = $props();
  const clock = (ms: number) => new Date(ms).toLocaleTimeString([], { hour12: false });
</script>

<section>
  {#if creds.live.length === 0 && creds.refused.length === 0}
    <div class="empty">
      <h2>No credentials yet</h2>
      <p>Run <code>make vault</code>, turn the Short-lived secrets layer to Audit or Enforce on the Layers view, then open the clinic page. A row appears when <code>records-api</code> is issued a database user.</p>
    </div>
  {:else}
    <table>
      <caption>Database credentials issued by Vault. Each lasts two minutes, and the service asks for a new one before it runs out.</caption>
      <thead><tr><th>Holder</th><th>Credential</th><th>Issued</th><th>Time left</th></tr></thead>
      <tbody>
        {#each creds.live as c (c.lease)}
          {@const expired = isExpired(c, now)}
          <tr class:expired>
            <td>{c.holder}</td>
            <td class="data">Postgres user, role {c.role}</td>
            <td class="data">{clock(c.issuedAt)}</td>
            <td class="data" aria-label={expired ? "expired" : `${secondsLeft(c, now)} seconds left`}>{expired ? "expired" : `${secondsLeft(c, now)}s`}</td>
          </tr>
        {/each}
      </tbody>
    </table>
    {#if creds.refused.length}
      <h2>Refused</h2>
      <ul class="refused">
        {#each creds.refused as r (r.id)}
          <li><b>{r.holder}</b> <span class="data">{clock(r.at)}</span> {r.reason}</li>
        {/each}
      </ul>
    {/if}
  {/if}
</section>

<style>
  section { display: grid; gap: 1rem; }
  table { width: 100%; border-collapse: collapse; background: var(--surface); border: 1px solid var(--rule); border-radius: var(--radius); }
  caption { text-align: left; color: var(--ink-soft); padding: 0 0 0.6rem; }
  th, td { text-align: left; padding: 0.6rem 1rem; border-bottom: 1px solid var(--rule); }
  th { color: var(--ink-soft); font-weight: 600; }
  tr.expired td { color: var(--ink-soft); text-decoration: line-through; }
  tr.expired td:last-child { text-decoration: none; }
  .refused { list-style: none; margin: 0; padding: 0; display: grid; gap: 0.4rem; }
  .empty { background: var(--surface); border: 1px solid var(--rule); border-radius: var(--radius); padding: 1.25rem 1.4rem; }
  h2 { margin: 0 0 0.4rem; font-size: 1.05rem; }
</style>
