# Huong Dan Su Dung Chaos Mesh Va Python Metrics

Tai lieu nay la ban huong dan da duoc toi uu theo ket qua test local.
Muc tieu:

1. Chay chaos an toan, khong bi xung dot network tc/ipset.
2. Thu metric Prometheus moi 30s.
3. Gan nhan theo rule va xuat CSV.

## 1) Dieu kien tien quyet

- Da co Kubernetes cluster va truy cap duoc bang `kubectl` hoac `sudo k3s kubectl`.
- Da cai Chaos Mesh (`chaos-mesh` namespace).
- Da co monitoring (`monitoring` namespace), co Prometheus.
- Trong namespace `backend` co pod target label `chaos-target=true`.

Kiem tra nhanh:

```bash
kctl(){ if command -v k3s >/dev/null 2>&1 && [[ -r /etc/rancher/k3s/k3s.yaml ]]; then sudo k3s kubectl "$@"; else kubectl "$@"; fi; }
kctl get ns | grep -E "chaos-mesh|monitoring|backend" || true
kctl get pods -n chaos-mesh
kctl get pods -n monitoring
```

## 2) Nguyen tac chay quan trong

- Khong `apply` tat ca file network chaos cung luc neu ban test immediate mode.
- Khong chay immediate network (`20-network-chaos.yaml`) dong thoi voi schedule network (`30-schedules-24h.yaml`).
- IOChaos chi inject vao `/mnt/chaos`, khong inject vao root `/`.

## 3) Khoi tao backend + target pod

```bash
kctl get ns backend >/dev/null 2>&1 || kctl create ns backend
kctl label ns backend chaos-injection=enabled --overwrite

kctl apply -f ./chaos-mesh-manifests/00-common-labels.yaml
kctl apply -f ./chaos-mesh-manifests/01-chaos-target-nginx.yaml
kctl rollout status deploy/chaos-target-nginx -n backend --timeout=120s
kctl get pods -n backend -l chaos-target=true
```

## 4) Chay 24h schedule mode (khuyen nghi)

Day la mode on dinh nhat de thu du lieu dai han:

```bash
kctl apply -f ./chaos-mesh-manifests/30-schedules-24h.yaml
kctl get schedules -n backend
kctl get iochaos,networkchaos,dnschaos,stresschaos -n backend
```

## 5) Chay immediate mode de test nhanh

### 5.1 Disk test

```bash
kctl apply -f ./chaos-mesh-manifests/10-disk-iochaos.yaml
kctl describe iochaos disk-latency-read-write -n backend | egrep "Type:|Status:|Failed|Applied"
```

Ky vong: `Selected=True`, `AllInjected=True`, khong co `path is the root`.

### 5.2 Network test (serial)

Khuyen nghi dung script serial:

```bash
chmod +x ./chaos-mesh-manifests/22-network-chaos-serial.sh
./chaos-mesh-manifests/22-network-chaos-serial.sh
```

Script nay tu dong uu tien `sudo k3s kubectl` neu phat hien moi truong k3s, va chay tung fault mot de tranh xung dot netem tree.

## 6) Xu ly loi thuong gap

### 6.1 `unable to set tcs` hoac `unable to flush ip sets`

Nguyen nhan pho bien: network faults chong len nhau hoac resource bi ket finalizer.

Xu ly nhanh:

```bash
kctl delete networkchaos --all -n backend --ignore-not-found
for r in $(kctl get networkchaos -n backend -o name); do
  kctl patch -n backend "$r" --type=json -p='[{"op":"remove","path":"/metadata/finalizers"}]' || true
done
kctl rollout restart ds/chaos-daemon -n chaos-mesh
kctl rollout status ds/chaos-daemon -n chaos-mesh --timeout=120s
```

### 6.2 `path is the root`

Nguyen nhan: IOChaos inject vao root filesystem.

File hien tai da dung path an toan:
- `volumePath: /mnt/chaos`
- `path: /mnt/chaos/*`

### 6.3 `no pod is selected`

Kiem tra target:

```bash
kctl get pods -n backend -l chaos-target=true
```

Neu khong co pod nao, apply lai `01-chaos-target-nginx.yaml`.

## 7) Thu metric va gan nhan moi 30s

```bash
source /home/shieldx/Documents/Github/lab-mechine-learning/env/bin/activate
pip install requests pyyaml pandas

python ./main.py \
  --prom-url http://localhost:9090 \
  --start 2026-03-21T15:40:00 \
  --end 2026-03-21T16:10:00 \
  --step 30s \
  --rules ./chaos-labeling-rules.yaml \
  --output ./chaos_labeled_30s.csv
```

Luu y: Neu `--start/--end` khong co timezone (khong co `Z` hoac `+07:00`) thi script se hieu theo gio local cua server.

Output se gom cot metric + cot label:
- `label_root_cause`
- `label_severity`
- `label_confidence`
- `matched_rules`
- `is_mixed`

## 8) Cleanup an toan

```bash
kctl delete -f ./chaos-mesh-manifests/30-schedules-24h.yaml --ignore-not-found
kctl delete -f ./chaos-mesh-manifests/21-dns-chaos.yaml --ignore-not-found
kctl delete -f ./chaos-mesh-manifests/20-network-chaos.yaml --ignore-not-found
kctl delete -f ./chaos-mesh-manifests/11-disk-stress-and-fill.yaml --ignore-not-found
kctl delete -f ./chaos-mesh-manifests/10-disk-iochaos.yaml --ignore-not-found
```

Neu can xoa manh network chaos dang ket finalizer, dung them block o muc `6.1`.
