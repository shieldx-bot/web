#!/usr/bin/env python3
"""Fetch Prometheus metrics and label each 30s window using chaos rules.

Example:
  python LAB_CENTER/agent/main.py \
	--prom-url http://localhost:9090 \
	--start 2026-03-20T00:00:00 \
	--end 2026-03-21T00:00:00 \
	--step 30s \
	--rules LAB_CENTER/agent/chaos-labeling-rules.yaml \
	--output LAB_CENTER/agent/chaos_labeled_30s.csv
"""

from __future__ import annotations

import argparse
import math
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import pandas as pd
import requests
import yaml


DEFAULT_METRIC_QUERIES: Dict[str, str] = {
	# Disk metrics
	"disk_read_latency_ms": "1000 * (rate(node_disk_read_time_seconds_total[5m]) / rate(node_disk_reads_completed_total[5m]))",
	"disk_write_latency_ms": "1000 * (rate(node_disk_write_time_seconds_total[5m]) / rate(node_disk_writes_completed_total[5m]))",
	"disk_await_ms": "1000 * (rate(node_disk_read_time_seconds_total[5m]) + rate(node_disk_write_time_seconds_total[5m])) / (rate(node_disk_reads_completed_total[5m]) + rate(node_disk_writes_completed_total[5m]))",
	"disk_svctm_ms": "1000 * (rate(node_disk_io_time_seconds_total[5m]) / (rate(node_disk_reads_completed_total[5m]) + rate(node_disk_writes_completed_total[5m])))",
	"disk_util_percent": "100 * rate(node_disk_io_time_seconds_total[5m])",
	"io_wait_percent": "100 * (sum by (instance) (rate(node_cpu_seconds_total{mode=\"iowait\"}[5m])) / sum by (instance) (rate(node_cpu_seconds_total[5m])))",
	"queue_length": "node_disk_io_now",
	"avg_qu_sz": "avg_over_time(node_disk_io_now[5m])",
	"disk_read_errors_rate": "rate(node_disk_read_errors_total[5m])",
	"disk_write_errors_rate": "rate(node_disk_write_errors_total[5m])",
	"container_reads_failed_rate": "rate(container_fs_reads_failed_total{namespace=\"monitoring\"}[5m])",
	"container_writes_failed_rate": "rate(container_fs_writes_failed_total{namespace=\"monitoring\"}[5m])",
	"disk_usage_percent": "100 * (sum by (instance) (node_filesystem_size_bytes{fstype!~\"tmpfs|squashfs|overlay|devtmpfs\"} - node_filesystem_free_bytes{fstype!~\"tmpfs|squashfs|overlay|devtmpfs\"}) / sum by (instance) (node_filesystem_size_bytes{fstype!~\"tmpfs|squashfs|overlay|devtmpfs\"}))",
	"free_space": "sum by (instance) (node_filesystem_avail_bytes{fstype!~\"tmpfs|squashfs|overlay|devtmpfs\"})",
	# Network metrics
	"request_fault": "sum by (instance) (rate(node_netstat_Tcp_RetransSegs[5m]) + rate(node_netstat_Tcp_InErrs[5m]) + rate(node_netstat_Tcp_OutRsts[5m]))",
	"timeout_total": "sum by (instance) (rate(node_netstat_Tcp_AttemptFails[5m]) + rate(node_netstat_Tcp_EstabResets[5m]))",
	"zero_traffic": "(sum by (instance) (rate(node_network_receive_bytes_total[5m])) == 0) * (sum by (instance) (rate(node_network_transmit_bytes_total[5m])) == 0)",
	"net_latency_p90_ms": "1000 * histogram_quantile(0.90, sum by (le) (rate(probe_http_duration_seconds_bucket[5m])))",
	"net_latency_p95_ms": "1000 * histogram_quantile(0.95, sum by (le) (rate(probe_http_duration_seconds_bucket[5m])))",
	"net_throughput": "sum by (instance) (rate(node_network_receive_bytes_total[5m]) + rate(node_network_transmit_bytes_total[5m]))",
	"drop_rate": "sum by (instance) (rate(node_network_receive_drop_total[5m]) + rate(node_network_transmit_drop_total[5m]))",
	"packet_loss_percent": "100 * sum by (instance) (rate(node_network_receive_drop_total[5m]) + rate(node_network_transmit_drop_total[5m])) / sum by (instance) (rate(node_network_receive_packets_total[5m]) + rate(node_network_transmit_packets_total[5m]))",
	"retry_rate": "rate(node_netstat_Tcp_RetransSegs[5m])",
	"net_latency_ms": "avg by (instance) (1000 * node_tcp_rtt_seconds)",
	"duplicate_ratio_percent": "100 * sum by (instance) (rate(node_netstat_Tcp_DSACKs[5m]) + rate(node_netstat_Tcp_DupAcks[5m])) / sum by (instance) (rate(node_netstat_Tcp_InSegs[5m]) + rate(node_netstat_Tcp_OutSegs[5m]))",
	"request_count": "sum by (instance) (rate(node_netstat_Tcp_InSegs[5m]) + rate(node_netstat_Tcp_OutSegs[5m]))",
	"checksum_error_rate": "sum by (instance) (rate(node_network_receive_crc_errors_total[5m]) + rate(node_network_receive_frame_errors_total[5m]) + rate(node_netstat_Tcp_InCsumErrors[5m]) + rate(node_netstat_Udp_InCsumErrors[5m]))",
	"bandwidth_util_percent": "100 * sum by (instance) (rate(node_network_receive_bytes_total[5m]) + rate(node_network_transmit_bytes_total[5m])) / 125000000",
	"throughput_plateau": "abs(deriv((sum by (instance) (rate(node_network_receive_bytes_total[5m]) + rate(node_network_transmit_bytes_total[5m])))[5m:30s]))",
	"net_queue_length": "avg by (instance) (node_network_transmit_queue_length + node_network_receive_queue_length)",
	"tcp_send_queue": "avg by (instance) (node_netstat_Tcp_SendQueueSize)",
	"net_rtt_ms": "avg by (instance) (1000 * node_tcp_rtt_seconds)",
	# DNS metrics
	"dns_probe_success": "probe_success{job=\"blackbox\", probe=\"dns\"}",
	"dns_failure_rate": "rate(probe_failed_total{job=\"blackbox\", probe=\"dns\"}[5m])",
	"dns_lookup_time_ms": "1000 * avg(probe_duration_seconds{job=\"blackbox\", probe=\"dns\"})",
}


CRITICAL_METRICS_FOR_LABELING = [
	"dns_probe_success",
	"dns_failure_rate",
	"net_latency_p95_ms",
	"zero_traffic",
]


@dataclass
class RuleHit:
	rule_id: str
	label: str
	hard_fault: bool


def parse_args() -> argparse.Namespace:
	parser = argparse.ArgumentParser(description="Fetch Prometheus metrics and label 30s windows")
	parser.add_argument("--prom-url", required=True, help="Prometheus base URL, ex: http://localhost:9090")
	parser.add_argument("--start", help="Start time ISO8601 or epoch seconds")
	parser.add_argument("--end", help="End time ISO8601 or epoch seconds")
	parser.add_argument("--step", default="30s", help="Query step, default 30s")
	parser.add_argument(
		"--rules",
		default="LAB_CENTER/agent/chaos-labeling-rules.yaml",
		help="Path to YAML rules",
	)
	parser.add_argument(
		"--output",
		default="LAB_CENTER/agent/chaos_labeled_30s.csv",
		help="CSV output file",
	)
	parser.add_argument(
		"--timeout",
		type=int,
		default=120,
		help="HTTP timeout in seconds for each Prometheus call",
	)
	return parser.parse_args()


def parse_time(value: Optional[str], default_dt: datetime) -> datetime:
	if not value:
		return default_dt
	value = value.strip()
	if value == "now":
		return datetime.now().astimezone().astimezone(timezone.utc)
	# Relative format: now-45m, now-2h, now-1d
	match = re.fullmatch(r"now-(\d+)([mhd])", value)
	if match:
		amount = int(match.group(1))
		unit = match.group(2)
		now_local = datetime.now().astimezone()
		if unit == "m":
			dt = now_local - timedelta(minutes=amount)
		elif unit == "h":
			dt = now_local - timedelta(hours=amount)
		else:
			dt = now_local - timedelta(days=amount)
		return dt.astimezone(timezone.utc)
	if value.isdigit():
		return datetime.fromtimestamp(int(value), tz=timezone.utc)
	dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
	if dt.tzinfo is None:
		# If user provides no timezone, interpret it as local server time.
		# This is more intuitive for operational commands typed on the server.
		local_tz = datetime.now().astimezone().tzinfo or timezone.utc
		dt = dt.replace(tzinfo=local_tz)
	return dt.astimezone(timezone.utc)


def resolve_existing_path(path_str: str) -> Path:
	"""Resolve path with a practical fallback to current working directory.

	Examples:
	- LAB_CENTER/agent/chaos-labeling-rules.yaml (repo root)
	- ./chaos-labeling-rules.yaml (agent dir)
	"""
	p = Path(path_str)
	if p.exists():
		return p

	# Fallback: if only basename exists in cwd, use it.
	alt = Path(p.name)
	if alt.exists():
		print(f"[WARN] Path not found: {p}. Using {alt} instead.")
		return alt

	return p


def prometheus_query_range(
	prom_url: str,
	query: str,
	start: datetime,
	end: datetime,
	step: str,
	timeout: int,
) -> List[Dict[str, Any]]:
	url = prom_url.rstrip("/") + "/api/v1/query_range"
	params = {
		"query": query,
		"start": f"{start.timestamp():.0f}",
		"end": f"{end.timestamp():.0f}",
		"step": step,
	}
	response = requests.get(url, params=params, timeout=timeout)
	response.raise_for_status()
	payload = response.json()
	if payload.get("status") != "success":
		raise RuntimeError(f"Prometheus API error: {payload}")
	return payload.get("data", {}).get("result", [])


def metric_alias_map_from_rules(rules_cfg: Dict[str, Any]) -> List[str]:
	aliases: set[str] = set()

	def collect(node: Any) -> None:
		if isinstance(node, dict):
			metric = node.get("metric")
			if metric:
				aliases.add(metric)
			for key in ("all_of", "any_of"):
				if key in node:
					for child in node[key]:
						collect(child)
		elif isinstance(node, list):
			for item in node:
				collect(item)

	for rule in rules_cfg.get("rules", []):
		collect(rule)
	return sorted(aliases)


def fetch_all_metrics(
	prom_url: str,
	alias_to_query: Dict[str, str],
	start: datetime,
	end: datetime,
	step: str,
	timeout: int,
) -> pd.DataFrame:
	rows: List[Dict[str, Any]] = []
	failed_metrics: List[str] = []
	for alias, promql in alias_to_query.items():
		try:
			result = prometheus_query_range(prom_url, promql, start, end, step, timeout)
		except requests.HTTPError as exc:
			failed_metrics.append(alias)
			resp_text = ""
			if exc.response is not None:
				resp_text = exc.response.text.strip()
			print(f"[WARN] Skip metric '{alias}' due to HTTP error: {exc}")
			if resp_text:
				print(f"[WARN] Prometheus response: {resp_text}")
			continue
		except requests.RequestException as exc:
			failed_metrics.append(alias)
			print(f"[WARN] Skip metric '{alias}' due to request error: {exc}")
			continue
		for series in result:
			metric_labels = series.get("metric", {})
			instance = metric_labels.get("instance") or metric_labels.get("pod") or "cluster"
			for ts_raw, val_raw in series.get("values", []):
				try:
					val = float(val_raw)
				except (TypeError, ValueError):
					val = math.nan
				rows.append(
					{
						"timestamp": pd.to_datetime(float(ts_raw), unit="s", utc=True),
						"instance": instance,
						"metric": alias,
						"value": val,
					}
				)

	if failed_metrics:
		print(f"[WARN] Failed metrics count: {len(failed_metrics)} | {', '.join(sorted(failed_metrics))}")

	if not rows:
		raise RuntimeError("No metric data returned from Prometheus")

	long_df = pd.DataFrame(rows)
	# In case a query still returns multiple series for one instance/timestamp, average them.
	grouped = (
		long_df.groupby(["timestamp", "instance", "metric"], as_index=False)["value"]
		.mean()
		.sort_values(["timestamp", "instance", "metric"])
	)
	wide_df = grouped.pivot(index=["timestamp", "instance"], columns="metric", values="value").reset_index()
	wide_df.columns.name = None
	return wide_df.sort_values(["timestamp", "instance"]).reset_index(drop=True)


def _rolling_std(series: pd.Series, window: int) -> pd.Series:
	return series.rolling(window=window, min_periods=1).std(ddof=0).fillna(0.0)


def add_features(df: pd.DataFrame, windows: Dict[str, int], eps: float) -> pd.DataFrame:
	out = df.copy()
	metric_cols = [c for c in out.columns if c not in {"timestamp", "instance"}]

	for metric in metric_cols:
		for w_name, w_rows in windows.items():
			grp = out.groupby("instance")[metric]
			mu = grp.transform(lambda s: s.rolling(window=w_rows, min_periods=1).mean())
			sd = grp.transform(lambda s: _rolling_std(s, w_rows))
			slope = grp.transform(lambda s: s.diff() / max(w_rows * 30, 1))
			z = (out[metric] - mu) / sd.clip(lower=eps)
			delta = (out[metric] - mu) / mu.abs().clip(lower=eps)
			out[f"{metric}__mu_{w_name}"] = mu
			out[f"{metric}__z_{w_name}"] = z
			out[f"{metric}__delta_{w_name}"] = delta
			out[f"{metric}__slope_{w_name}"] = slope.fillna(0.0)
	return out


def get_metric_value(row: pd.Series, metric: str) -> float:
	val = row.get(metric)
	if pd.isna(val):
		return float("nan")
	return float(val)


def get_feature_value(row: pd.Series, metric: str, kind: str, window_name: str) -> float:
	key = f"{metric}__{kind}_{window_name}"
	val = row.get(key)
	if pd.isna(val):
		return float("nan")
	return float(val)


def evaluate_atomic(row: pd.Series, cond: Dict[str, Any], default_window: str) -> bool:
	metric = cond["metric"]
	op = cond["op"]
	value = float(cond.get("value", 0))
	w_name = cond.get("window", default_window)

	if op in {"eq", "gt", "ge"}:
		x = get_metric_value(row, metric)
	elif op in {"z_gt", "delta_gt", "slope_lt", "abs_lt"}:
		if op == "z_gt":
			x = get_feature_value(row, metric, "z", w_name)
		elif op == "delta_gt":
			x = get_feature_value(row, metric, "delta", w_name)
		elif op == "slope_lt":
			x = get_feature_value(row, metric, "slope", w_name)
		else:
			x = get_metric_value(row, metric)
	else:
		return False

	if math.isnan(x):
		return False
	if op == "eq":
		return math.isclose(x, value, rel_tol=0.0, abs_tol=1e-9)
	if op == "gt":
		return x > value
	if op == "ge":
		return x >= value
	if op == "z_gt":
		return x > value
	if op == "delta_gt":
		return x > value
	if op == "slope_lt":
		return x < value
	if op == "abs_lt":
		return abs(x) < value
	return False


def evaluate_condition_tree(row: pd.Series, node: Dict[str, Any], default_window: str) -> bool:
	if "all_of" in node:
		return all(evaluate_condition_tree(row, c, default_window) for c in node["all_of"])
	if "any_of" in node:
		return any(evaluate_condition_tree(row, c, default_window) for c in node["any_of"])
	return evaluate_atomic(row, node, default_window)


def has_missing_critical_metrics(row: pd.Series, metric_names: Iterable[str]) -> bool:
	for metric in metric_names:
		val = row.get(metric)
		if pd.isna(val):
			return True
	return False


def apply_rules(df: pd.DataFrame, rules_cfg: Dict[str, Any]) -> pd.DataFrame:
	out = df.copy()
	labels: List[str] = []
	severities: List[str] = []
	confidences: List[float] = []
	matched_rules_list: List[str] = []
	is_mixed_list: List[int] = []

	rule_defs = rules_cfg.get("rules", [])
	default_window = "w60"

	for _, row in out.iterrows():
		hits: List[RuleHit] = []
		for rule in rule_defs:
			if evaluate_condition_tree(row, rule, default_window):
				hits.append(RuleHit(rule_id=rule["id"], label=rule["label"], hard_fault=bool(rule.get("hard_fault", False))))

		labels_hit = sorted({h.label for h in hits})
		hard_hit = any(h.hard_fault for h in hits)

		if not labels_hit:
			if has_missing_critical_metrics(row, CRITICAL_METRICS_FOR_LABELING):
				label = "insufficient_data"
				confidence = 0.2
			else:
				label = "normal"
				confidence = 0.4
			is_mixed = 0
		elif len(labels_hit) >= 2:
			label = "mixed_fault"
			confidence = 0.8 if hard_hit else 0.7
			is_mixed = 1
		else:
			label = labels_hit[0]
			confidence = 0.95 if hard_hit else 0.75
			is_mixed = 0

		severity = infer_severity(row, label)
		labels.append(label)
		severities.append(severity)
		confidences.append(confidence)
		matched_rules_list.append(",".join(sorted({h.rule_id for h in hits})))
		is_mixed_list.append(is_mixed)

	out["window_size"] = "30s"
	out["label_root_cause"] = labels
	out["label_severity"] = severities
	out["label_confidence"] = confidences
	out["matched_rules"] = matched_rules_list
	out["is_mixed"] = is_mixed_list
	return out


def infer_severity(row: pd.Series, label: str) -> str:
	if label in {"normal", "insufficient_data"}:
		return "low"

	# Simple practical severity scoring from available metrics.
	latency_terms = [
		abs(float(row.get("net_latency_p95_ms", 0) or 0)),
		abs(float(row.get("disk_await_ms", 0) or 0)),
	]
	error_terms = [
		abs(float(row.get("request_fault", 0) or 0)),
		abs(float(row.get("disk_read_errors_rate", 0) or 0)),
		abs(float(row.get("disk_write_errors_rate", 0) or 0)),
	]
	throughput_penalty = max(0.0, -float(row.get("net_throughput__delta_w60", 0) or 0))
	usage = float(row.get("disk_usage_percent", 0) or 0)

	score = 0.0
	score += min(40.0, sum(latency_terms) / 20.0)
	score += min(30.0, sum(error_terms) * 10.0)
	score += min(20.0, throughput_penalty * 50.0)
	score += min(10.0, max(0.0, usage - 70.0) / 3.0)

	if label == "net_partition" and float(row.get("zero_traffic", 0) or 0) >= 1:
		return "critical"
	if usage >= 97.0:
		return "critical"

	if score >= 75:
		return "critical"
	if score >= 50:
		return "high"
	if score >= 25:
		return "medium"
	return "low"


def build_windows_from_rules(rules_cfg: Dict[str, Any]) -> Dict[str, int]:
	# Query step is fixed to 30s, so row counts are seconds / 30.
	mapping: Dict[str, int] = {}
	for w in rules_cfg.get("windows", []):
		w_name = w["name"]
		seconds = int(w["seconds"])
		rows = max(1, seconds // 30)
		mapping[w_name] = rows
	return mapping


def ensure_all_required_columns(df: pd.DataFrame, required_metrics: Iterable[str]) -> pd.DataFrame:
	out = df.copy()
	for metric in required_metrics:
		if metric not in out.columns:
			out[metric] = math.nan
	return out


def main() -> None:
	args = parse_args()

	now = datetime.now(tz=timezone.utc)
	default_end = now
	default_start = now - timedelta(hours=24)
	start = parse_time(args.start, default_start)
	end = parse_time(args.end, default_end)
	if end <= start:
		raise ValueError("End time must be greater than start time")

	rules_path = resolve_existing_path(args.rules)
	with rules_path.open("r", encoding="utf-8") as f:
		rules_cfg = yaml.safe_load(f)

	required_aliases = metric_alias_map_from_rules(rules_cfg)
	alias_to_query: Dict[str, str] = {}
	missing: List[str] = []
	for alias in required_aliases:
		query = DEFAULT_METRIC_QUERIES.get(alias)
		if not query:
			missing.append(alias)
			continue
		alias_to_query[alias] = query

	if missing:
		raise RuntimeError(
			"Missing PromQL mapping for metric aliases: " + ", ".join(sorted(missing))
		)

	print(f"[INFO] Fetching {len(alias_to_query)} metrics from {args.prom_url}")
	base_df = fetch_all_metrics(
		prom_url=args.prom_url,
		alias_to_query=alias_to_query,
		start=start,
		end=end,
		step=args.step,
		timeout=args.timeout,
	)

	base_df = ensure_all_required_columns(base_df, required_aliases)
	windows = build_windows_from_rules(rules_cfg)
	eps = float(rules_cfg.get("global", {}).get("eps", 1.0e-9))

	feat_df = add_features(base_df, windows=windows, eps=eps)
	labeled_df = apply_rules(feat_df, rules_cfg)

	# Keep labels near the front; keep all metric and feature columns after.
	front_cols = [
		"timestamp",
		"instance",
		"window_size",
		"label_root_cause",
		"label_severity",
		"label_confidence",
		"matched_rules",
		"is_mixed",
	]
	other_cols = [c for c in labeled_df.columns if c not in front_cols]
	final_df = labeled_df[front_cols + other_cols]

	output_path = resolve_existing_path(args.output)
	if output_path.exists() and output_path.is_dir():
		raise IsADirectoryError(f"Output path points to a directory: {output_path}")
	output_path.parent.mkdir(parents=True, exist_ok=True)
	final_df.to_csv(output_path, index=False)
	print(f"[INFO] Wrote labeled dataset: {output_path}")
	print(f"[INFO] Rows: {len(final_df)}, Columns: {len(final_df.columns)}")


if __name__ == "__main__":
	main()
