include versions.env
export

CTX := k3d-$(CLUSTER_NAME)

.DEFAULT_GOAL := help
.PHONY: help
help: ## list targets
	@grep -hE '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-8s %s\n", $$1, $$2}'

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

test: ## fast no-infra tests, lint and type-check
	cd services/observer && uv run ruff check . && uv run pytest -q
	cd web && npm run check && npm test

e2e: ## browser tests against the live cluster (needs make up && make echo)
	cd web && npx playwright test

hooks: ## enable the pre-push hook
	git config core.hooksPath .githooks

.PHONY: clinic
clinic: ## build and deploy the clinic app (web, records-api, billing, postgres)
	docker build -q -t ztp/clinic:dev services/clinic
	k3d image import ztp/clinic:dev -c $(CLUSTER_NAME)
	kubectl --context $(CTX) apply -f deploy/clinic/app.yaml
	kubectl --context $(CTX) -n clinic rollout restart deploy/web deploy/records-api deploy/billing
	kubectl --context $(CTX) -n clinic rollout status deploy/postgres deploy/web deploy/records-api deploy/billing --timeout=180s
