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

vault auth list -format=json | grep -q '"jwt/"' || vault auth enable jwt >/dev/null

# SPIRE's CA, as PEM, from the trust bundle. Vault needs it to fetch the signing keys over TLS.
kubectl --context "$CTX" -n spire-server get cm spire-bundle -o jsonpath='{.data.bundle\.spiffe}' |
  jq -r '.keys[] | select(.use=="x509-svid") | .x5c[0]' |
  while read -r cert; do echo "-----BEGIN CERTIFICATE-----"; echo "$cert" | fold -w64; echo "-----END CERTIFICATE-----"; done |
  vault write auth/jwt/config jwks_url="$KEYS" bound_issuer="$ISSUER" jwks_ca_pem=- >/dev/null

# One role per service, bound to that service's SPIFFE ID. No policy yet: later cards add what each may read.
for svc in $SERVICES; do
  vault write "auth/jwt/role/$svc" role_type=jwt user_claim=sub bound_audiences=vault \
    bound_subject="spiffe://$TRUST_DOMAIN/ns/clinic/sa/$svc" token_ttl=2m token_policies=default >/dev/null
done
echo "vault configured: jwt auth trusts $ISSUER, roles: $SERVICES"
