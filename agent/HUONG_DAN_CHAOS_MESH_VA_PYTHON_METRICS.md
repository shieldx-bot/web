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
sudo k3s kubectl(){ if command -v k3s >/dev/null 2>&1 && [[ -r /etc/rancher/k3s/k3s.yaml ]]; then sudo k3s kubectl "$@"; else kubectl "$@"; fi; }
sudo k3s kubectl get ns | grep -E "chaos-mesh|monitoring|backend" || true
sudo k3s kubectl get pods -n chaos-mesh
sudo k3s kubectl get pods -n monitoring
```

## 2) Nguyen tac chay quan trong

- Khong `apply` tat ca file network chaos cung luc neu ban test immediate mode.
- Khong chay immediate network (`20-network-chaos.yaml`) dong thoi voi schedule network (`30-schedules-24h.yaml`).
- IOChaos chi inject vao `/mnt/chaos`, khong inject vao root `/`.

## 3) Khoi tao backend + target pod

```bash
sudo k3s kubectl get ns backend >/dev/null 2>&1 || sudo k3s kubectl create ns backend
sudo k3s kubectl label ns backend chaos-injection=enabled --overwrite

sudo k3s kubectl apply -f ./chaos-mesh-manifests/00-common-labels.yaml
sudo k3s kubectl apply -f ./chaos-mesh-manifests/01-chaos-target-nginx.yaml
sudo k3s kubectl rollout status deploy/chaos-target-nginx -n backend --timeout=120s
sudo k3s kubectl get pods -n backend -l chaos-target=true
```

## 4) Chay 24h schedule mode (khuyen nghi)

Day la mode on dinh nhat de thu du lieu dai han:

```bash
sudo k3s kubectl apply -f ./chaos-mesh-manifests/30-schedules-24h.yaml
sudo k3s kubectl get schedules -n backend
sudo k3s kubectl get iochaos,networkchaos,dnschaos,stresschaos -n backend
```

## 5) Chay immediate mode de test nhanh

### 5.1 Disk test

```bash
sudo k3s kubectl apply -f ./chaos-mesh-manifests/10-disk-iochaos.yaml
sudo k3s kubectl describe iochaos disk-latency-read-write -n backend | egrep "Type:|Status:|Failed|Applied"
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
sudo k3s kubectl delete networkchaos --all -n backend --ignore-not-found
for r in $(sudo k3s kubectl get networkchaos -n backend -o name); do
  sudo k3s kubectl patch -n backend "$r" --type=json -p='[{"op":"remove","path":"/metadata/finalizers"}]' || true
done
sudo k3s kubectl rollout restart ds/chaos-daemon -n chaos-mesh
sudo k3s kubectl rollout status ds/chaos-daemon -n chaos-mesh --timeout=120s
```

### 6.2 `path is the root`

Nguyen nhan: IOChaos inject vao root filesystem.

File hien tai da dung path an toan:
- `volumePath: /mnt/chaos`
- `path: /mnt/chaos/*`

### 6.3 `no pod is selected`

Kiem tra target:

```bash
sudo k3s kubectl get pods -n backend -l chaos-target=true
```

Neu khong co pod nao, apply lai `01-chaos-target-nginx.yaml`.

## 7) Thu metric va gan nhan moi 30s

```bash
source /home/shieldx/Documents/Github/lab-mechine-learning/env/bin/activate
pip install requests pyyaml pandas

python ./main.py \
  --prom-url http://localhost:9090 \
  --start now-45m \
  --end now \
  --step 30s \
  --rules ./chaos-labeling-rules.yaml \
  --output ./chaos_labeled_30s.csv
```

Luu y: Co the dung ISO8601 (`2026-03-21T15:40:00+07:00`) hoac dang tuong doi (`now-45m`, `now-2h`, `now-1d`, `now`).

Output se gom cot metric + cot label:
- `label_root_cause`
- `label_severity`
- `label_confidence`
- `matched_rules`
- `is_mixed`

## 8) Cleanup an toan

```bash
sudo k3s kubectl delete -f ./chaos-mesh-manifests/30-schedules-24h.yaml --ignore-not-found
sudo k3s kubectl delete -f ./chaos-mesh-manifests/21-dns-chaos.yaml --ignore-not-found
sudo k3s kubectl delete -f ./chaos-mesh-manifests/20-network-chaos.yaml --ignore-not-found
sudo k3s kubectl delete -f ./chaos-mesh-manifests/11-disk-stress-and-fill.yaml --ignore-not-found
sudo k3s kubectl delete -f ./chaos-mesh-manifests/10-disk-iochaos.yaml --ignore-not-found
```

Neu can xoa manh network chaos dang ket finalizer, dung them block o muc `6.1`.
