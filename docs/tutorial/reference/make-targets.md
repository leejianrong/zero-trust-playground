# Make targets

Every command runs from the repository root. `make` with no target prints this list.

| Target | What it does |
|---|---|
| `make up` | Creates the k3d cluster `ztp` and installs SPIRE |
| `make spire` | Installs or upgrades SPIRE and the `clinic` registration |
| `make down` | Deletes the cluster |
| `make status` | Shows every pod and the node's memory use |
| `make echo` | Builds and deploys the two identity demo workloads |
| `make clinic` | Builds the image and deploys `web`, `records-api`, `billing`, `records-mcp`, Postgres, the `agent` and the `attacker` |
| `make attack A=<name>` | Runs an attack from the attacker pod and prints the outcome and evidence. With no `A`, lists the attacks. Needs `make observer` |
| `make vault` | Installs a throwaway dev-mode Vault and configures JWT login, database credentials and the audit log. Run it again after Vault restarts |
| `make eso` | Installs External Secrets and syncs one secret from Vault into the `clinic` namespace. Needs `make vault` |
| `make keycloak` | Installs a throwaway dev-mode Keycloak, then creates the `clinic` realm with its clients, two roles and two users. Run it again after Keycloak restarts |
| `make keycloak-ui` | Port-forwards Keycloak to <http://localhost:8180>. The clinic page's Sign in needs it |
| `make web` | Port-forwards the clinic app to <http://localhost:8081> |
| `make observer` | Runs the observer on port 8765 |
| `make headlamp` | Installs Headlamp with a read-only login |
| `make headlamp-ui` | Port-forwards Headlamp to <http://localhost:4466> |
| `make headlamp-token` | Prints a one-hour Headlamp token. `ROLE=admin` creates a cluster-admin identity first |
| `make docs` | Serves this tutorial at <http://localhost:8000> |
| `make docs-build` | Builds the tutorial strictly into `site/` |
| `make test` | Runs unit tests, lint, type checks and the docs checks. No cluster needed |
| `make e2e` | Runs the browser tests against the live cluster. Needs `make up`, `make echo`, `make clinic`, `make headlamp`, `make vault`, `make eso` and `make keycloak` |
| `make hooks` | Turns on the pre-push hook that runs `make test` |

Chart and image versions are pinned in `versions.env`.
