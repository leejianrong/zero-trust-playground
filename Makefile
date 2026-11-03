include versions.env
export

CTX := k3d-$(CLUSTER_NAME)

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
