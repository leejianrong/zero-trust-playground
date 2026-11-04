# Break the network layer

Run these with the network layer enforced and the other layers off. Each one shows a way the layer can fail and what you see when it does. Set it up from the Layers view or:

```console
$ curl -s -X PUT localhost:8765/layers/network -H 'content-type: application/json' -d '{"mode":"enforce"}'
{"identity":"off","mtls":"off","secrets":"off","network":"enforce"}
```

Keep the clinic page open through `make web`.

## Delete an allow and predict what breaks

Policy `allow-records-api` lets `web`, `billing` and `records-mcp` reach `records-api`. Before you delete it, write down what you expect to happen to the clinic page and to **Summarise with AI**. Then:

```console
$ kubectl --context k3d-ztp -n clinic delete networkpolicy allow-records-api
networkpolicy.networking.k8s.io "allow-records-api" deleted from clinic namespace
$ curl -s -o /dev/null -w "%{http_code} in %{time_total}s\n" localhost:8081/api/patients
500 in 0.022041s
$ curl -s -o /dev/null -w "%{http_code} in %{time_total}s\n" -X POST localhost:8081/api/agent/summarise
500 in 0.116629s
```

Both fail. The summary fails because the agent reaches the data through `records-mcp`, and `records-mcp` is also a caller of `records-api`. The failure is fast, not a hang, because a blocked connection is refused straight away. The web log says so:

```console
$ kubectl --context k3d-ztp -n clinic logs deploy/web --since=2m | grep ConnectError
httpx.ConnectError: [Errno 111] Connection refused
```

The default-deny is still in place, so nothing else opened up. Only the one path you removed is gone, and the clinic page shows a bare `Internal Server Error` with no hint that a network rule is the cause.

Now look at what the controller thinks:

```console
$ curl -s localhost:8765/layers
{"identity":"off","mtls":"off","secrets":"off","network":"partial"}
```

It says `partial`. The controller reads `enforce` only when the whole set exists. With a policy missing but a default-deny still in place, it says `partial`: some paths are open and the rest still deny. The attack matrix treats `partial` like `enforce`, so an attack the set still stops is shown as blocked, not as a success. Only `off` means no default-deny is left. The deletion is also an event (see the next section).

To recover, enforce again. The controller reapplies the full set, which puts back what is missing and leaves the rest alone:

```console
$ curl -s -X PUT localhost:8765/layers/network -H 'content-type: application/json' -d '{"mode":"enforce"}'
{"identity":"off","mtls":"off","secrets":"off","network":"enforce"}
$ curl -s -o /dev/null -w "%{http_code}\n" localhost:8081/api/patients
200
```

## Delete a policy behind the controller's back

The deletion above was made with `kubectl`, not through the controller. The observer watches the policies in `clinic` and `agents` every 2 seconds and reports a change as soon as it sees one. Delete another allow and read the event:

```console
$ kubectl --context k3d-ztp -n clinic delete networkpolicy allow-billing
networkpolicy.networking.k8s.io "allow-billing" deleted from clinic namespace
$ curl -s 'localhost:8765/events?follow=false' | grep '^data:' | grep policy_removed | tail -1 | sed 's/^data: //'
{"v": 1, "ts": 1793729535.3781226, "layer": "network", "kind": "policy_removed", "verdict": "info", "src": "out-of-band", "dst": "clinic/allow-billing", "reason": "allow-billing removed outside the controller", "trace": null, "evidence": {"origin": "out-of-band", "namespace": "clinic", "name": "allow-billing"}, "id": 12092}
```

In our run the event was in the store about a second after the delete, and the limit is 5 seconds. `src` and `origin` say `out-of-band`: someone changed the policies without going through the controller. Now let the controller put it back and compare:

```console
$ curl -s -X PUT localhost:8765/layers/network -H 'content-type: application/json' -d '{"mode":"enforce"}'
{"identity":"off","mtls":"off","secrets":"off","network":"enforce"}
$ curl -s 'localhost:8765/events?follow=false' | grep '^data:' | grep policy_added | tail -1 | sed 's/^data: //'
{"v": 1, "ts": 1793729539.8191347, "layer": "network", "kind": "policy_added", "verdict": "info", "src": "controller", "dst": "clinic/allow-billing", "reason": "allow-billing added by the controller", "trace": null, "evidence": {"origin": "controller", "namespace": "clinic", "name": "allow-billing"}, "id": 12093}
```

This one says `controller`. The watch only reports. It does not put a deleted policy back for you. A change to a policy's rules shows up as `policy_changed`, and an extra policy someone adds shows up as `policy_added` with `out-of-band`.

One gap to know about: a change that lands in the instant between the controller's apply and its own check can be labelled `controller` by mistake.

## Swap the layer under an attack

Run `no-identity-records` with the network layer on and then with mTLS on instead. The same attack is stopped by a different layer, and the output says so. [Turn on the network layer](../the-network-layer.md) walks through it, including the case where both are on and the network gets the credit.

## Reset

```console
$ curl -s -X PUT localhost:8765/layers/network -H 'content-type: application/json' -d '{"mode":"off"}'
{"identity":"off","mtls":"off","secrets":"off","network":"off"}
```

Check that nothing is left behind:

```console
$ kubectl --context k3d-ztp get networkpolicy -A
No resources found
```
