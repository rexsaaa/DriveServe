"""A small durable CPU job for S1 recovery validation; not training resume."""

import fcntl
import json
from pathlib import Path
import time

from .evidence import Run, atomic_json, file_hash, process_identity
from .task import label, canonical


def recoverable_job(root, dataset, state_dir, delay=0, stop_after=None):
    state_dir = Path(state_dir)
    state_dir.mkdir(parents=True, exist_ok=True)
    with (state_dir / "job.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError("job already running; refusing duplicate worker") from exc
        state_path = state_dir / "checkpoint.json"
        data_hash = file_hash(dataset)
        state = json.loads(state_path.read_text()) if state_path.exists() else {
            "schema_version": 1, "data_sha256": data_hash, "completed": [], "last_run_id": None}
        if state["data_sha256"] != data_hash or state["schema_version"] != 1:
            raise ValueError("checkpoint/data version mismatch")
        records = [json.loads(line) for line in Path(dataset).read_text().splitlines() if line.strip()]
        done = state["completed"]
        if len(done) > len(records) or any(value != {"scene_id": records[i]["scene"]["scene_id"],
                                                   "label": label(records[i]["scene"])} for i, value in enumerate(done)):
            raise ValueError("checkpoint integrity check failed")
        run = Run(root, "cpu-recovery-drill", {"data": {"sha256": data_hash}, "resume_from": len(done)},
                  previous_run_id=state["last_run_id"])
        state["last_run_id"] = run.manifest["run_id"]
        state["process"] = process_identity()
        atomic_json(state_path, state)
        count = 0
        try:
            for record in records[len(done):]:
                time.sleep(delay)
                done.append({"scene_id": record["scene"]["scene_id"], "label": label(record["scene"])})
                atomic_json(state_path, state)
                count += 1
                if stop_after and count >= stop_after:
                    result = {"completed": len(done), "total": len(records), "checkpoint_sha256": file_hash(state_path)}
                    atomic_json(run.path / "checkpoint-snapshot.json", state)
                    run.finish("interrupted", result)
                    return run
            atomic_json(run.path / "checkpoint-snapshot.json", state)
            run.finish("completed", {"completed": len(done), "total": len(records), "checkpoint_sha256": file_hash(state_path)})
            return run
        except BaseException as exc:
            run.finish("interrupted", {"error": str(exc), "completed": len(done)})
            raise
