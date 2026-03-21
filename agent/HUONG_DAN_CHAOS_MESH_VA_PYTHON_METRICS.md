# Huong Dan Chay Chaos Mesh Va Python Metrics

Tai lieu nay huong dan end-to-end:

1. Chuan bi cluster k3s + Chaos Mesh + monitoring
2. Chay ke hoach chaos 24h
3. Thu metric tu Prometheus moi 30s
4. Gan nhan label theo bo rule
5. Xuat dataset CSV

## 1) Dieu kien tien quyet

- Da co cluster `k3s`.
- Da cai `Chaos Mesh` (namespace `chaos-mesh`).
- Da co stack monitoring (Prometheus + Grafana) trong namespace `monitoring`.
- Co quyen `kubectl` vao cluster.
- Python environment san sang trong workspace.

Kiem tra nhanh:

```bash
kubectl get ns
kubectl get pods -n chaos-mesh
kubectl get pods -n monitoring
```

## 2) Cac file su dung

- Ke hoach 24h: `LAB_CENTER/agent/chaos-mesh-24h-plan.md`
- Manifest chaos: `LAB_CENTER/agent/chaos-mesh-manifests/`
- Dieu khoan label: `LAB_CENTER/agent/chaos-labeling-terms.md`
- Rule label YAML: `LAB_CENTER/agent/chaos-labeling-rules.yaml`
- Script Python metric + label: `LAB_CENTER/agent/main.py`

## 3) Mo dashboard quan sat

```bash
kubectl port-forward svc/my-grafana 3000:80 -n monitoring
kubectl port-forward svc/chaos-dashboard 2333:30329 -n chaos-mesh
```

Neu dung pod port-forward:

```bash
sudo k3s kubectl port-forward pod/chaos-dashboard-6b9c9c6ff7-95d57 8080:2333 -n chaos-mesh --address 0.0.0.0
sudo k3s kubectl port-forward pod/my-grafana-786d99cb8d-d4lh6 3000:3000 -n monitoring --address 0.0.0.0
```

## 4) Gan target vao node/pod can inject

Gan nhan node de dồn tai chaos:

```bash
kubectl label node <k3s-node-1> chaos-target=true
kubectl label node <k3s-node-2> chaos-target=true
```

Dam bao workload trong `backend` co label:

- `chaos-target=true`

Va (neu can) dependency service co label:

- `role=dependency`

## 5) Chay chaos plan 24h

Apply toan bo manifest:

```bash
kubectl apply -f LAB_CENTER/agent/chaos-mesh-manifests/
```

Kiem tra trang thai chaos object:

```bash
kubectl get iochaos,networkchaos,dnschaos,stresschaos,schedules -n backend
kubectl describe schedule chaos-24h-network-delay -n backend
```

## 6) Chuan bi Python environment

Kich hoat env:

```bash
source env/bin/activate
```

Cai package can thiet:

```bash
pip install requests pyyaml pandas
```

## 7) Thu metric va gan nhan moi 30s

Script se:

- Goi Prometheus `/api/v1/query_range` theo `--step 30s`
- Tao 1 dong moi `timestamp + instance`
- Moi cot la metric (va feature rolling)
- Gan nhan theo `chaos-labeling-rules.yaml`
- Xuat CSV label

Lenh chay mau 24h:

```bash
python LAB_CENTER/agent/main.py \
  --prom-url http://localhost:9090 \
  --start 2026-03-20T00:00:00 \
  --end 2026-03-21T00:00:00 \
  --step 30s \
  --rules LAB_CENTER/agent/chaos-labeling-rules.yaml \
  --output LAB_CENTER/agent/chaos_labeled_30s.csv
```

## 8) Dinh dang output CSV

Cac cot label chinh:

- `timestamp`
- `instance`
- `window_size` (co dinh `30s`)
- `label_root_cause`
- `label_severity`
- `label_confidence`
- `matched_rules`
- `is_mixed`

Cac cot con lai:

- Toan bo metric
- Feature rolling cho `w30/w60/w300`: `mu`, `z`, `delta`, `slope`

## 9) Dung va cleanup sau khi thu du lieu

```bash
kubectl delete -f LAB_CENTER/agent/chaos-mesh-manifests/
```

## 10) Loi thuong gap

1. Khong lay duoc metric tu Prometheus
- Kiem tra URL `--prom-url`
- Kiem tra Prometheus co metric hay khong
- Thu test API:

```bash
curl "http://localhost:9090/api/v1/query?query=up"
```

2. Loi Python import `requests` hoac `yaml`
- Cai lai package:

```bash
pip install requests pyyaml pandas
```

3. File CSV trong
- Kiem tra thoi gian `--start --end`
- Kiem tra metric ton tai trong cluster hien tai
- Kiem tra namespace monitoring exporters da chay

4. Chaos khong inject vao pod mong muon
- Kiem tra label `chaos-target=true`
- Kiem tra namespace selector trong manifest
- Kiem tra `role=dependency` doi voi test partition
