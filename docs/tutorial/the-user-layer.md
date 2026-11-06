# Turn on the user layer

Until now the clinic asked which service was calling. It never asked which person was behind the call. We add that question: a person signs in, `records-api` checks who they are, and what they may do depends on their role. First we watch an attacker get patient records with a made-up identity. Then we switch the layer on and watch the same attacks fail, and we sign in as two different people to see them get different answers.

You need the clinic deployed (`make clinic`), Keycloak installed (`make keycloak`), the observer running (`make observer`), and two port-forwards: the clinic page (`make web`) and Keycloak (`make keycloak-ui`). Your browser has to reach Keycloak to sign in, so the second one is not optional. The dashboard (`cd web && npm run dev`) has a **Users** view and a **Layers** view. Every step also works with `curl`, and we show that.

Keycloak runs in dev mode here: it keeps everything in memory, uses a fixed admin password (`admin` / `playground-dev-admin`), and forgets the whole realm when its pod restarts. That is fine for a laptop and wrong for anything else. If it restarts, run `make keycloak` again. It needs about 0.7 GB of memory, so the whole cluster with Vault and Keycloak runs at about 2.4 GiB.

## Who is in the clinic

`make keycloak` creates one realm, `clinic`, with two roles and two people:

| Person | Password | Role | May |
|---|---|---|---|
| `aisha` | `playground-aisha` | `clinician` | read and write patients |
| `bob` | `playground-bob` | `receptionist` | read patients only |

The clinic page signs people in through Keycloak. `records-api` is the only service that decides what they may do. `billing` and `records-mcp` pass the person's token along and decide nothing.

## Start with everything off

```console
$ make attack A=no-identity-records
no-identity-records: SUCCEEDS   [identity=off, mtls=off, secrets=off, user=off, network=off]
expected succeeds: as expected
{
  "status": 200,
  "items": 5
}
```

The attacker has no token and gets every patient. Now the same call with a claim of identity, written in a header with nothing to back it:

```console
$ make attack A=forged-user-header
forged-user-header: SUCCEEDS   [identity=off, mtls=off, secrets=off, user=off, network=off]
expected succeeds: as expected
{
  "claimed": "aisha",
  "status": 200,
  "items": 5
}
```

With the layer off, `records-api` believes the `X-User` header and logs who it claimed to be. A header is only a string, so anyone can write it. And one more: a real token, but one that was issued for a different service.

```console
$ make attack A=wrong-audience-token
wrong-audience-token: SUCCEEDS   [identity=off, mtls=off, secrets=off, user=off, network=off]
expected succeeds: as expected
{
  "status": 200,
  "items": 5
}
```

The attacker signed in as a real user through a client called `attacker-cli`. That client is deliberately weak: it accepts a password directly, and it exists only so this attack can hold a genuine token. The token says it is for `billing`.

## Audit: see what would be refused

Open **Layers** and set **User identity** to **Audit**, or run:

```console
$ curl -s -X PUT localhost:8765/layers/user -H 'content-type: application/json' -d '{"mode":"audit"}'
{"identity":"off","mtls":"off","secrets":"off","user":"audit","network":"off"}
```

Run the wrong-audience attack again:

```console
$ make attack A=wrong-audience-token
wrong-audience-token: SUCCEEDS   [identity=off, mtls=off, secrets=off, user=audit, network=off]
expected succeeds: as expected
{
  "status": 200,
  "items": 5
}
```

Nothing changed for the attacker. What changed is the record. `records-api` checked the token, found it was not for `records-api`, and wrote down that it would have refused:

```console
$ curl -s 'localhost:8765/events?follow=false' | grep '^data:' | grep would_deny | tail -1 | sed 's/^data: //'
{"v": 1, "ts": 1793930431.8424637, "layer": "user", "kind": "user_authorisation", "verdict": "info", "src": "anonymous", "dst": "records-api", "reason": "the token is not for records-api: wrong audience", "trace": "25dde478a9ac", "evidence": {"mode": "audit", "decision": "would_deny", "method": "GET", "route": "/patients", "subject": null, "roles": [], "client": null, "audience": []}, "id": 19206}
```

Two things to notice. The verdict is `info`, because audit lets the request through. And `src` says `anonymous` although the token belonged to a real person: the check stops at the audience and does not read the rest of the token, so the event does not name them yet.

## Enforce: no identity, no records

Set **User identity** to **Enforce**, or run:

```console
$ curl -s -X PUT localhost:8765/layers/user -H 'content-type: application/json' -d '{"mode":"enforce"}'
{"identity":"off","mtls":"off","secrets":"off","user":"enforce","network":"off"}
```

Run the attacks again:

```console
$ make attack A=no-identity-records
no-identity-records: BLOCKED   [identity=off, mtls=off, secrets=off, user=enforce, network=off]
expected blocked: as expected
stopped by: user
{
  "error": "HTTPStatusError",
  "detail": "Client error '401 Unauthorized' for url 'http://records-api.clinic.svc:8080/patients'\nFor more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401",
  "phase": "request"
}
```

The forged header and the wrong-audience token end the same way: `BLOCKED`, `stopped by: user`, and a 401. The header is no longer believed, and a token meant for `billing` is not accepted by `records-api`. The MCP route is closed too, and its error carries the reason:

```console
$ make attack A=mcp-no-identity
mcp-no-identity: BLOCKED   [identity=off, mtls=off, secrets=off, user=enforce, network=off]
expected blocked: as expected
stopped by: user
{
  "error": "RuntimeError",
  "detail": "Error executing tool list_patients: records-api answered 401. user layer: no token: this request has no bearer token",
  "phase": "request"
}
```

`records-api` records every refusal, with the layer that made it:

```console
$ curl -s 'localhost:8765/events?follow=false' | grep '^data:' | grep user_authorisation | grep '"deny"' | tail -1 | sed 's/^data: //'
{"v": 1, "ts": 1793930745.2126648, "layer": "user", "kind": "user_authorisation", "verdict": "deny", "src": "anonymous", "dst": "records-api", "reason": "no token: this request has no bearer token", "trace": "3c0c0e693cb4", "evidence": {"mode": "enforce", "decision": "deny", "method": "GET", "route": "/patients", "subject": null, "roles": [], "client": null, "audience": []}, "id": 19366}
```

One attack is not stopped, and it should not be:

```console
$ make attack A=cross-namespace-billing
cross-namespace-billing: SUCCEEDS   [identity=off, mtls=off, secrets=off, user=enforce, network=off]
expected succeeds: as expected
{
  "status": 200,
  "items": 5
}
```

`billing` decides nothing about people. It never asked who the caller was, so a request from another namespace still works. The mTLS and network layers are what stop that one. This is why the playground has layers: each one covers a gap in the others.

## Sign in as two different people

Open <http://localhost:8081>. With the layer enforced and nobody signed in, the list cannot load. The page shows the refusal: `Refused by the user layer: no token: this request has no bearer token`. Choose **Sign in**. Keycloak shows a login form. Sign in as `aisha` with `playground-aisha`.

You land back on the clinic page, and the top reads **Signed in as aisha (clinician)**. Add a patient: it works, because a clinician may write.

Choose **Sign out**, then sign in as `bob` with `playground-bob`. The top now reads **Signed in as bob (receptionist)**. The list of patients loads. Now try to add a patient. The page says:

```text
Refused by the user layer: bob has receptionist, which does not allow write
```

Bob can see patients and cannot change them. Both answers came from `records-api`, which read the role out of a token that Keycloak signed. The sign-in is a standard authorization code flow with PKCE, so the page never sees the password and never handles a token. The server keeps the token and the browser holds only a cookie that scripts cannot read.

Look at the **Users** view in the dashboard. It lists the people who have signed in, the requests `records-api` checked for them, and failed sign-ins. Try a wrong password for `bob` and you get a row under **Failed sign-ins**. The same record is in the stream:

```console
$ curl -s 'localhost:8765/events?follow=false' | grep '^data:' | grep user_login_failed | tail -1 | sed 's/^data: //'
{"v": 1, "ts": 1793930492.783, "layer": "user", "kind": "user_login_failed", "verdict": "deny", "src": "bob", "dst": "web", "reason": "bob could not sign in to web: invalid_user_credentials", "trace": null, "evidence": {"serial": "keycloak/2026-11-06 02:01:32,783/LOGIN_ERROR/c9f439c0-d1a8-43f0-8972-f13d22d0be6f/", "client": "web", "user_id": "c9f439c0-d1a8-43f0-8972-f13d22d0be6f", "error": "invalid_user_credentials"}, "id": 19269}
```

Keycloak wrote that line to its own log. The observer reads the log the way it reads Vault's audit log.

## What the layer does not cover

The layer answers one question: is this person allowed to do this? It does not tell you whether the request itself is safe. The `agent-prompt-injection` attack is also blocked above, but only because the simulated attacker has no account, so it cannot plant its text. A signed-in clinician who plants the text still gets it obeyed, because the agent passes that clinician's token along unchanged. [Break the user layer](how-to/break-the-user-layer.md) shows this, and the agent identity work in a later slice is meant to close it.

It also does nothing for a person who is who they say they are and does the wrong thing. And a stolen token works until it expires, as a leaked password did in the [secrets layer](the-secrets-layer.md).

Set the layer back to **Off** when you are done:

```console
$ curl -s -X PUT localhost:8765/layers/user -H 'content-type: application/json' -d '{"mode":"off"}'
{"identity":"off","mtls":"off","secrets":"off","user":"off","network":"off"}
```

Next, [break the user layer](how-to/break-the-user-layer.md).
