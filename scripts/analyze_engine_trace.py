"""Reaggregate matched real diagnostic runs; keep observational limits explicit."""

import argparse
from collections import Counter
import json
from pathlib import Path
import statistics
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from driveserve.evidence import atomic_json, file_hash, verify_assets

parser = argparse.ArgumentParser()
parser.add_argument("--trace-on", type=Path, required=True)
parser.add_argument("--trace-off", type=Path, required=True)
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
manifests = [json.loads((p / "manifest.json").read_text()) for p in [args.trace_on, args.trace_off]]
for manifest in manifests:
    if manifest["status"] != "completed": raise ValueError("diagnostic run incomplete")
    verify_assets(root, manifest)
configs = [dict(m["config"]) for m in manifests]
for config in configs:
    config.pop("trace")
if configs[0] != configs[1] or manifests[0]["code"]["sha"] != manifests[1]["code"]["sha"]:
    raise ValueError("on/off experiments are not matched")
workloads = [json.loads((p / "workload.json").read_text()) for p in [args.trace_on, args.trace_off]]
if workloads[0] != workloads[1]: raise ValueError("on/off input tokens differ")
results = [{r["request_id"]: r for r in json.loads((p / "results.json").read_text())}
           for p in [args.trace_on, args.trace_off]]
if set(results[0]) != set(results[1]): raise ValueError("request sets differ")
identical = sum(results[0][key]["output_token_ids"] == results[1][key]["output_token_ids"] for key in results[0])
events = [json.loads(line) for p in sorted((args.trace_on / "engine-trace").glob("*.jsonl"))
          for line in p.read_text().splitlines()]
enqueued = {r["request_id"]: r["monotonic_ns"] for r in events if r["event"] == "Scheduler.add_seq_group"}
schedules = [r for r in events if r["event"] == "Scheduler.schedule"]
first_scheduled = {}
for row in schedules:
    for item in row["scheduled"]:
        first_scheduled.setdefault(item["request_id"], row["started_ns"] + row["host_call_ns"])
waits = []
for request in workloads[0]:
    key = request["request_id"]
    waits.append({"request_id": key, "prompt_tokens": len(request["tokens"]), "hot": request["hot"],
                  "enqueue_to_schedule_return_ms": (first_scheduled[key] - enqueued[key]) / 1e6})
host_totals = [sum(r["host_step_ns"] for r in json.loads((p / "steps.json").read_text())) / 1e9
               for p in [args.trace_on, args.trace_off]]
phase = {}
for name, prompt in [("prefill", True), ("decode", False)]:
    values = [r["host_call_ns"] / 1e6 for r in events
              if r["event"] == "ModelRunner.execute_model" and r["is_prompt"] is prompt]
    phase[name] = {"calls_including_warmup": len(values), "host_call_median_ms": statistics.median(values)}
report = {"trace_on": manifests[0]["run_id"], "trace_off": manifests[1]["run_id"],
          "code_sha": manifests[0]["code"]["sha"], "requests": len(results[0]),
          "identical_output_token_sequences": identical, "event_counts": dict(Counter(r["event"] for r in events)),
          "host_engine_step_total_s": {"trace_on": host_totals[0], "trace_off": host_totals[1]},
          "observed_host_step_relative_difference": host_totals[0] / host_totals[1] - 1,
          "max_queue_lengths": {key: max(r["queues_before"][key] for r in schedules) for key in ("waiting", "running", "swapped")},
          "preemptions": sum(r["preempted"] for r in schedules),
          "vllm_reported_cached_tokens_by_wave": {str(wave): sum(r["num_cached_tokens"] or 0 for r in results[0].values() if r["wave"] == wave) for wave in range(3)},
          "queue_observations": waits, "model_runner_host_phases": phase,
          "inputs_sha256": file_hash(args.trace_on / "workload.json"),
          "limitations": ["One on/off pair; not an isolated causal overhead estimate or independent repeats.",
                          "Host clocks and Python calls are not GPU kernel execution times.",
                          "Reported cached tokens follow vLLM output semantics; not necessarily the exact number of skipped Prefill tokens.",
                          "Enqueue-to-schedule-return includes observer and scheduler overhead; not HTTP arrival-to-admission latency.",
                          "Synthetic fixed-length outputs; no business quality or final P99 claim.",
                          "No cache pressure/preemption observed; no evidence for a saturation or eviction bottleneck."]}
atomic_json(args.output, report)
print(json.dumps({k: v for k, v in report.items() if k != "queue_observations"}, indent=2))
