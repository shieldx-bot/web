#!/usr/bin/env bash
set -euo pipefail

# Custom Chaos Mesh runner for on-demand fault injection.
# Supports k3s and standard kubectl environments.

NS="backend"
SELECTOR_KEY="chaos-target"
SELECTOR_VALUE="true"
DURATION="15m"
FAULT=""
ACTION="apply"

if [[ -r /etc/rancher/k3s/k3s.yaml ]] && command -v k3s >/dev/null 2>&1; then
  KCTL=(sudo k3s kubectl)
else
  KCTL=(kubectl)
fi

kctl() {
  "${KCTL[@]}" "$@"
}

usage() {
  cat <<'EOF'
Usage:
  ./23-chaos-custom.sh --list
  ./23-chaos-custom.sh --fault <fault-id> [--duration 15m] [--namespace backend] [--selector chaos-target=true] [--apply|--delete|--status]
  ./23-chaos-custom.sh --delete-all [--namespace backend]

Fault IDs:
  disk-latency
  disk-read-fault
  disk-write-fault
  disk-saturation
  net-delay
  net-loss
  net-duplicate
  net-corrupt
  net-bandwidth
  net-partition
  dns-error
  dns-timeout

Examples:
  ./23-chaos-custom.sh --fault net-delay --duration 10m --apply
  ./23-chaos-custom.sh --fault dns-error --duration 5m --apply
  ./23-chaos-custom.sh --fault net-delay --delete
  ./23-chaos-custom.sh --delete-all
EOF
}

list_faults() {
  awk 'BEGIN {
    print "Available faults:";
    print "- disk-latency";
    print "- disk-read-fault";
    print "- disk-write-fault";
    print "- disk-saturation";
    print "- net-delay";
    print "- net-loss";
    print "- net-duplicate";
    print "- net-corrupt";
    print "- net-bandwidth";
    print "- net-partition";
    print "- dns-error";
    print "- dns-timeout";
  }'
}

validate_duration() {
  if ! [[ "${DURATION}" =~ ^[0-9]+[smhd]$ ]]; then
    echo "[ERROR] Invalid duration: ${DURATION}. Expected format like 30s, 10m, 2h, 1d"
    exit 1
  fi
}

set_selector() {
  local selector="$1"
  if [[ "${selector}" != *=* ]]; then
    echo "[ERROR] Invalid selector: ${selector}. Expected key=value"
    exit 1
  fi
  SELECTOR_KEY="${selector%%=*}"
  SELECTOR_VALUE="${selector#*=}"
}

fault_meta() {
  case "${FAULT}" in
    disk-latency) echo "IOChaos custom-disk-latency" ;;
    disk-read-fault) echo "IOChaos custom-disk-read-fault" ;;
    disk-write-fault) echo "IOChaos custom-disk-write-fault" ;;
    disk-saturation) echo "StressChaos custom-disk-saturation" ;;
    net-delay) echo "NetworkChaos custom-net-delay" ;;
    net-loss) echo "NetworkChaos custom-net-loss" ;;
    net-duplicate) echo "NetworkChaos custom-net-duplicate" ;;
    net-corrupt) echo "NetworkChaos custom-net-corrupt" ;;
    net-bandwidth) echo "NetworkChaos custom-net-bandwidth" ;;
    net-partition) echo "NetworkChaos custom-net-partition" ;;
    dns-error) echo "DNSChaos custom-dns-error" ;;
    dns-timeout) echo "DNSChaos custom-dns-timeout" ;;
    *)
      echo "[ERROR] Unknown fault: ${FAULT}"
      list_faults
      exit 1
      ;;
  esac
}

render_manifest() {
  case "${FAULT}" in
    disk-latency)
      cat <<EOF
apiVersion: chaos-mesh.org/v1alpha1
kind: IOChaos
metadata:
  name: custom-disk-latency
  namespace: ${NS}
spec:
  action: latency
  mode: all
  selector:
    namespaces:
      - ${NS}
    labelSelectors:
      ${SELECTOR_KEY}: "${SELECTOR_VALUE}"
  volumePath: /mnt/chaos
  path: "/mnt/chaos/*"
  delay: "80ms"
  percent: 100
  methods:
    - READ
    - WRITE
  duration: "${DURATION}"
EOF
      ;;
    disk-read-fault)
      cat <<EOF
apiVersion: chaos-mesh.org/v1alpha1
kind: IOChaos
metadata:
  name: custom-disk-read-fault
  namespace: ${NS}
spec:
  action: fault
  mode: fixed-percent
  value: "50"
  selector:
    namespaces:
      - ${NS}
    labelSelectors:
      ${SELECTOR_KEY}: "${SELECTOR_VALUE}"
  volumePath: /mnt/chaos
  path: "/mnt/chaos/*"
  errno: 5
  percent: 100
  methods:
    - READ
  duration: "${DURATION}"
EOF
      ;;
    disk-write-fault)
      cat <<EOF
apiVersion: chaos-mesh.org/v1alpha1
kind: IOChaos
metadata:
  name: custom-disk-write-fault
  namespace: ${NS}
spec:
  action: fault
  mode: fixed-percent
  value: "50"
  selector:
    namespaces:
      - ${NS}
    labelSelectors:
      ${SELECTOR_KEY}: "${SELECTOR_VALUE}"
  volumePath: /mnt/chaos
  path: "/mnt/chaos/*"
  errno: 28
  percent: 100
  methods:
    - WRITE
  duration: "${DURATION}"
EOF
      ;;
    disk-saturation)
      cat <<EOF
apiVersion: chaos-mesh.org/v1alpha1
kind: StressChaos
metadata:
  name: custom-disk-saturation
  namespace: ${NS}
spec:
  mode: all
  selector:
    namespaces:
      - ${NS}
    labelSelectors:
      ${SELECTOR_KEY}: "${SELECTOR_VALUE}"
  stressors:
    cpu:
      workers: 2
      load: 80
    memory:
      workers: 1
      size: "1GB"
  duration: "${DURATION}"
EOF
      ;;
    net-delay)
      cat <<EOF
apiVersion: chaos-mesh.org/v1alpha1
kind: NetworkChaos
metadata:
  name: custom-net-delay
  namespace: ${NS}
spec:
  action: delay
  mode: all
  selector:
    namespaces:
      - ${NS}
    labelSelectors:
      ${SELECTOR_KEY}: "${SELECTOR_VALUE}"
  delay:
    latency: "180ms"
    correlation: "35"
    jitter: "60ms"
  duration: "${DURATION}"
EOF
      ;;
    net-loss)
      cat <<EOF
apiVersion: chaos-mesh.org/v1alpha1
kind: NetworkChaos
metadata:
  name: custom-net-loss
  namespace: ${NS}
spec:
  action: loss
  mode: fixed-percent
  value: "70"
  selector:
    namespaces:
      - ${NS}
    labelSelectors:
      ${SELECTOR_KEY}: "${SELECTOR_VALUE}"
  loss:
    loss: "12"
    correlation: "30"
  duration: "${DURATION}"
EOF
      ;;
    net-duplicate)
      cat <<EOF
apiVersion: chaos-mesh.org/v1alpha1
kind: NetworkChaos
metadata:
  name: custom-net-duplicate
  namespace: ${NS}
spec:
  action: duplicate
  mode: fixed-percent
  value: "60"
  selector:
    namespaces:
      - ${NS}
    labelSelectors:
      ${SELECTOR_KEY}: "${SELECTOR_VALUE}"
  duplicate:
    duplicate: "8"
    correlation: "20"
  duration: "${DURATION}"
EOF
      ;;
    net-corrupt)
      cat <<EOF
apiVersion: chaos-mesh.org/v1alpha1
kind: NetworkChaos
metadata:
  name: custom-net-corrupt
  namespace: ${NS}
spec:
  action: corrupt
  mode: fixed-percent
  value: "60"
  selector:
    namespaces:
      - ${NS}
    labelSelectors:
      ${SELECTOR_KEY}: "${SELECTOR_VALUE}"
  corrupt:
    corrupt: "3"
    correlation: "25"
  duration: "${DURATION}"
EOF
      ;;
    net-bandwidth)
      cat <<EOF
apiVersion: chaos-mesh.org/v1alpha1
kind: NetworkChaos
metadata:
  name: custom-net-bandwidth
  namespace: ${NS}
spec:
  action: bandwidth
  mode: all
  selector:
    namespaces:
      - ${NS}
    labelSelectors:
      ${SELECTOR_KEY}: "${SELECTOR_VALUE}"
  bandwidth:
    rate: "2mbps"
    limit: 20971520
    buffer: 10000
  duration: "${DURATION}"
EOF
      ;;
    net-partition)
      cat <<EOF
apiVersion: chaos-mesh.org/v1alpha1
kind: NetworkChaos
metadata:
  name: custom-net-partition
  namespace: ${NS}
spec:
  action: partition
  mode: all
  selector:
    namespaces:
      - ${NS}
    labelSelectors:
      ${SELECTOR_KEY}: "${SELECTOR_VALUE}"
  direction: both
  target:
    mode: all
    selector:
      namespaces:
        - ${NS}
      labelSelectors:
        role: dependency
  duration: "${DURATION}"
EOF
      ;;
    dns-error)
      cat <<EOF
apiVersion: chaos-mesh.org/v1alpha1
kind: DNSChaos
metadata:
  name: custom-dns-error
  namespace: ${NS}
spec:
  action: error
  mode: all
  selector:
    namespaces:
      - ${NS}
    labelSelectors:
      ${SELECTOR_KEY}: "${SELECTOR_VALUE}"
  patterns:
    - "kubernetes.default.svc.cluster.local"
    - "myapp.backend.svc.cluster.local"
  duration: "${DURATION}"
EOF
      ;;
    dns-timeout)
      cat <<EOF
apiVersion: chaos-mesh.org/v1alpha1
kind: DNSChaos
metadata:
  name: custom-dns-timeout
  namespace: ${NS}
spec:
  action: random
  mode: fixed-percent
  value: "70"
  selector:
    namespaces:
      - ${NS}
    labelSelectors:
      ${SELECTOR_KEY}: "${SELECTOR_VALUE}"
  patterns:
    - "kubernetes.default.svc.cluster.local"
    - "myapp.backend.svc.cluster.local"
  duration: "${DURATION}"
EOF
      ;;
  esac
}

apply_fault() {
  local tmp
  tmp="$(mktemp)"
  render_manifest >"${tmp}"
  echo "[INFO] applying fault='${FAULT}' duration='${DURATION}' namespace='${NS}' selector='${SELECTOR_KEY}=${SELECTOR_VALUE}'"
  kctl apply -f "${tmp}"
  rm -f "${tmp}"
}

delete_fault() {
  read -r kind name < <(fault_meta)
  local resource
  resource="$(echo "${kind}" | tr '[:upper:]' '[:lower:]')/${name}"
  echo "[INFO] deleting ${resource} in namespace ${NS}"
  kctl delete -n "${NS}" "${resource}" --ignore-not-found
}

status_fault() {
  read -r kind name < <(fault_meta)
  local resource
  resource="$(echo "${kind}" | tr '[:upper:]' '[:lower:]')/${name}"
  kctl get -n "${NS}" "${resource}" -o wide || true
}

delete_all() {
  echo "[INFO] deleting all custom chaos resources in namespace ${NS}"
  kctl delete -n "${NS}" iochaos/custom-disk-latency --ignore-not-found
  kctl delete -n "${NS}" iochaos/custom-disk-read-fault --ignore-not-found
  kctl delete -n "${NS}" iochaos/custom-disk-write-fault --ignore-not-found
  kctl delete -n "${NS}" stresschaos/custom-disk-saturation --ignore-not-found
  kctl delete -n "${NS}" networkchaos/custom-net-delay --ignore-not-found
  kctl delete -n "${NS}" networkchaos/custom-net-loss --ignore-not-found
  kctl delete -n "${NS}" networkchaos/custom-net-duplicate --ignore-not-found
  kctl delete -n "${NS}" networkchaos/custom-net-corrupt --ignore-not-found
  kctl delete -n "${NS}" networkchaos/custom-net-bandwidth --ignore-not-found
  kctl delete -n "${NS}" networkchaos/custom-net-partition --ignore-not-found
  kctl delete -n "${NS}" dnschaos/custom-dns-error --ignore-not-found
  kctl delete -n "${NS}" dnschaos/custom-dns-timeout --ignore-not-found
}

if [[ $# -eq 0 ]]; then
  usage
  exit 1
fi

while [[ $# -gt 0 ]]; do
  case "$1" in
    --list)
      list_faults
      exit 0
      ;;
    --fault)
      FAULT="${2:-}"
      shift 2
      ;;
    --duration)
      DURATION="${2:-}"
      shift 2
      ;;
    --namespace)
      NS="${2:-}"
      shift 2
      ;;
    --selector)
      set_selector "${2:-}"
      shift 2
      ;;
    --apply)
      ACTION="apply"
      shift
      ;;
    --delete)
      ACTION="delete"
      shift
      ;;
    --status)
      ACTION="status"
      shift
      ;;
    --delete-all)
      ACTION="delete-all"
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "[ERROR] Unknown argument: $1"
      usage
      exit 1
      ;;
  esac
done

if [[ "${ACTION}" == "delete-all" ]]; then
  delete_all
  exit 0
fi

if [[ -z "${FAULT}" ]]; then
  echo "[ERROR] --fault is required"
  usage
  exit 1
fi

validate_duration

case "${ACTION}" in
  apply)
    apply_fault
    ;;
  delete)
    delete_fault
    ;;
  status)
    status_fault
    ;;
  *)
    echo "[ERROR] Unsupported action: ${ACTION}"
    exit 1
    ;;
esac
