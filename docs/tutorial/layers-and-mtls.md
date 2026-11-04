# Turn on mutual TLS

We switch the identity and mTLS layers on, one step at a time, and run the same attacks at each step. By the end you will have seen one attack that mTLS stops, one it cannot stop, and one it stops in a place no log can see.

You need the clinic deployed (`make clinic`), the observer running (`make observer`), and the clinic page open through `make web`. The dashboard (`cd web && npm run dev`) gives you a **Layers** view for the switches. Every step below also works with `curl`, and we show both.

## Start with everything off

```console
$ make attack A=no-identity-records
no-identity-records: SUCCEEDS   [identity=off, mtls=off, secrets=off, user=off, network=off]
expected succeeds: as expected
{
  "status": 200,
  "items": 6
}
```

The attacker pod has no business in the clinic, and `records-api` handed over every patient. Nothing asked who was calling.

## Turn on identity

Open **Layers** and set **Workload identity** to **Audit**, or run:

```console
$ curl -s -X PUT localhost:8765/layers/identity -H 'content-type: application/json' -d '{"mode":"audit"}'
```

Services now call each other over mutual TLS and present their SPIFFE identity. Nobody checks it yet, so the attack from the last step still works. Open **Architecture** and you will see an `ID` badge on each service.

Now try to jump ahead and enforce mTLS first, with identity back off:

```console
$ curl -s -X PUT localhost:8765/layers/identity -H 'content-type: application/json' -d '{"mode":"off"}'
$ curl -s -X PUT localhost:8765/layers/mtls -H 'content-type: application/json' -d '{"mode":"enforce"}'
{"detail":"mTLS needs workload identity: turn identity on first, or mTLS off first"}
```

The controller refuses, because enforcing mTLS with no identities would lock the clinic's own services out. The **Layers** view shows the same sentence. Set identity to audit again before you carry on.

## Audit: see what would be refused

Set **Mutual TLS and authorisation** to **Audit** (or `PUT /layers/mtls` with `{"mode":"audit"}`). A change reaches every service within a few seconds. Run the attack again:

```console
$ make attack A=no-identity-records
no-identity-records: SUCCEEDS   [identity=audit, mtls=audit, secrets=off, user=off, network=off]
expected succeeds: as expected
{
  "status": 200,
  "items": 6
}
```

It still gets through, because audit only logs. Look at what `records-api` recorded:

```console
$ kubectl --context k3d-ztp -n clinic logs deploy/records-api --since=1m | grep would_deny
{"event": "authz", "service": "records-api", "mode": "audit", "caller": null, "method": "GET", "route": "/patients", "listener": "plain", "verdict": "would_deny", "reason": "plain connection: no identity can be proven", "trace": "d78c846800a8"}
```

`would_deny` is the line to read. In enforce mode this request is refused for that reason. Audit is how you find out what a layer would break before you switch it on. The legitimate callers, such as `web` and `records-mcp`, show up in the same log as `allow` with their SPIFFE ID in `caller`.

## Enforce

Set **Mutual TLS and authorisation** to **Enforce** and run the attack once more:

```console
$ make attack A=no-identity-records
no-identity-records: BLOCKED   [identity=audit, mtls=enforce, secrets=off, user=off, network=off]
expected blocked: as expected
stopped by: mtls
```

`stopped by` comes from the events: the attack tags every request with one trace id, and the layer of the first refusal with that id is reported. To see the refusal itself, call the service by hand:

```console
$ kubectl --context k3d-ztp -n attacker exec deploy/attacker -- python -c "
import urllib.request as u
try: print(u.urlopen('http://records-api.clinic.svc:8080/patients').status)
except Exception as e: print(e.code, e.read().decode())"
403 {"error": "refused", "reason": "plain connection: no identity can be proven", "trace": "e71e0c7d0d8b"}
```

The clinic page still works. Add, edit and delete a patient, and press **Summarise with AI**. The calls between the services carry identities that are on the allow-list.

Run `make attack` with no name to list every attack, and try `cross-namespace-billing` and `mcp-no-identity`. Both are blocked and both name `mtls`.

## The attack mTLS cannot stop

Run the prompt injection:

```console
$ make attack A=agent-prompt-injection
agent-prompt-injection: SUCCEEDS   [identity=audit, mtls=enforce, secrets=off, user=off, network=off]
expected succeeds: as expected
```

The decoy patient is deleted even though mTLS is enforced. The attack goes the way a user would: **Summarise with AI** calls `web`, `web` calls the agent, and the agent calls the tools. Every one of those callers is legitimate and on the allow-list, so there is nothing for mTLS to refuse. The agent obeys text hidden in a record, and that is a different problem. It is why the playground has a later slice for agents.

`read-postgres` also still succeeds. mTLS covers calls between services, and the database password is a separate problem for the network and secrets layers.

## The attack that no log can see

```console
$ make attack A=forged-identity
forged-identity: BLOCKED   [identity=audit, mtls=enforce, secrets=off, user=off, network=off]
expected blocked: as expected
stopped by: no layer recorded an event (refused before any request, or not by a layer)
{
  "error": "RemoteProtocolError",
  "detail": "Server disconnected without sending a response."
}
```

The attacker made up a certificate that names itself `spiffe://playground.local/ns/clinic/sa/web`. Anyone can write that name. Only SPIRE can sign it, so the server drops the connection during the TLS handshake. That happens before any HTTP request exists, so there is no trace id, no `authz` event and no `stopped by`.

Set mTLS back to **Off** and run it again. It now succeeds, because with the layer off the server does not ask for a certificate at all. In **Audit** it is dropped at the handshake, the same as in **Enforce**, so audit mode cannot log it.

## Recap

- Identity and mTLS are separate layers. Identity comes first, and the controller refuses an order that would break the clinic.
- Audit tells you what enforcement would refuse. It changes nothing.
- Enforce stopped three of the seven attacks. Each result lists which layer stopped it.
- A forged certificate dies in the handshake, where no log can see it.
- The prompt injection and the database read are still open, and that tells you which layers to build next.

## Next steps

- [Break the mTLS layer](how-to/break-the-mtls-layer.md) shows what goes wrong when the identity underneath fails.
- [Attacks](reference/attacks.md) has the full table of outcomes per layer.
