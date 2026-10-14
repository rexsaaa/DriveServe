"""Read back model artifacts and produce a storage plan without uploading anything."""

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from driveserve.evidence import atomic_json, file_hash, git_state, now

parser = argparse.ArgumentParser()
parser.add_argument("--model-root", type=Path, required=True)
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
if args.output.exists():
    raise SystemExit("choose a new inventory path; previous evidence is retained")
models = []
for role, folder, second_copy in [
    ("target", "target", "target-weights"),
    ("draft", "draft", "draft-weights"),
    ("draft_aligned", "draft-aligned-v1", None),
    ("awq_smoke", "awq-smoke", None),
]:
    directory = args.model_root / folder
    provenance = json.loads((directory / "driveserve-provenance.json").read_text())
    files = []
    for expected in provenance["files"]:
        name = Path(expected["path"]).name
        source = directory / name
        if source.stat().st_size != expected["bytes"] or file_hash(source) != expected["sha256"]:
            raise ValueError(f"artifact changed: {source}")
        copies = []
        if second_copy:
            candidate = root / "artifacts/models" / second_copy / name
            if candidate.stat().st_size != expected["bytes"] or file_hash(candidate) != expected["sha256"]:
                raise ValueError(f"local copy changed: {candidate}")
            copies.append(str(candidate.relative_to(root)))
        files.append({"name": name, "source": str(source), "bytes": expected["bytes"],
                      "sha256": expected["sha256"], "verified_local_copies": copies})
    models.append({"role": role, "model": provenance["model"],
                   "derivation": provenance.get("derivation"),
                   "provenance_path": str(directory / "driveserve-provenance.json"),
                   "provenance_sha256": file_hash(directory / "driveserve-provenance.json"),
                   "bytes": sum(f["bytes"] for f in files), "files": files})
total = sum(m["bytes"] for m in models)
result = {"captured_at": now(), "code": git_state(root),
          "inventory_script_sha256": file_hash(__file__), "models": models,
          "payload_bytes": total, "payload_decimal_GB": total / 1e9,
          "persistence": "unverified: source is temporary disk; local copies are on overlay",
          "proposed_storage": {"destination": None, "status": "not authorized or uploaded",
              "incremental_cap_GB": 30, "quoted_CNY_per_GB_hour": 0.0004,
              "quote_source": "user-provided platform screenshot on 2026-10-14",
              "storage_only_cap_CNY_per_day": 30 * 0.0004 * 24,
              "storage_only_cap_CNY_per_30_days": 30 * 0.0004 * 24 * 30,
              "method": "separate uncompressed tar per model file plus provenance; upload and download/hash-check sequentially",
              "limitation": "storage cost estimate only; other fees and exact platform billing units not verified"}}
atomic_json(args.output, result)
print(json.dumps({"inventory": str(args.output), "payload_bytes": total,
                  "models": [{"role": m["role"], "bytes": m["bytes"]} for m in models]}, indent=2))
