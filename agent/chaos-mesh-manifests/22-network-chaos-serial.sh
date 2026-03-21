#!/usr/bin/env bash
set -euo pipefail

NS="backend"
BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ -r /etc/rancher/k3s/k3s.yaml ]] && command -v k3s >/dev/null 2>&1; then
  KCTL=(sudo k3s kubectl)
else
  KCTL=(kubectl)
fi

echo "[INFO] using kubectl command: ${KCTL[*]}"

kctl() {
  "${KCTL[@]}" "$@"
}

apply_one() {
  local name="$1"
  local yaml="$2"
  local wait_sec="$3"

  echo "[INFO] apply ${name}"
  kctl apply -f "${yaml}"
  sleep "${wait_sec}"
  kctl get networkchaos -n "${NS}" || true

  echo "[INFO] delete ${name}"
  kctl delete -f "${yaml}" --ignore-not-found
  sleep 5
}

has_dependency_targets() {
  kctl get pods -n "${NS}" -l role=dependency --no-headers 2>/dev/null | grep -q .
}

# These network faults must run one-by-one to avoid tc netem tree conflicts.
apply_one "delay" "${BASE_DIR}/20-network-chaos-delay.yaml" 30
apply_one "loss" "${BASE_DIR}/20-network-chaos-loss.yaml" 30
apply_one "duplicate" "${BASE_DIR}/20-network-chaos-duplicate.yaml" 30
apply_one "corrupt" "${BASE_DIR}/20-network-chaos-corrupt.yaml" 30
apply_one "bandwidth" "${BASE_DIR}/20-network-chaos-bandwidth.yaml" 30

if has_dependency_targets; then
  apply_one "partition" "${BASE_DIR}/20-network-chaos-partition.yaml" 30
else
  echo "[INFO] skip partition: no pods with label role=dependency in namespace ${NS}"
fi

echo "[INFO] completed serial network chaos run"
