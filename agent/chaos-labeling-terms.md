# Chaos Labeling Terms (24h Metrics)

Muc tieu: gan nhan fault dua tren bien thien metric theo tung window size sau khi thu du lieu 24h.

## 1) Window size va feature

Dung 3 window song song:

- `w30 = 30s`: bat su kien nhanh, burst, spike
- `w60 = 60s`: can bang giua nhay va on dinh
- `w300 = 300s`: xu huong ben vung, sustained fault

Feature tinh cho moi metric `x` tai thoi diem `t`:

- `mu_w(x)`: rolling mean tren cua so `w`
- `sigma_w(x)`: rolling std tren cua so `w`
- `z_w(x) = (x_t - mu_w) / max(sigma_w, eps)`
- `delta_w(x) = (x_t - mu_w) / max(abs(mu_w), eps)`
- `slope_w(x) = d(x)/dt` tren `w`

`eps = 1e-9` de tranh chia cho 0.

## 2) Baseline 24h

- Baseline khoi tao: 00:00-02:00 (block baseline trong plan 24h).
- Cap nhat baseline theo gio, nhung bo qua khung dang inject fault.
- Neu co nhieu instance: baseline tinh rieng cho tung `instance`.

## 3) Taxonomy label

`label_root_cause`:

- `normal`
- `disk_latency`
- `disk_saturation`
- `disk_error`
- `disk_capacity`
- `net_delay`
- `net_loss`
- `net_duplicate`
- `net_corrupt`
- `net_bandwidth_limit`
- `net_partition`
- `dns_fault`
- `mixed_fault`
- `unknown_anomaly`

`label_severity`:

- `low`
- `medium`
- `high`
- `critical`

## 4) Dieu khoan gan nhan theo fault type

Dieu kien co hieu luc khi it nhat 2/3 windows (`30s`, `60s`, `300s`) dong y, tru fault "hard".

### 4.1 Hard fault (uu tien cao)

1. `net_partition`
- `zero_traffic == 1` va
- `request_fault` tang manh (`z60 > 3`) va
- `timeout` tang manh (`z60 > 3`)
- Neu dung > 120s -> `critical`

2. `dns_fault`
- `dns_probe_success == 0` hoac
- (`dns_failure_rate z60 > 3` va `dns_lookup_time_ms z60 > 2`)

3. `disk_error`
- `disk_read_errors_rate > 0` hoac `disk_write_errors_rate > 0` hoac
- `container_fs_reads_failed_rate > 0` hoac `container_fs_writes_failed_rate > 0`
- Neu keo dai > 5m -> it nhat `high`

### 4.2 Disk soft fault

1. `disk_latency`
- `read_latency_ms z60 > 2` hoac `write_latency_ms z60 > 2`
- va `await_ms z60 > 2`
- va `svctm_ms z300 > 1`

2. `disk_saturation`
- `disk_util_percent > 80` hoac `disk_util_percent z300 > 2`
- va `io_wait_percent z60 > 2`
- va (`queue_length z60 > 2` hoac `avg_qu_sz z300 > 2`)

3. `disk_capacity`
- `disk_usage_percent > 85` va `free_space` giam (`slope300 < 0`)
- `disk_usage_percent > 92` -> toi thieu `high`
- `disk_usage_percent > 97` -> `critical`

### 4.3 Network soft fault

1. `net_delay`
- `latency_p95_ms z60 > 2` va `latency_p90_ms z60 > 2`
- throughput khong giam manh (de phan biet voi bandwidth/partition): `throughput delta60 > -0.4`

2. `net_loss`
- `packet_loss_percent z60 > 2` hoac `drop_rate z60 > 2`
- va `retry_rate z60 > 2`
- va `latency_ms z60 > 1`

3. `net_duplicate`
- `duplicate_ratio_percent z60 > 2`
- va `request_count z60 >= 0`
- va `double_process_rate z60 > 1` (neu co metric nay)

4. `net_corrupt`
- `checksum_error_rate z60 > 2`
- va (`retry_rate z60 > 1` hoac `request_fault z60 > 1`)

5. `net_bandwidth_limit`
- `bandwidth_util_percent > 85` hoac `throughput_plateau z300 < nguong_nho`
- va (`queue_length z60 > 2` hoac `tcp_send_queue z60 > 2`)
- va `latency_rtt_ms z60 > 1`

## 5) Quy tac mixed va unknown

- `mixed_fault`: tu 2 fault tro len cung dat dieu kien trong cung 1 cua so 5 phut.
- `unknown_anomaly`: khong dat rule fault nao nhung tong anomaly score cao.

Tong anomaly score goi y:

`A = mean(clip(abs(z60), 0, 6))` tren tap metric chinh.

- Neu `A >= 2.5` va khong map duoc root cause -> `unknown_anomaly`.

## 6) Dieu khoan severity

Tinh `impact_score` (0-100):

- 40% tu latency/timeout impact
- 30% tu error/failure impact
- 20% tu throughput drop impact
- 10% tu duration impact

Map severity:

- `< 25` -> `low`
- `25-50` -> `medium`
- `50-75` -> `high`
- `>= 75` -> `critical`

Override:

- `net_partition` co `zero_traffic` > 120s -> `critical`
- `disk_usage_percent >= 97` -> `critical`
- bat ky `disk_error` lien tuc > 10m -> it nhat `high`

## 7) Chuan hoa theo window

De giam noise cho `30s`, tang threshold z-score:

- `w30`: threshold = `1.3 * threshold_mac_dinh`
- `w60`: threshold = `1.0 * threshold_mac_dinh`
- `w300`: threshold = `0.8 * threshold_mac_dinh`

Va quy tac dong thuan:

- Label hop le khi co it nhat 2/3 windows dong y
- Rieng hard fault (`partition`, `dns_fault`, `disk_error`) chi can 1 window + duy tri >= 2 mau lien tiep

## 8) Mau output label cho moi row

- `timestamp`
- `instance`
- `window_size`
- `label_root_cause`
- `label_severity`
- `label_confidence` (0-1)
- `matched_rules` (list rule id)
- `is_mixed` (0/1)

`label_confidence` goi y:

- 0.9-1.0: hard fault
- 0.7-0.89: soft fault + 3/3 windows dong y
- 0.5-0.69: soft fault + 2/3 windows dong y
- <0.5: unknown
