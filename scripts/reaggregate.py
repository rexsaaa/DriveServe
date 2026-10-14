"""Recompute a client's result from preserved requests and measurement boundaries."""

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from driveserve.benchmark import aggregate

parser = argparse.ArgumentParser()
parser.add_argument("run_dir", type=Path)
args = parser.parse_args()
rows = [json.loads(line) for line in (args.run_dir / "requests.jsonl").read_text().splitlines()]
window = json.loads((args.run_dir / "measurement.json").read_text())
duration = (window["finished_monotonic_ns"] - window["started_monotonic_ns"]) / 1e9
result = aggregate(rows, duration)
saved = json.loads((args.run_dir / "summary.json").read_text())
if result != saved:
    raise SystemExit("reaggregated result differs from preserved summary; do not overwrite evidence")
print(json.dumps({"identical": True, "summary": result}, ensure_ascii=False, indent=2))
