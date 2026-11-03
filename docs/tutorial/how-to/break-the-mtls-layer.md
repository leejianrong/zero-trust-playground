# Break the mTLS layer

Run these with mTLS enforced. Each one shows a way the layer can fail, and what you see when it does. The setup is `identity` at audit and `mtls` at enforce, from the Layers view or:

```console
$ curl -s -X PUT localhost:8765/layers/identity -H 'content-type: application/json' -d '{"mode":"audit"}'
$ curl -s -X PUT localhost:8765/layers/mtls -H 'content-type: application/json' -d '{"mode":"enforce"}'
```

## Remove the identities

Delete the registration that gives the clinic services their identities:

```console
$ kubectl --context k3d-ztp delete clusterspiffeid clinic
clusterspiffeid.spire.spiffe.io "clinic" deleted
```

The clinic keeps working at first, because each service still holds a certificate. We checked the clinic page after 30 seconds and after 90 seconds and it still loaded. After about two and a half minutes the certificates ran out and the page failed with a server error. The web service's log shows why:

```text
httpx.ConnectError: [SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: certificate has expired
```

Zero trust fails closed. A service with no valid identity cannot call another service, and nothing falls back to plain HTTP in enforce mode.

Put the registration back and the clinic recovers by itself:

```console
$ kubectl --context k3d-ztp apply -f deploy/spire/clusterspiffeid-clinic.yaml
```

In our run the page was back 9 seconds later.

## Turn identity off under a running mTLS layer

```console
$ curl -s -X PUT localhost:8765/layers/identity -H 'content-type: application/json' -d '{"mode":"off"}'
{"detail":"mTLS needs workload identity: turn identity on first, or mTLS off first"}
```

The controller refuses. This is a guard that keeps you from breaking your own clinic. It is also the only thing standing in the way, because the controller runs as you.

## Call a service from the wrong place

From the attacker pod, call `records-api` on the plain port, and then on the mTLS port with no certificate. Both are refused in enforce mode, and `kubectl logs deploy/records-api` shows an `authz` line with `"verdict": "deny"` for each. Compare it with the `would_deny` lines you got in audit mode.

## Reset

```console
$ curl -s -X PUT localhost:8765/layers/mtls -H 'content-type: application/json' -d '{"mode":"off"}'
$ curl -s -X PUT localhost:8765/layers/identity -H 'content-type: application/json' -d '{"mode":"off"}'
```
