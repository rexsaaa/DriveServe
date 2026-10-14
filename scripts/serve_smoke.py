"""Launch an explicitly configured real vLLM service after artifact verification."""

import argparse
import json
import os
import signal
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from driveserve.evidence import Run, file_hash, process_identity, atomic_json

parser = argparse.ArgumentParser()
parser.add_argument("--python", type=Path, required=True)
parser.add_argument("--model-dir", type=Path, required=True)
parser.add_argument("--model-role", choices=("target", "awq_smoke"), default="target")
parser.add_argument("--tp", type=int, choices=(1, 2), default=1)
parser.add_argument("--port", type=int, default=8000)
parser.add_argument("--memory-fraction", type=float, default=None)
parser.add_argument("--draft-dir", type=Path)
parser.add_argument("--draft-tokens", type=int, default=3)
parser.add_argument("--graph", action="store_true")
parser.add_argument("--devices", choices=("0", "1", "0,1", "1,0"), help="Physical CUDA device selection; count must match TP")
parser.add_argument("--stage", choices=("S1", "S2"), default="S1")
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
config = json.loads((root / "configs/service-smoke.json").read_text())
config["tensor_parallel_size"] = args.tp
config["port"] = args.port
config["enforce_eager"] = not args.graph
config["stage"] = args.stage
devices = args.devices or ("0,1" if args.tp == 2 else "0")
if len(devices.split(",")) != args.tp:
    raise SystemExit("device count must match tensor parallel size")
config["environment"]["CUDA_VISIBLE_DEVICES"] = devices
if args.memory_fraction is not None:
    if not 0 < args.memory_fraction < 1:
        raise SystemExit("memory fraction must be between 0 and 1")
    config["gpu_memory_utilization"] = args.memory_fraction
provenance = json.loads((args.model_dir / "driveserve-provenance.json").read_text())
lock = json.loads((root / "configs/models.json").read_text())[args.model_role]
config["model_role"] = args.model_role
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
           "--gpu-memory-utilization", str(config["gpu_memory_utilization"])]
if config["enforce_eager"]:
    command.append("--enforce-eager")
if args.model_role == "awq_smoke":
    config["quantization"] = "awq"
    command.extend(["--quantization", "awq"])
if args.draft_dir:
    draft = json.loads((args.draft_dir / "driveserve-provenance.json").read_text())
    draft_lock = json.loads((root / "configs/models.json").read_text())["draft"]
    if draft["model"]["revision"] != draft_lock["revision"]:
        raise SystemExit("Draft revision mismatch")
    for asset in draft["files"]:
        path = args.draft_dir / Path(asset["path"]).name
        if path.stat().st_size != asset["bytes"] or file_hash(path) != asset["sha256"]:
            raise SystemExit(f"Draft artifact verification failed: {path}")
    config["draft_provenance"] = draft
    config["enable_prefix_caching"] = False
    speculative = {"model": str(args.draft_dir), "num_speculative_tokens": args.draft_tokens,
                   "draft_tensor_parallel_size": 1, "method": "draft_model"}
    config["speculative_config"] = speculative
    command.extend(["--speculative-config", json.dumps(speculative)])
else:
    command.append("--enable-prefix-caching")
run = Run(root, "vllm-service-smoke", {**config, "model": lock, "argv": command, "artifact_provenance": provenance})
service_environment = subprocess.run([str(args.python), "-m", "driveserve", "doctor"], cwd=root,
                                     text=True, capture_output=True, check=True)
atomic_json(run.path / "service-environment.json", json.loads(service_environment.stdout))
run.manifest["service_environment_id"] = file_hash(run.path / "service-environment.json")
run.save()
environment = dict(os.environ)
environment.update(config["environment"])
environment["HF_HUB_OFFLINE"] = "1"
environment["TRANSFORMERS_OFFLINE"] = "1"
print(run.path, flush=True)
child = None
def interrupted(signum, frame):
    raise KeyboardInterrupt(f"signal {signum}")
signal.signal(signal.SIGTERM, interrupted)
try:
    with (run.path / "service.log").open("w", buffering=1) as log:
        child = subprocess.Popen(command, cwd=root, env=environment, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        run.manifest["child_process"] = process_identity(child.pid)
        run.manifest["child_process_group"] = child.pid
        run.save()
        code = child.wait()
    run.finish("completed" if code == 0 else "failed", {"returncode": code,
               "limitation": "server exit status alone is not evidence of request success"})
except BaseException as exc:
    if child is not None:
        try:
            os.killpg(child.pid, signal.SIGTERM)
            child.wait(timeout=15)
        except ProcessLookupError:
            pass
        except subprocess.TimeoutExpired:
            os.killpg(child.pid, signal.SIGKILL)
            child.wait(timeout=5)
    run.finish("interrupted", {"error": str(exc)})
    raise
sys.exit(code)
