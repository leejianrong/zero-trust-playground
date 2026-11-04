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

# web: public client, authorization code with PKCE. Tokens for web carry the records-api audience.
if [ -z "$(kc get clients -r clinic -q clientId=web --fields id --format csv --noquotes | tr -d '\r')" ]; then
  quiet kc create clients -r clinic -s clientId=web -s publicClient=true \
    -s 'redirectUris=["http://localhost:8081/*"]' -s 'webOrigins=["+"]' \
    -s 'attributes={"pkce.code.challenge.method":"S256"}'
  WEB=$(kc get clients -r clinic -q clientId=web --fields id --format csv --noquotes | tr -d '\r')
  quiet kc create "clients/$WEB/protocol-mappers/models" -r clinic -s name=records-api-audience \
    -s protocol=openid-connect -s protocolMapper=oidc-audience-mapper \
    -s 'config={"included.client.audience":"records-api","access.token.claim":"true","id.token.claim":"false"}'
fi
if [ -z "$(kc get clients -r clinic -q clientId=records-api --fields id --format csv --noquotes | tr -d '\r')" ]; then
  quiet kc create clients -r clinic -s clientId=records-api -s bearerOnly=true
fi

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
