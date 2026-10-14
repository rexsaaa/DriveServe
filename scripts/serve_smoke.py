"""Launch an explicitly configured real vLLM service after artifact verification."""

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from driveserve.evidence import Run, file_hash, process_identity

parser = argparse.ArgumentParser()
parser.add_argument("--python", type=Path, required=True)
parser.add_argument("--model-dir", type=Path, required=True)
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
config = json.loads((root / "configs/service-smoke.json").read_text())
provenance = json.loads((args.model_dir / "driveserve-provenance.json").read_text())
lock = json.loads((root / "configs/models.json").read_text())["target"]
if provenance["model"]["revision"] != lock["revision"]:
    raise SystemExit("model revision mismatch")
for asset in provenance["files"]:
    path = args.model_dir / Path(asset["path"]).name
    if path.stat().st_size != asset["bytes"] or file_hash(path) != asset["sha256"]:
        raise SystemExit(f"artifact verification failed: {path}")
command = [str(args.python), "-m", "vllm.entrypoints.openai.api_server", "--model", str(args.model_dir),
           "--served-model-name", config["served_model_name"], "--host", config["host"], "--port", str(config["port"]),
           "--tensor-parallel-size", str(config["tensor_parallel_size"]), "--dtype", config["dtype"],
           "--max-model-len", str(config["max_model_len"]), "--max-num-seqs", str(config["max_num_seqs"]),
           "--gpu-memory-utilization", str(config["gpu_memory_utilization"]), "--enforce-eager", "--enable-prefix-caching"]
run = Run(root, "vllm-service-smoke", {**config, "model": lock, "argv": command, "artifact_provenance": provenance})
environment = dict(os.environ)
environment.update(config["environment"])
environment["HF_HUB_OFFLINE"] = "1"
environment["TRANSFORMERS_OFFLINE"] = "1"
print(run.path, flush=True)
try:
    with (run.path / "service.log").open("w", buffering=1) as log:
        child = subprocess.Popen(command, cwd=root, env=environment, stdout=log, stderr=subprocess.STDOUT)
        run.manifest["child_process"] = process_identity(child.pid)
        run.save()
        code = child.wait()
    run.finish("completed" if code == 0 else "failed", {"returncode": code,
               "limitation": "server exit status alone is not evidence of request success"})
except BaseException as exc:
    run.finish("interrupted", {"error": str(exc)})
    raise
sys.exit(code)
