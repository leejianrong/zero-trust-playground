<script lang="ts">
  import type { Users } from "./users";

  let { users }: { users: Users } = $props();
  const clock = (ms: number) => new Date(ms).toLocaleTimeString([], { hour12: false });
  const people = $derived(Object.values(users.people).sort((a, b) => a.user.localeCompare(b.user)));
  const empty = $derived(people.length === 0 && users.requests.length === 0 && users.failures.length === 0);
  const VERDICT: Record<string, string> = { allow: "Allowed", deny: "Refused", info: "Would refuse" };
</script>

<section>
  {#if empty}
    <div class="empty">
      <h2>No users yet</h2>
      <p>Run <code>make keycloak</code> and <code>make keycloak-ui</code>, then open the clinic page and choose Sign in. Turn the User identity layer to Audit or Enforce on the Layers view to see each request checked.</p>
    </div>
  {:else}
    <table>
      <caption>People Keycloak has signed in to the clinic.</caption>
      <thead><tr><th>User</th><th>Role</th><th>Status</th><th>Sign-ins</th><th>Refused</th></tr></thead>
      <tbody>
        {#each people as p (p.user)}
          <tr>
            <td>{p.user}</td>
            <td class="data">{p.roles.join(", ") || "not seen yet"}</td>
            <td>{p.signedIn ? "Signed in" : "Signed out"}</td>
            <td class="data">{p.logins}</td>
            <td class="data">{p.refused}</td>
          </tr>
        {/each}
      </tbody>
    </table>

    <h2>Requests checked by records-api</h2>
    {#if users.requests.length === 0}
      <p class="soft">Nothing yet. A request is listed here when the User identity layer is on Audit or Enforce.</p>
    {:else}
      <table>
        <thead><tr><th>Time</th><th>User</th><th>Client</th><th>Audience</th><th>Request</th><th>Result</th></tr></thead>
        <tbody>
          {#each users.requests as r (r.id)}
            <tr class:refused={r.verdict === "deny"}>
              <td class="data">{clock(r.at)}</td>
              <td>{r.user}</td>
              <td class="data">{r.client ?? "none"}</td>
              <td class="data">{r.audience.join(", ") || "none"}</td>
              <td class="data">{r.method} {r.route}</td>
              <td title={r.reason}>{VERDICT[r.verdict] ?? r.verdict}</td>
            </tr>
          {/each}
        </tbody>
      </table>
    {/if}

    {#if users.failures.length}
      <h2>Failed sign-ins</h2>
      <ul class="failures">
        {#each users.failures as f (f.id)}
          <li><span class="data">{clock(f.at)}</span> {f.reason}</li>
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
  tr.refused td:last-child { color: var(--deny); font-weight: 600; }
  .failures { list-style: none; margin: 0; padding: 0; display: grid; gap: 0.4rem; }
  .soft { margin: 0; color: var(--ink-soft); }
  .empty { background: var(--surface); border: 1px solid var(--rule); border-radius: var(--radius); padding: 1.25rem 1.4rem; }
  h2 { margin: 0 0 0.4rem; font-size: 1.05rem; }
</style>
