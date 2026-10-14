"""Analyze an exported Nsight SQLite timeline by real API/kernel correlation IDs."""

import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import sqlite3
import statistics
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from driveserve.evidence import atomic_json, file_hash


def union_ns(intervals):
    end, total = None, 0
    for begin, finish in sorted(intervals):
        if end is None or begin >= end:
            total += finish - begin
        elif finish > end:
            total += finish - end
        end = max(end or finish, finish)
    return total


parser = argparse.ArgumentParser()
parser.add_argument("--sqlite", type=Path, required=True)
parser.add_argument("--report", type=Path, required=True)
parser.add_argument("--nsys-rep", type=Path, required=True)
args = parser.parse_args()
connection = sqlite3.connect(f"file:{args.sqlite.resolve()}?mode=ro", uri=True)
connection.row_factory = sqlite3.Row
strings = dict(connection.execute("SELECT id, value FROM StringIds"))
ranges = [dict(row) for row in connection.execute("SELECT start,end,text,globalTid FROM NVTX_EVENTS WHERE text LIKE 'DriveServe.ModelRunner.%' AND end IS NOT NULL ORDER BY start")]
apis = [dict(row) for row in connection.execute("SELECT start,end,globalTid,correlationId,nameId FROM CUPTI_ACTIVITY_KIND_RUNTIME")]
correlations = {}
for api in apis:
    api["name"] = strings[api["nameId"]]
    key = (api["globalTid"] & ~0xFFFFFF, api["correlationId"])
    if key in correlations:
        raise ValueError("ambiguous API correlation; adapt analysis before using these results")
    correlations[key] = api
kernel_rows = [dict(row) for row in connection.execute("SELECT start,end,deviceId,streamId,globalPid,correlationId,demangledName FROM CUPTI_ACTIVITY_KIND_KERNEL")]
grouped, unmatched, by_kernel = defaultdict(list), [], defaultdict(list)
for kernel in kernel_rows:
    kernel["name"] = strings[kernel["demangledName"]]
    by_kernel[kernel["name"]].append(kernel["end"] - kernel["start"])
    api = correlations.get((kernel["globalPid"], kernel["correlationId"]))
    matched = None
    if api:
        for index, nvtx in enumerate(ranges):
            if nvtx["globalTid"] == api["globalTid"] and nvtx["start"] <= api["start"] and api["end"] <= nvtx["end"]:
                matched = index
                break
    if matched is None:
        unmatched.append(kernel)
    else:
        kernel["launch_api_ns"] = api["end"] - api["start"]
        kernel["start_minus_api_end_ns"] = kernel["start"] - api["end"]
        grouped[matched].append(kernel)
per_range = []
for index, nvtx in enumerate(ranges):
    kernels = grouped[index]
    if not kernels: raise ValueError("NVTX range has no correlated kernels")
    # This run is a single device. Union handles overlap across streams.
    if len({k["deviceId"] for k in kernels}) != 1:
        raise ValueError("multi-device ranges need per-device accounting")
    union = union_ns([(k["start"], k["end"]) for k in kernels])
    span = max(k["end"] for k in kernels) - min(k["start"] for k in kernels)
    per_range.append({"index": index, "phase": nvtx["text"].rsplit(".", 1)[-1],
        "host_start_ns": nvtx["start"], "host_duration_ms": (nvtx["end"] - nvtx["start"]) / 1e6,
        "kernel_count": len(kernels), "kernel_union_ms": union / 1e6,
        "kernel_span_ms": span / 1e6, "kernel_gap_ms": (span - union) / 1e6,
        "launch_api_total_ms": sum(k["launch_api_ns"] for k in kernels) / 1e6,
        "kernel_start_minus_api_end_median_us": statistics.median(k["start_minus_api_end_ns"] for k in kernels) / 1e3})
phases = {}
for phase in sorted({r["phase"] for r in per_range}):
    rows = [r for r in per_range if r["phase"] == phase]
    phases[phase] = {"ranges": len(rows), "kernel_count": sum(r["kernel_count"] for r in rows),
        **{f"median_{field}": statistics.median(r[field] for r in rows)
           for field in ["host_duration_ms", "kernel_union_ms", "kernel_span_ms", "kernel_gap_ms", "launch_api_total_ms"]}}
total_kernel_ns = sum(k["end"] - k["start"] for k in kernel_rows)
top = [{"kernel": name, "calls": len(durations), "sum_ms": sum(durations) / 1e6,
        "share_of_kernel_duration_sum": sum(durations) / total_kernel_ns}
       for name, durations in sorted(by_kernel.items(), key=lambda item: sum(item[1]), reverse=True)]
report = {"sqlite": str(args.sqlite), "sqlite_sha256": file_hash(args.sqlite),
          "nsys_rep": str(args.nsys_rep), "nsys_rep_sha256": file_hash(args.nsys_rep),
          "kernel_count": len(kernel_rows), "unmatched_kernels": len(unmatched),
          "phase_summary": phases, "top_kernels": top, "ranges": per_range,
          "limitations": ["Profiled single-GPU synthetic workload with observers; not a performance baseline.",
                          "Kernel union is execution of captured kernels only. Kernel gaps may contain memory work or unrelated activity; they are not proof of CPU bottlenecks or whole-device idleness.",
                          "API time can overlap GPU execution; host and device durations cannot simply be added.",
                          "NVTX phase assigned from actual model-input attention metadata; kernels linked through same-process CUDA API correlation IDs.",
                          "Single-GPU capture does not measure TP2 NCCL communication."]}
atomic_json(args.report, report)
print(json.dumps({"kernel_count": report["kernel_count"], "unmatched_kernels": report["unmatched_kernels"],
                  "phase_summary": phases, "top_three_kernels": top[:3]}, indent=2))
