#!/bin/sh
# Configure the dev Vault from nothing: JWT auth that trusts SPIRE, and one role per clinic service.
# Safe to run again. The root token is the dev-mode throwaway from deploy/vault/vault.yaml (ADR-0012).
set -eu
CTX="${CTX:-k3d-ztp}"
SERVICES="web records-api billing records-mcp"
TRUST_DOMAIN="${TRUST_DOMAIN:-playground.local}"
ISSUER="https://oidc-discovery.$TRUST_DOMAIN"
KEYS="https://spire-spiffe-oidc-discovery-provider.spire-server.svc.cluster.local/keys"

vault() {
  kubectl --context "$CTX" -n vault exec -i deploy/vault -- env VAULT_ADDR=http://127.0.0.1:8200 VAULT_TOKEN=playground-dev-root vault "$@"
}

# The audit log goes to the pod's stdout, where the observer reads it for the Secrets view.
vault audit list -format=json | grep -q '"file/"' || vault audit enable file file_path=stdout >/dev/null
vault auth list -format=json | grep -q '"jwt/"' || vault auth enable jwt >/dev/null

# SPIRE's CA, as PEM, from the trust bundle. Vault needs it to fetch the signing keys over TLS.
kubectl --context "$CTX" -n spire-server get cm spire-bundle -o jsonpath='{.data.bundle\.spiffe}' |
  jq -r '.keys[] | select(.use=="x509-svid") | .x5c[0]' |
  while read -r cert; do echo "-----BEGIN CERTIFICATE-----"; echo "$cert" | fold -w64; echo "-----END CERTIFICATE-----"; done |
  vault write auth/jwt/config jwks_url="$KEYS" bound_issuer="$ISSUER" jwks_ca_pem=- >/dev/null

# Vault gets its own Postgres admin, so the app's static password is not the one Vault depends on and can be revoked.
# The password is random on every run, goes to Postgres and Vault over stdin, and is never printed.
ADMIN_PW=$(head -c 24 /dev/urandom | od -An -tx1 | tr -d ' \n')
printf "DO \$\$ BEGIN IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname='vault_admin') THEN CREATE ROLE vault_admin LOGIN SUPERUSER; END IF; END \$\$;\nALTER ROLE vault_admin PASSWORD '%s';\n" "$ADMIN_PW" |
  kubectl --context "$CTX" -n clinic exec -i deploy/postgres -- psql -q -U clinic -d clinic -v ON_ERROR_STOP=1 >/dev/null

vault secrets list -format=json | grep -q '"database/"' || vault secrets enable database >/dev/null
jq -n --arg pw "$ADMIN_PW" '{plugin_name:"postgresql-database-plugin", allowed_roles:"records-api", username:"vault_admin", password:$pw,
  connection_url:"postgresql://{{username}}:{{password}}@postgres.clinic.svc.cluster.local:5432/clinic?sslmode=disable"}' |
  vault write database/config/clinic - >/dev/null
# A credential lasts two minutes and cannot be extended.
vault write database/roles/records-api db_name=clinic default_ttl=2m max_ttl=2m \
  creation_statements="CREATE ROLE \"{{name}}\" WITH LOGIN PASSWORD '{{password}}' VALID UNTIL '{{expiration}}'; GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO \"{{name}}\"; GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO \"{{name}}\";" >/dev/null
echo 'path "database/creds/records-api" { capabilities = ["read"] }' | vault policy write records-api - >/dev/null

# One role per service, bound to that service's SPIFFE ID. Only records-api may read database credentials.
for svc in $SERVICES; do
  policy=default; [ "$svc" = records-api ] && policy=records-api
  vault write "auth/jwt/role/$svc" role_type=jwt user_claim=sub bound_audiences=vault \
    bound_subject="spiffe://$TRUST_DOMAIN/ns/clinic/sa/$svc" token_ttl=2m token_policies="$policy" >/dev/null
done
# External Secrets logs in with a Kubernetes service account token and may read one path, nothing else.
vault auth list -format=json | grep -q '"kubernetes/"' || vault auth enable kubernetes >/dev/null
vault write auth/kubernetes/config kubernetes_host=https://kubernetes.default.svc disable_iss_validation=true >/dev/null
echo 'path "secret/data/clinic/billing-api-key" { capabilities = ["read"] }' | vault policy write eso - >/dev/null
vault write auth/kubernetes/role/eso bound_service_account_names=eso-reader bound_service_account_namespaces=clinic \
  policies=eso ttl=10m >/dev/null
vault kv get secret/clinic/billing-api-key >/dev/null 2>&1 || vault kv put secret/clinic/billing-api-key value=placeholder-api-key >/dev/null
echo "vault configured: jwt auth trusts $ISSUER, roles: $SERVICES, database credentials for records-api"
