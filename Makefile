include versions.env
export

CTX := k3d-$(CLUSTER_NAME)

.DEFAULT_GOAL := help
.PHONY: help
help: ## list targets
	@grep -hE '^[a-z0-9-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-8s %s\n", $$1, $$2}'

.PHONY: up down status spire clean-check

up: ## create the cluster and install SPIRE
	@k3d cluster list $(CLUSTER_NAME) >/dev/null 2>&1 || k3d cluster create $(CLUSTER_NAME) \
	  --image $(K3S_IMAGE) --no-lb --wait --timeout 240s \
	  --k3s-arg "--disable=traefik@server:0" --k3s-arg "--disable=metrics-server@server:0"
	@kubectl --context $(CTX) create ns clinic --dry-run=client -o yaml | kubectl --context $(CTX) apply -f - >/dev/null
	@$(MAKE) spire
	@echo "ready: $(CTX)"

spire: ## install or upgrade SPIRE and the clinic ClusterSPIFFEID
	@helm repo add spiffe https://spiffe.github.io/helm-charts-hardened/ >/dev/null 2>&1 || true
	@helm repo update spiffe >/dev/null
	@for ns in spire-system spire-server; do kubectl --context $(CTX) create ns $$ns --dry-run=client -o yaml | kubectl --context $(CTX) apply -f - >/dev/null; done
	helm --kube-context $(CTX) upgrade --install spire-crds spiffe/spire-crds --version $(SPIRE_CRDS_CHART) \
	  -n spire-server --wait
	helm --kube-context $(CTX) upgrade --install spire spiffe/spire --version $(SPIRE_CHART) \
	  -n spire-server -f deploy/spire/values.yaml --wait --timeout 5m
	kubectl --context $(CTX) apply -f deploy/spire/clusterspiffeid-clinic.yaml

down: ## delete the cluster
	@k3d cluster delete $(CLUSTER_NAME)

status: ## show cluster pods and memory
	@kubectl --context $(CTX) get pods -A
	@docker stats --no-stream --format '{{.Name}}\t{{.MemUsage}}' | grep $(CLUSTER_NAME) || true

.PHONY: echo
echo: ## build and deploy the V1 spike workloads
	docker build -q -t ztp/echo:dev services/echo
	k3d image import ztp/echo:dev -c $(CLUSTER_NAME)
	kubectl --context $(CTX) apply -f deploy/clinic/echo.yaml
	kubectl --context $(CTX) -n clinic rollout restart deploy/echo-a deploy/echo-b

.PHONY: observer test e2e hooks
observer: ## run the observer on :8765 against the cluster
	cd services/observer && uv run uvicorn --factory observer.app:create_app --port 8765

test: ## fast no-infra tests, lint, type-check and docs checks
	python3 scripts/check_docs_commands.py
	cd services/observer && uv run ruff check . && uv run pytest -q
	cd services/clinic && uv run ruff check . && uv run pytest -q
	cd web && npm run check && npm test

e2e: ## browser tests against the live cluster (needs make up, echo, clinic and headlamp)
	cd web && npx playwright test

hooks: ## enable the pre-push hook
	git config core.hooksPath .githooks

.PHONY: clinic web attack vault eso
attack: ## run an attack from the attacker pod: make attack A=<name> (no A lists them)
	@python3 scripts/attack.py $(A)

clinic: ## build and deploy the clinic app (web, records-api, billing, postgres)
	docker build -q -t ztp/clinic:dev services/clinic
	k3d image import ztp/clinic:dev -c $(CLUSTER_NAME)
	kubectl --context $(CTX) apply -f deploy/spire/clusterspiffeid-clinic.yaml
	kubectl --context $(CTX) apply -f deploy/clinic/app.yaml -f deploy/attacker.yaml -f deploy/agent.yaml -f deploy/clinic/layer-modes.yaml
	kubectl --context $(CTX) -n clinic get cm layer-modes >/dev/null 2>&1 || kubectl --context $(CTX) create -f deploy/clinic/layer-modes-default.yaml
	kubectl --context $(CTX) -n clinic rollout restart deploy/web deploy/records-api deploy/billing deploy/records-mcp
	kubectl --context $(CTX) -n agents rollout restart deploy/agent
	kubectl --context $(CTX) -n attacker rollout restart deploy/attacker
	kubectl --context $(CTX) -n clinic rollout status deploy/postgres deploy/web deploy/records-api deploy/billing deploy/records-mcp --timeout=180s
	kubectl --context $(CTX) -n agents rollout status deploy/agent --timeout=120s
	kubectl --context $(CTX) -n attacker rollout status deploy/attacker --timeout=120s

vault: ## install the dev Vault and configure JWT login for each clinic service (needs make up and clinic)
	sed 's|VAULT_IMAGE|$(VAULT_IMAGE)|' deploy/vault/vault.yaml | kubectl --context $(CTX) apply -f -
	kubectl --context $(CTX) -n vault rollout status deploy/vault --timeout=180s
	sh scripts/vault-configure.sh

eso: ## install External Secrets and sync one secret from Vault (needs make vault)
	@helm repo add external-secrets https://charts.external-secrets.io >/dev/null 2>&1 || true
	@helm repo update external-secrets >/dev/null
	helm --kube-context $(CTX) upgrade --install external-secrets external-secrets/external-secrets --version $(ESO_CHART) \
	  -n external-secrets --create-namespace -f deploy/eso/values.yaml --wait --timeout 5m
	kubectl --context $(CTX) apply -f deploy/eso/store.yaml
	kubectl --context $(CTX) -n clinic wait --for=condition=Ready externalsecret/billing-api-key --timeout=120s

web: ## open the clinic app at http://localhost:8081 (port-forward, Ctrl-C to stop)
	kubectl --context $(CTX) -n clinic port-forward svc/web 8081:8080

.PHONY: headlamp headlamp-token headlamp-ui docs docs-build
headlamp: ## install Headlamp (cluster dashboard) with a read-only login
	@helm repo add headlamp https://kubernetes-sigs.github.io/headlamp/ >/dev/null 2>&1 || true
	@helm repo update headlamp >/dev/null
	helm --kube-context $(CTX) upgrade --install headlamp headlamp/headlamp --version $(HEADLAMP_CHART) \
	  -n headlamp --create-namespace --wait --timeout 3m
	kubectl --context $(CTX) apply -f deploy/headlamp/rbac.yaml

headlamp-token: ## print a login token for Headlamp (ROLE=admin for the cluster-admin contrast)
	@scripts/headlamp-token.sh

headlamp-ui: ## open Headlamp at http://localhost:4466 (port-forward, Ctrl-C to stop)
	kubectl --context $(CTX) -n headlamp port-forward svc/headlamp 4466:80

DOCS_PY := .docs-venv/bin/python
$(DOCS_PY):
	uv venv .docs-venv --python 3.12 --allow-existing
	uv pip install zensical --python $(DOCS_PY)

docs: $(DOCS_PY) ## serve the tutorial at http://localhost:8000
	.docs-venv/bin/zensical serve

docs-build: $(DOCS_PY) ## build the tutorial (strict) into site/
	.docs-venv/bin/zensical build --clean --strict
