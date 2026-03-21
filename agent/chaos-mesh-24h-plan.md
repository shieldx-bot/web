# Chaos Mesh 24h Plan (k3s) - Disk Fault + Network Fault

Muc tieu: tao bo du lieu train model du doan va chan doan loi bang cach gay loi co kiem soat trong 24h, tap trung vao cac instance Kubernetes k3s.

## 1) Pham vi va nguyen tac

- Cluster: k3s, Chaos Mesh da cai dat (`chaos-mesh` namespace).
- Target namespace chinh: `backend` (ung dung).
- Observability namespace: `monitoring` (Prometheus, Grafana, Blackbox, CoreDNS metrics).
- Tuong quan theo instance: phan tich metric theo nhan `instance` va `node`.
- Khong chay dong thoi nhieu fault nhe + nang tren cung nhom pod de tranh "data mo".
- Moi scenario gom 3 pha: warm-up (10m) -> injection (20-40m) -> recovery (10m).

## 2) Chon target tap trung vao instance

Gan nhan cho node muon dồn tai:

```bash
kubectl label node <k3s-node-1> chaos-target=true
kubectl label node <k3s-node-2> chaos-target=true
```

Gan nhan cho workload backend (deployment/statefulset):

```yaml
metadata:
  labels:
    chaos-target: "true"
```

Khuyen nghi bo sung `nodeSelector` hoac `nodeAffinity` cho workload de tap trung tren cac node da label `chaos-target=true`.

## 3) Mapping loi -> metric can thu

### Disk Fault

1. I/O Throughput
- `disk_write_bytes/sec`, `disk_read_bytes/sec`
- `disk_write_ops/sec`, `disk_read_ops/sec`

2. Disk Utilization / Saturation
- `Disk_utilization/saturation(%)`
- `I/O await(%)`
- `Queue Length`
- `AVG_qu-sz`

3. Error Metrics
- `disk_error`
- `read/write failure`
- `file system error`

4. Capacity (Disk full)
- `disk_usage(%)`
- `free_space`

5. I/O Latency
- `disk_read_latency`, `disk_write_latency`
- `await (linux iostat)`, `SVCTM`

### Network Fault

1. Delay
- `latency(p95,p90)`, `throughput`, `error rate`

2. Packet loss
- `error rate`, `retry`, `throughput`, `latency (do retry)`

3. Duplicate
- `throughput`, `request_count`, kha nang `double process`

4. Corrupt
- `checksum error rate`, `retry`, `request fault ngau nhien`

5. Bandwidth limit
- `queue`, `latency`, `throughput`

6. Partition
- `request_fault ~100%`, `timeout ~100%`, `zero traffic response`

7. DNS fault
- `request fault tu dau`, `khong connect`, `dns lookup time`

## 4) Lich 24h de train model

- Tong thoi gian: 24h
- Cua so thuc nghiem: 30-60m/case
- Ty le baseline:fault = 40:60

### Time blocks

- 00:00-02:00: Baseline + nhe (delay nho, io latency nho)
- 02:00-04:00: Disk latency + disk read/write fault
- 04:00-06:00: Disk saturation (throughput/io wait/queue)
- 06:00-08:00: Disk full canh bao som (70-85%)
- 08:00-10:00: Delay network tang dan (p90/p95)
- 10:00-12:00: Packet loss theo bac 1%, 3%, 8%, 15%
- 12:00-14:00: Duplicate packet + burst duplicate
- 14:00-16:00: Corrupt packet + random fault
- 16:00-18:00: Bandwidth limit theo profile gio cao diem
- 18:00-20:00: Partition (1 chieu, 2 chieu, intermittent)
- 20:00-22:00: DNS fault (NXDOMAIN/SERVFAIL/timeout)
- 22:00-24:00: Combined mild faults + recovery window dai

## 5) Cac truong hop la de model hoc tot hon

- Delay bat doi xung: chi tang delay egress, ingress binh thuong.
- Loss theo burst: 0% -> 20% trong 2m, sau do ve 1%.
- Duplicate + loss cung luc nhung ngan (5-8m) de tao "edge pattern".
- Corrupt nho nhung keo dai (1-2%) de mo phong NIC loi vat.
- Partition gian doan: 3m down / 2m up lap lai 30m.
- Disk latency chi danh vao `READ` hoac chi danh vao `WRITE`.
- Disk full theo ngat quang: fill nhanh 5m, giai phong 5m, lap lai.

## 6) Bo manifest de chay

Thu muc: `LAB_CENTER/agent/chaos-mesh-manifests/`

- `00-common-labels.yaml`
- `10-disk-iochaos.yaml`
- `11-disk-stress-and-fill.yaml`
- `20-network-chaos.yaml`
- `21-dns-chaos.yaml`
- `30-schedules-24h.yaml`

Ap dung:

```bash
kubectl apply -f LAB_CENTER/agent/chaos-mesh-manifests/
```

Xem trang thai:

```bash
kubectl get iochaos,networkchaos,dnschaos,stresschaos,schedules -n backend
kubectl describe schedule chaos-24h-network-delay -n backend
```

Dung va cleanup:

```bash
kubectl delete -f LAB_CENTER/agent/chaos-mesh-manifests/
```

## 7) Ghi nhan dataset huan luyen

Moi mau du lieu nen co:

- `timestamp`
- `instance`, `node`, `namespace`, `pod`, `container`
- `fault_type` (disk_latency, disk_fault, net_loss, dns_error...)
- `fault_profile` (muc do, huong, burst/intermittent)
- `stage` (warmup|inject|recovery)
- Tat ca metric dau vao da chuan hoa (latency = ms)
- `label_root_cause`
- `label_severity` (low/med/high/critical)

Khuyen nghi windowing cho training:

- Cua so 30s, 60s, 300s (multi-scale)
- Trich xuat them slope/derivative va rolling std

Bo dieu khoan gan nhan fault theo bien thien metric:

- `LAB_CENTER/agent/chaos-labeling-terms.md`
- `LAB_CENTER/agent/chaos-labeling-rules.yaml`

## 8) Kiem soat rui ro

- Dat `mode: fixed-percent` truoc khi chay `mode: all`.
- Start nhe, tang dan intensity.
- Luon co `duration` ro rang cho moi chaos.
- Khong gay fault vao monitoring stack trong cung thoi diem can thu metric.
- Tao 1 `maintenance window` de khoi phuc va xac minh service health.
