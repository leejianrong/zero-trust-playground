#!/usr/bin/env bash
# Log one line of machine and cluster state every INTERVAL seconds, so a failing run shows whether the runner was
# starved at that moment. Run it in the background; it stops when the job ends. Usage: ci-sample.sh LOGFILE [INTERVAL]
log=${1:?log file}
interval=${2:-10}
node=k3d-${CLUSTER_NAME:-ztp}-server-0
ctx=k3d-${CLUSTER_NAME:-ztp}
echo "time | host mem used/avail MB | swap used MB | load1 | node mem/limit, cpu% | oom | pod restarts | pods not ready" >"$log"
while true; do
  mem=$(free -m | awk '/^Mem:/{printf "%s/%s", $3, $7}')
  swap=$(free -m | awk '/^Swap:/{print $3}')
  load=$(cut -d' ' -f1 /proc/loadavg)
  stats=$(docker stats --no-stream --format '{{.MemUsage}}, {{.CPUPerc}}' "$node" 2>/dev/null || echo "n/a")
  oom=$(docker inspect -f '{{.State.OOMKilled}}' "$node" 2>/dev/null || echo "n/a")
  pods=$(kubectl --context "$ctx" get pods -A --no-headers 2>/dev/null || true)
  restarts=$(echo "$pods" | awk '{n+=$5} END{print n+0}')
  notready=$(echo "$pods" | awk '{split($3,a,"/"); if ($4!="Completed" && a[1]!=a[2]) printf "%s/%s ", $1, $2}')
  echo "$(date +%T) | $mem | $swap | $load | $stats | $oom | $restarts | ${notready:-none}" >>"$log"
  sleep "$interval"
done
