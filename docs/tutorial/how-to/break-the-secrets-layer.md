# Break the secrets layer

Run these with the secrets layer enforced and the other layers off. Each one shows a way the layer can fail and what you see when it does. Set it up from the Layers view or:

```console
$ curl -s -X PUT localhost:8765/layers/secrets -H 'content-type: application/json' -d '{"mode":"enforce"}'
{"identity":"off","mtls":"off","secrets":"enforce","user":"off","network":"off"}
```

Keep the clinic page open through `make web` and the **Secrets** view open in the dashboard. Vault must be installed (`make vault`).

## Ask for a credential as the wrong service

Every service logs in to Vault with its own SPIFFE identity, and each Vault role accepts only that identity. Run this from the `billing` pod. It logs in as `billing` and tries two things: the `records-api` role, and a `records-api` database credential:

```console
$ kubectl --context k3d-ztp -n clinic exec -i deploy/billing -- python - <<'EOF'
import json, urllib.request, urllib.error
from spiffe import WorkloadApiClient
def vault(path, body=None, token=None):
    req = urllib.request.Request("http://vault.vault.svc:8200/v1/" + path, data=json.dumps(body).encode() if body else None,
                                 headers={"X-Vault-Token": token} if token else {}, method="PUT" if body else "GET")
    return json.load(urllib.request.urlopen(req, timeout=5))
with WorkloadApiClient(socket_path="unix:///spiffe-workload-api/spire-agent.sock") as c:
    jwt = c.fetch_jwt_svid(audience={"vault"}).token
try:
    vault("auth/jwt/login", {"role": "records-api", "jwt": jwt})
except urllib.error.HTTPError as e:
    print(e.code, json.load(e)["errors"])
token = vault("auth/jwt/login", {"role": "billing", "jwt": jwt})["auth"]["client_token"]
try:
    vault("database/creds/records-api", token=token)
except urllib.error.HTTPError as e:
    print(e.code, json.load(e)["errors"])
EOF
400 ['error validating token: invalid subject (sub) claim']
403 ['1 error occurred:\n\t* permission denied\n\n']
```

Two refusals, at two different points. Vault will not even log `billing` in to the `records-api` role, because the identity in its token does not match the role. And `billing`'s own role has no permission to read database credentials. The second refusal is recorded, and the **Secrets** view shows it under **Refused**:

```console
$ curl -s 'localhost:8765/events?follow=false' | grep '^data:' | grep credential_denied | tail -1 | sed 's/^data: //'
{"v": 1, "ts": 1793767201.414629, "layer": "secrets", "kind": "credential_denied", "verdict": "deny", "src": "billing", "dst": "postgres", "reason": "billing was refused a records-api database credential: permission denied", "trace": null, "evidence": {"role": "records-api"}, "id": 16397}
```

## Stop Vault and predict what breaks

With the layer enforced, `records-api` depends on Vault. Before you stop it, write down two things: whether the clinic page keeps working right away, and when it stops. Then:

```console
$ kubectl --context k3d-ztp -n vault scale deploy/vault --replicas=0
deployment.apps/vault scaled
```

Request the patient list every 10 seconds, and stop at the first failure:

```console
$ for i in $(seq 1 14); do code=$(curl -s -o /dev/null -w "%{http_code}" localhost:8081/api/patients); echo $code; [ "$code" != 200 ] && break; sleep 10; done
200
200
200
200
200
200
200
200
200
503
```

It keeps working for about 90 seconds. `records-api` holds the credential it already has and asks for a new one when 30 seconds are left. Vault is gone, so the renewal fails. Read the failure:

```console
$ curl -s localhost:8081/api/patients
{"detail":"could not get a database credential from Vault: ConnectError"}
```

The reason is in the answer. A service that cannot get a credential says so and does not hang. Even so, the clinic is down because its one source of credentials is. Turning the layer on moved the risk from a password that might leak to a service that must stay up.

Bring Vault back. It forgot everything when it stopped, so `make vault` configures it again:

```console
$ make vault
vault configured: jwt auth trusts https://oidc-discovery.playground.local, roles: web records-api billing records-mcp, database credentials for records-api
$ curl -s -o /dev/null -w "%{http_code}\n" localhost:8081/api/patients
200
```

## Revoke a credential before it expires

A leaked credential is good until it expires, but you do not have to wait. Ask Vault for a credential and keep the lease it comes with:

```console
$ V="kubectl --context k3d-ztp -n vault exec deploy/vault -- env VAULT_ADDR=http://127.0.0.1:8200 VAULT_TOKEN=playground-dev-root vault"
$ CRED=$($V read -format=json database/creds/records-api)
$ DBUSER=$(echo "$CRED" | jq -r .data.username); DBPASS=$(echo "$CRED" | jq -r .data.password); LEASE=$(echo "$CRED" | jq -r .lease_id)
```

Use it from inside the Postgres pod:

```console
$ kubectl --context k3d-ztp -n clinic exec deploy/postgres -- env PGPASSWORD="$DBPASS" psql -h postgres.clinic.svc -U "$DBUSER" -d clinic -Atc "select count(*) from patients"
5
```

Now revoke the lease and try again:

```console
$ $V lease revoke "$LEASE"
All revocation operations queued successfully!
$ kubectl --context k3d-ztp -n clinic exec deploy/postgres -- env PGPASSWORD="$DBPASS" psql -h postgres.clinic.svc -U "$DBUSER" -d clinic -Atc "select count(*) from patients"
psql: error: connection to server at "postgres.clinic.svc" (10.43.167.251), port 5432 failed: FATAL:  password authentication failed for user "v-token-records--Gou7TNKoKS4n88V4kafH-1793767334"
```

The credential died the moment it was revoked. The shared password could not do that: it was one secret for everyone, so revoking it meant breaking the clinic. Here each credential belongs to one holder, so you can end one without touching the others.

One thing the layer cannot do is close a connection that is already open. When a credential expires, Vault revokes what the user may do, so an open connection stays up but every query fails with `permission denied`. A client that holds connections has to expect that and ask for a new credential.

## Put everything back

```console
$ curl -s -X PUT localhost:8765/layers/secrets -H 'content-type: application/json' -d '{"mode":"off"}'
{"identity":"off","mtls":"off","secrets":"off","user":"off","network":"off"}
```
