"""Actually terminate a disposable CPU worker, reject a duplicate, and resume."""

import json
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from driveserve.evidence import Run, atomic_json, verify_assets

root = Path(__file__).resolve().parents[1]
run = Run(root, "cpu-process-interruption-validation", {"mechanism": "SIGTERM child, flock, resume"})
state = root / "artifacts/recovery" / run.manifest["run_id"]
args = [sys.executable, "-m", "driveserve", "recovery", "--dataset", "data/samples/proxy-v1.jsonl", "--state-dir", str(state)]
worker = None
try:
    with (run.path / "first-worker.log").open("w") as stream:
        worker = subprocess.Popen(args + ["--delay", "0.1"], cwd=root, stdout=stream, stderr=subprocess.STDOUT)
        deadline = time.monotonic() + 20
        checkpoint = state / "checkpoint.json"
        while time.monotonic() < deadline:
            if worker.poll() is not None:
                raise RuntimeError("first worker exited before interruption")
            if checkpoint.exists() and len(json.loads(checkpoint.read_text())["completed"]) >= 3:
                break
            time.sleep(.05)
        else:
            raise RuntimeError("checkpoint never appeared")
        before = json.loads(checkpoint.read_text())
        duplicate = subprocess.run(args, cwd=root, text=True, capture_output=True, timeout=10)
        (run.path / "duplicate-worker.log").write_text(duplicate.stdout + duplicate.stderr)
        assert duplicate.returncode != 0 and "job already running" in duplicate.stderr
        worker.terminate()
        first_code = worker.wait(timeout=10)
        before = json.loads(checkpoint.read_text())
        atomic_json(run.path / "interrupted-checkpoint.json", before)
    resumed = subprocess.run(args, cwd=root, text=True, capture_output=True, timeout=20)
    (run.path / "resumed-worker.log").write_text(resumed.stdout + resumed.stderr)
    assert resumed.returncode == 0, resumed.stderr
    after = json.loads(checkpoint.read_text())
    ids = [item["scene_id"] for item in after["completed"]]
    assert len(ids) == len(set(ids)) == 128
    assert after["completed"][:len(before["completed"])] == before["completed"]
    atomic_json(run.path / "final-checkpoint.json", after)
    previous_path = root / "experiments/runs" / before["last_run_id"] / "manifest.json"
    assert json.loads(previous_path.read_text())["status"] == "interrupted"
    run.finish("completed", {"first_worker_exit_code": first_code, "duplicate_refused": True,
                             "resume_prefix_preserved": True, "interrupted_after": len(before["completed"]),
                             "completed": len(ids), "first_run_id": before["last_run_id"],
                             "resumed_run_id": after["last_run_id"], "scope": "CPU job; not training recovery"})
    print(json.dumps({"run_id": run.manifest["run_id"], "result": run.manifest["result"],
                      "verified_assets": verify_assets(root, run.manifest)}, indent=2))
except BaseException as exc:
    if worker is not None and worker.poll() is None:
        worker.terminate()
        worker.wait(timeout=10)
    run.finish("failed", {"error": str(exc)})
    raise
