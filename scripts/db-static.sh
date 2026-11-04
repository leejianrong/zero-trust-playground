#!/bin/sh
# Revoke or restore the static Postgres password (the `clinic` user's password from the db-static Secret).
# `revoke` replaces it with a random one nobody knows, so a leaked copy stops working. `restore` puts it back.
# The secrets layer calls this. Existing connections stay open; only new logins are affected.
set -eu
CTX="${CTX:-k3d-ztp}"
case "${1:-}" in
  revoke) PW=$(head -c 24 /dev/urandom | od -An -tx1 | tr -d ' \n') ;;
  restore) PW=$(kubectl --context "$CTX" -n clinic get secret db-static -o jsonpath='{.data.password}' | base64 -d) ;;
  *) echo "usage: db-static.sh revoke|restore" >&2; exit 2 ;;
esac
printf "ALTER ROLE clinic PASSWORD '%s';\n" "$PW" |
  kubectl --context "$CTX" -n clinic exec -i deploy/postgres -- psql -q -U clinic -d clinic -v ON_ERROR_STOP=1 >/dev/null
echo "static password: $1"
