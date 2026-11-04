# Turn on the secrets layer

We replace the clinic's one shared database password with credentials that last two minutes. First we watch an attacker use the old password. Then we switch the layer on and watch the same attack fail while the clinic keeps working. By the end you will know what the layer changes, what it leaves alone, and how to read a credential's life in the dashboard.

You need the clinic deployed (`make clinic`), Vault installed (`make vault`), the observer running (`make observer`) and the clinic page forwarded to your machine (`make web`). The dashboard (`cd web && npm run dev`) has a **Secrets** view and a **Layers** view. Every step also works with `curl`, and we show that.

Vault runs in dev mode here: it keeps everything in memory, uses a fixed root token, and forgets all of it when its pod restarts. That is fine for a laptop and wrong for anything else. If it restarts, run `make vault` again.

## Start with everything off

```console
$ make attack A=read-postgres
read-postgres: SUCCEEDS   [identity=off, mtls=off, secrets=off, network=off]
expected succeeds: as expected
{
  "rows": 5,
  "sample": "Aisha Rahman"
}
```

The attacker pod holds the clinic's shared database password, the same one `records-api` uses. It never changes and it works from anywhere, so the attacker read every patient.

## Audit: credentials from Vault, old password still valid

Open **Layers** and set **Short-lived secrets** to **Audit**, or run:

```console
$ curl -s -X PUT localhost:8765/layers/secrets -H 'content-type: application/json' -d '{"mode":"audit"}'
{"identity":"off","mtls":"off","secrets":"audit","network":"off"}
```

`records-api` now logs in to Vault with its SPIFFE identity, asks for a database user, and uses that user instead of the shared password. Open the clinic page, or run:

```console
$ curl -s -o /dev/null -w "%{http_code}\n" localhost:8081/api/patients
200
```

Open the **Secrets** view. A row appears for `records-api` with a countdown from 120 seconds. Vault records each credential it hands out, and the observer turns that record into an event:

```console
$ curl -s 'localhost:8765/events?follow=false' | grep '^data:' | grep credential_issued | tail -1 | sed 's/^data: //'
{"v": 1, "ts": 1793767120.323044, "layer": "secrets", "kind": "credential_issued", "verdict": "allow", "src": "records-api", "dst": "postgres", "reason": "records-api was issued a 120 second records-api database credential", "trace": null, "evidence": {"role": "records-api", "ttl_s": 120, "serial": "database/creds/records-api/EDocssGbn8xhR81Z47NpqT9E"}, "id": 16376}
```

The audit log hashes the username and password, so the event names who asked and which lease they got, not the credential itself. Audit mode changes nothing for the attacker. The shared password still works:

```console
$ make attack A=read-postgres
read-postgres: SUCCEEDS   [identity=off, mtls=off, secrets=audit, network=off]
expected succeeds: as expected
```

## Enforce: the old password is revoked

Set **Short-lived secrets** to **Enforce**, or run:

```console
$ curl -s -X PUT localhost:8765/layers/secrets -H 'content-type: application/json' -d '{"mode":"enforce"}'
{"identity":"off","mtls":"off","secrets":"enforce","network":"off"}
```

The controller waits a few seconds so that `records-api` is already on Vault credentials, then changes the shared password to a random one that nobody knows. Run the attack again:

```console
$ make attack A=read-postgres
read-postgres: BLOCKED   [identity=off, mtls=off, secrets=enforce, network=off]
expected blocked: as expected
stopped by: secrets (inferred)
{
  "error": "OperationalError",
  "detail": "connection failed: connection to server at \"10.43.167.251\", port 5432 failed: FATAL:  password authentication failed for user \"clinic\"",
  "phase": "auth"
}
```

Postgres turned the old password away. The same goes for an attacker with code execution inside a clinic pod:

```console
$ make attack A=postgres-from-billing
postgres-from-billing: BLOCKED   [identity=off, mtls=off, secrets=enforce, network=off]
expected blocked: as expected
stopped by: secrets (inferred)
```

The clinic itself did not notice:

```console
$ curl -s -o /dev/null -w "%{http_code}\n" localhost:8081/api/patients
200
```

Two things to read here. The attack runner records the `phase` that failed, and `auth` means the server answered and refused the password. And `stopped by` says `(inferred)`. Nothing in the failure proves the revoked password is the cause, so the observer names the secrets layer because the layer is enforced and a password was refused. A mistyped password would be reported the same way. The attacks here use the real leaked password, so the guess is right.

## What the layer does not cover

A password that leaks today is still good for up to two minutes. The layer shrinks the window, it does not close it. It also does nothing about the network: with `secrets=enforce` and `network=off`, the attacker can still open a connection to Postgres. It just cannot log in. [Turn on the network layer](the-network-layer.md) stops the connection itself, and the two layers together stop the attack twice.

Leaving the layer is safe too. Set it back to **Off** and the controller restores the shared password before the services return to it.

## A second path: static secrets with External Secrets

Some secrets do not change every two minutes, like an API key for another service. For those the playground uses the External Secrets Operator, which copies one value out of Vault into a Kubernetes Secret. Install it:

```console
$ make eso
```

Look at what it created:

```console
$ kubectl --context k3d-ztp -n clinic get externalsecret billing-api-key
NAME              STORETYPE     STORE   REFRESH INTERVAL   STATUS         READY   LAST SYNC
billing-api-key   SecretStore   vault   15s                SecretSynced   True    8s
$ kubectl --context k3d-ztp -n clinic get secret billing-api-key -o jsonpath='{.data.value}' | base64 -d
placeholder-api-key
```

Change the value in Vault and wait for the next refresh:

```console
$ kubectl --context k3d-ztp -n vault exec deploy/vault -- env VAULT_ADDR=http://127.0.0.1:8200 VAULT_TOKEN=playground-dev-root vault kv put secret/clinic/billing-api-key value=rotated-api-key
=========== Secret Path ===========
secret/data/clinic/billing-api-key

======= Metadata =======
Key                Value
---                -----
created_time       2026-11-04T04:42:59.838272998Z
custom_metadata    <nil>
deletion_time      n/a
destroyed          false
version            2
$ sleep 20; kubectl --context k3d-ztp -n clinic get secret billing-api-key -o jsonpath='{.data.value}' | base64 -d
rotated-api-key
```

The value is a placeholder, and the Kubernetes Secret is only as private as your cluster's RBAC. This path shows the mechanism. The dynamic credentials above are the part that removes a standing secret.

Next, [break the secrets layer](how-to/break-the-secrets-layer.md).
