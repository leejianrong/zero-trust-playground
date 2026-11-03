#!/bin/sh
# Print a one-hour login token for Headlamp. ROLE=viewer (default) is read-only.
# ROLE=admin creates a cluster-admin identity on demand, so you can see how much a cluster
# dashboard can do when its identity is too powerful. The token goes to stdout only.
set -eu
CTX="${CTX:-k3d-ztp}"
ROLE="${ROLE:-viewer}"
if [ "$ROLE" = "admin" ]; then
  kubectl --context "$CTX" -n headlamp create serviceaccount headlamp-admin --dry-run=client -o yaml | kubectl --context "$CTX" apply -f - >/dev/null
  kubectl --context "$CTX" create clusterrolebinding headlamp-admin --clusterrole=cluster-admin \
    --serviceaccount=headlamp:headlamp-admin --dry-run=client -o yaml | kubectl --context "$CTX" apply -f - >/dev/null
  SA=headlamp-admin
else
  SA=headlamp-viewer
fi
kubectl --context "$CTX" -n headlamp create token "$SA" --duration=1h
