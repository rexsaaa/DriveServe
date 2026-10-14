"""Send actual requests round-robin to two separate, verified GPU services."""

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from driveserve.benchmark import aggregate, request
from driveserve.evidence import Run, atomic_json, file_hash, process_alive
from driveserve.task import audit_dataset

parser = argparse.ArgumentParser()
parser.add_argument("--service-manifest", action="append", type=Path, required=True)
parser.add_argument("--dataset", type=Path, default=Path("data/samples/proxy-v1.jsonl"))
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
if len(args.service_manifest) != 2:
    raise ValueError("two distinct service manifests required")
services = [json.loads(p.read_text()) for p in args.service_manifest]
if any(m["status"] != "running" or not process_alive(m["process"]) for m in services):
    raise ValueError("both launchers must be verified alive")
configs = [m["config"] for m in services]
if any(c["tensor_parallel_size"] != 1 or c["model_role"] != "target" for c in configs):
    raise ValueError("this experiment requires two Target TP1 replicas")
if configs[0]["model"] != configs[1]["model"]:
    raise ValueError("model provenance mismatch")
devices = [c["environment"]["CUDA_VISIBLE_DEVICES"] for c in configs]
if len(set(devices)) != 2 or any("," in device for device in devices):
    raise ValueError("replicas must use different physical GPUs")
endpoints = [f"http://127.0.0.1:{c['port']}/v1" for c in configs]
if len(set(endpoints)) != 2:
    raise ValueError("replica endpoints must differ")
records = [json.loads(line) for line in args.dataset.read_text().splitlines() if line.strip()]
audit_dataset(records)
records = [r for r in records if r["split"] == "dev"][:32]
if not records:
    raise ValueError("empty development workload")
config = {"stage": "S2", "requirement_ids": ["M6-03"],
          "hypothesis": "two independent physical GPUs each serve assigned real SSE requests",
          "service_runs": [m["run_id"] for m in services], "service_configs": configs,
          "data": {"path": str(args.dataset), "sha256": file_hash(args.dataset), "split": "dev"},
          "endpoints": endpoints, "routing": "input index modulo 2, no prefix affinity", "concurrency": 4,
          "warmup": False, "model": configs[0]["model"],
          "limitations": ["Exploratory smoke, not a tuned B1 or fair deployment comparison.",
                          "Earlier TP2 client concurrency was 2; do not compute a speedup against it."]}
run = Run(root, "dual-replica-real-requests", config, formal=True)
print(run.path, flush=True)
rows = []
started = time.perf_counter_ns()
try:
    def execute(index, record):
        replica = index % 2
        row = request(endpoints[replica], configs[replica]["served_model_name"], record)
        row.update(replica=replica, endpoint=endpoints[replica], service_run=services[replica]["run_id"])
        return row
    with (run.path / "requests.jsonl").open("w", buffering=1) as stream:
        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = [pool.submit(execute, index, record) for index, record in enumerate(records)]
            for future in as_completed(futures):
                row = future.result()
                rows.append(row)
                stream.write(json.dumps(row, ensure_ascii=False) + "\n")
                stream.flush()
                os.fsync(stream.fileno())
    finished = time.perf_counter_ns()
    elapsed = (finished - started) / 1e9
    atomic_json(run.path / "measurement.json", {"started_monotonic_ns": started,
                "finished_monotonic_ns": finished, "attempted": len(records)})
    summary = aggregate(rows, elapsed)
    atomic_json(run.path / "summary.json", summary)
    per_replica = {str(index): {"requests": sum(r["replica"] == index for r in rows),
                              "success": sum(r["replica"] == index and r["status"] == "completed" for r in rows)} for index in range(2)}
    atomic_json(run.path / "per-replica.json", per_replica)
    run.finish("completed" if summary["success"] == len(records) else "failed", {"summary": summary, "per_replica": per_replica})
except BaseException as exc:
    run.finish("failed", {"error": str(exc)})
    raise
