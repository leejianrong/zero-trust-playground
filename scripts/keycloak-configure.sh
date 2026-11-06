#!/bin/sh
# Create the clinic realm in a dev Keycloak (ADR-0013). Safe to run twice: each step looks before it creates.
# Throwaway passwords, localhost only.
set -eu
CTX="${CTX:-k3d-ztp}"
kc() { kubectl --context "$CTX" -n keycloak exec deploy/keycloak -- /opt/keycloak/bin/kcadm.sh "$@"; }
quiet() { "$@" >/dev/null; }

quiet kc config credentials --server http://localhost:8080 --realm master --user admin --password playground-dev-admin

if ! kc get realms/clinic >/dev/null 2>&1; then
  quiet kc create realms -s realm=clinic -s enabled=true -s eventsEnabled=true -s 'eventsListeners=["jboss-logging"]'
fi

for role in clinician receptionist; do
  kc get "roles/$role" -r clinic >/dev/null 2>&1 || quiet kc create roles -r clinic -s "name=$role"
done

# Each step looks before it creates, including the audience mappers, so a run that stopped halfway can be repeated.
client_id() { kc get clients -r clinic -q "clientId=$1" --fields id --format csv --noquotes | tr -d '\r'; }
audience_mapper() {  # client, audience: tokens issued to the client name that audience
  if ! kc get "clients/$(client_id "$1")/protocol-mappers/models" -r clinic --fields name --format csv --noquotes | grep -qx "$1-audience"; then
    quiet kc create "clients/$(client_id "$1")/protocol-mappers/models" -r clinic -s "name=$1-audience" \
      -s protocol=openid-connect -s protocolMapper=oidc-audience-mapper \
      -s "config={\"included.client.audience\":\"$2\",\"access.token.claim\":\"true\",\"id.token.claim\":\"false\"}"
  fi
}

# web: public client, authorization code with PKCE. Tokens for web carry the records-api audience.
[ -n "$(client_id web)" ] || quiet kc create clients -r clinic -s clientId=web -s publicClient=true \
  -s 'redirectUris=["http://localhost:8081/*"]' -s 'webOrigins=["+"]' -s 'attributes={"pkce.code.challenge.method":"S256"}'
audience_mapper web records-api
[ -n "$(client_id records-api)" ] || quiet kc create clients -r clinic -s clientId=records-api -s bearerOnly=true

# LABELLED WEAK, FOR ATTACKS ONLY: a client that signs in with a password and gets tokens meant for billing, not records-api.
# The wrong-audience attack uses it to hold a genuine token that records-api must still refuse.
[ -n "$(client_id billing)" ] || quiet kc create clients -r clinic -s clientId=billing -s bearerOnly=true
[ -n "$(client_id attacker-cli)" ] || quiet kc create clients -r clinic -s clientId=attacker-cli -s publicClient=true -s directAccessGrantsEnabled=true
audience_mapper attacker-cli billing

for pair in aisha:clinician bob:receptionist; do
  user=${pair%%:*}; role=${pair##*:}
  if [ -z "$(kc get users -r clinic -q "username=$user" --fields id --format csv --noquotes | tr -d '\r')" ]; then
    quiet kc create users -r clinic -s "username=$user" -s enabled=true -s "email=$user@clinic.test" \
      -s emailVerified=true -s "firstName=$user" -s lastName=Test
    quiet kc set-password -r clinic --username "$user" --new-password "playground-$user"
    quiet kc add-roles -r clinic --uusername "$user" --rolename "$role"
  fi
done

echo "keycloak configured: realm clinic, clients web records-api, roles clinician receptionist, users aisha bob"
