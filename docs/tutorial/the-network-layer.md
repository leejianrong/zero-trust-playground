# Turn on the network layer

We switch on the network layer and watch it stop an attack that mutual TLS cannot see. Then we swap the layers over and watch a different layer stop a different attack. By the end you will know what the network layer covers, what it leaves open, and how the output tells the two layers apart.

You need the clinic deployed (`make clinic`), the observer running (`make observer`) and the clinic page forwarded to your machine (`make web`). The dashboard (`cd web && npm run dev`) has a **Layers** view with a switch for each layer. Every step also works with `curl`, and we show that.

## Start with everything off

```console
$ make attack A=read-postgres
read-postgres: SUCCEEDS   [identity=off, mtls=off, network=off]
expected succeeds: as expected
{
  "rows": 5,
  "sample": "Aisha Rahman"
}
```

The attacker pod holds the shared database password and any pod can reach Postgres, so it read every patient. No network rule stood in the way.

## Turn on the network layer

Open **Layers** and set **Network policy** to **Enforce**, or run:

```console
$ curl -s -X PUT localhost:8765/layers/network -H 'content-type: application/json' -d '{"mode":"enforce"}'
{"identity":"off","mtls":"off","network":"enforce"}
```

The controller applied a set of Kubernetes NetworkPolicies. Look at them:

```console
$ kubectl --context k3d-ztp get networkpolicy -A
NAMESPACE   NAME                POD-SELECTOR      AGE
agents      allow-agent         app=agent         1s
agents      default-deny        <none>            1s
clinic      allow-billing       app=billing       1s
clinic      allow-postgres      app=postgres      1s
clinic      allow-records-api   app=records-api   1s
clinic      allow-records-mcp   app=records-mcp   1s
clinic      allow-web           app=web           1s
clinic      default-deny        <none>            1s
```

Each namespace has a `default-deny` that refuses all incoming connections. Each `allow-` policy then opens one door: the policy for Postgres lets in only `records-api`, the one for `records-api` lets in `web`, `billing` and `records-mcp`, and so on. [Network policies](reference/network-policies.md) lists them all. The only service open to anyone is `web`, because it is the front door.

The layer only restricts incoming connections. Outgoing traffic is open, because nothing in the clinic needed an egress rule.

## The attack is stopped by the network

```console
$ make attack A=read-postgres
read-postgres: BLOCKED   [identity=off, mtls=off, network=enforce]
expected blocked: as expected
stopped by: network (inferred)
{
  "error": "OperationalError",
  "detail": "connection failed: connection to server at \"10.43.167.251\", port 5432 failed: Connection refused\n\tIs the server running on that host and accepting TCP/IP connections?",
  "phase": "connect"
}
```

Two things to read here. The password was correct, and it did not matter: the connection was refused before Postgres could look at it. And `stopped by` says `(inferred)`.

A dropped connection leaves no log line, so no layer can report that it refused you. The observer works it out instead. The attack runner records which phase failed (`connect`, `handshake` or `request`), and the observer names the network layer when the connection never opened or timed out while connecting, the policies are applied (fully or partly), and the target is one they cover. That is a good guess and not proof. A service with no running pods would refuse a connection too, and a closed port on a service that does not define it times out the same way a drop can. Both would be reported the same way.

This is also why the network layer has no **Audit** mode. With mTLS you can log what would have been refused. Here there is nothing to read, so the controller refuses `audit` and says why.

## A compromised pod inside the clinic

The attacker pod is an outsider. A more worrying case is a pod that already belongs to the clinic. `postgres-from-billing` runs the same Postgres attack from inside the `billing` pod, as if someone had gained code execution there:

```console
$ make attack A=postgres-from-billing
postgres-from-billing: BLOCKED   [identity=off, mtls=off, network=enforce]
expected blocked: as expected
stopped by: network (inferred)
{
  "error": "OperationalError",
  "detail": "connection failed: connection to server at \"10.43.167.251\", port 5432 failed: Connection refused\n\tIs the server running on that host and accepting TCP/IP connections?",
  "phase": "connect"
}
```

`billing` is in the clinic and has a good reason to be there, but it has no reason to talk to the database. The per-service allows mean it cannot. A rule that let the whole `clinic` namespace reach Postgres would have missed this. Turn the network layer off and run it again, and it succeeds.

## The clinic still works

Add, edit and delete a patient in the clinic page, and press **Summarise with AI**. Or:

```console
$ curl -s -o /dev/null -w "%{http_code}\n" localhost:8081/api/patients
200
$ curl -s -X POST localhost:8081/api/agent/summarise
{"summary":"5 patients on file","tool_calls":[{"tool":"list_patients","origin":"task"}],"obeyed_injected_text":false}
```

Every call the clinic needs has an allow, so nothing legitimate broke.

## Swap the layers over

Turn the network layer off and mTLS on. The controller wants identity on first, so set that to audit:

```console
$ curl -s -X PUT localhost:8765/layers/network -H 'content-type: application/json' -d '{"mode":"off"}'
$ curl -s -X PUT localhost:8765/layers/identity -H 'content-type: application/json' -d '{"mode":"audit"}'
$ curl -s -X PUT localhost:8765/layers/mtls -H 'content-type: application/json' -d '{"mode":"enforce"}'
{"identity":"audit","mtls":"enforce","network":"off"}
```

Wait a few seconds for the services to pick up the change, then run two attacks:

```console
$ make attack A=no-identity-records
no-identity-records: BLOCKED   [identity=audit, mtls=enforce, network=off]
expected blocked: as expected
stopped by: mtls
$ make attack A=read-postgres
read-postgres: SUCCEEDS   [identity=audit, mtls=enforce, network=off]
expected succeeds: as expected
{
  "rows": 5,
  "sample": "Aisha Rahman"
}
```

The same pod, a different layer. The call to `records-api` is now refused by mTLS, with a log line and a reason, and the Postgres read is wide open again. mTLS protects calls between services. Postgres does not speak it, so the network layer is the one that has to guard the database.

## Both layers on

Turn the network layer back on, with mTLS still enforced, and run the attack that mTLS stopped a moment ago:

```console
$ curl -s -X PUT localhost:8765/layers/network -H 'content-type: application/json' -d '{"mode":"enforce"}'
{"identity":"audit","mtls":"enforce","network":"enforce"}
$ make attack A=no-identity-records
no-identity-records: BLOCKED   [identity=audit, mtls=enforce, network=enforce]
expected blocked: as expected
stopped by: network (inferred)
```

Now the network stops it first, so mTLS never sees a request and never logs one. That is defence in depth: the attack is still stopped if either layer is switched off, but the result only names the layer that got there first. The forged certificate from the mTLS page now reads the same way:

```console
$ make attack A=forged-identity
forged-identity: BLOCKED   [identity=audit, mtls=enforce, network=enforce]
expected blocked: as expected
stopped by: network (inferred)
```

With the network layer off it was dropped at the TLS handshake and no layer was named. The `phase` in the attack's detail tells them apart: `connect` for a network drop, `handshake` for a forged certificate.

## Reset

```console
$ curl -s -X PUT localhost:8765/layers/network -H 'content-type: application/json' -d '{"mode":"off"}'
$ curl -s -X PUT localhost:8765/layers/mtls -H 'content-type: application/json' -d '{"mode":"off"}'
$ curl -s -X PUT localhost:8765/layers/identity -H 'content-type: application/json' -d '{"mode":"off"}'
```

## Recap

- The network layer is a default-deny for incoming connections plus one allow for each call the clinic makes. Turning it off deletes the policies.
- It stopped the Postgres attack from the attacker pod and from a compromised `billing` pod. mTLS cannot do either.
- A dropped connection leaves no log, so the result says `network (inferred)` and the attack's `phase` shows how it failed.
- With both layers on, the first to refuse an attack gets the credit, and the other never sees it.
- The prompt injection still succeeds with every layer on, because it goes through services that are allowed to talk to each other.

## Next steps

- [Break the network layer](how-to/break-the-network-layer.md) deletes policies and shows what you see.
- [Network policies](reference/network-policies.md) lists every allow, and [Attacks](reference/attacks.md) has the outcome of every attack for each layer.
