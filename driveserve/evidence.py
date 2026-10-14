"""Durable run records and explicit exploratory/formal separation."""

import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import tempfile
import uuid
from datetime import datetime
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Asia/Shanghai")


def now():
    return datetime.now(TZ).isoformat()


def command(args, cwd=None, timeout=15):
    try:
        result = subprocess.run(args, cwd=cwd, text=True, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, timeout=timeout)
        return {"argv": args, "returncode": result.returncode,
                "stdout": result.stdout.strip(), "stderr": result.stderr.strip()}
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"argv": args, "returncode": None, "error": str(exc)}


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    name = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, encoding="utf-8", delete=False) as stream:
            name = stream.name
            json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
        fd = os.open(path.parent, os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    finally:
        if name and os.path.exists(name):
            os.unlink(name)


def file_hash(path):
    result = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def environment(root):
    root = Path(root).resolve()
    packages = {}
    for name in ("torch", "vllm", "transformers", "flash-attn", "pip", "setuptools", "wheel"):
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            packages[name] = None
    return {"captured_at": now(), "python": sys.version, "executable": sys.executable,
            "platform": platform.platform(), "cpu_count": os.cpu_count(), "packages": packages,
            "gpu": command(["nvidia-smi", "--query-gpu=index,name,uuid,memory.total,driver_version,pci.bus_id", "--format=csv"]),
            "topology": command(["nvidia-smi", "topo", "-m"]),
            "compiler": command(["nvcc", "--version"]),
            "storage": command(["df", "-hT", str(root)]),
            "mount": command(["findmnt", "-T", str(root), "-o", "TARGET,SOURCE,FSTYPE,SIZE,AVAIL"]),
            "persistence": "unknown: mount inspection cannot prove survival across shutdown/migration",
            "lease_deadline": "unknown"}


def git_state(root):
    sha = command(["git", "rev-parse", "--verify", "HEAD"], root)
    status = command(["git", "status", "--porcelain"], root)
    return {"sha": sha.get("stdout") if sha.get("returncode") == 0 else None,
            "dirty": status.get("returncode") != 0 or bool(status.get("stdout")),
            "status": status}


def process_identity(pid=None):
    pid = os.getpid() if pid is None else pid
    try:
        stat = Path(f"/proc/{pid}/stat").read_text()
        tail = stat[stat.rfind(")") + 2:].split()
        return {"pid": pid, "boot_id": Path("/proc/sys/kernel/random/boot_id").read_text().strip(),
                "start_ticks": tail[19], "state": tail[0]}
    except (OSError, IndexError):
        return None


def process_alive(saved):
    current = process_identity(saved["pid"]) if saved else None
    return bool(current and current["state"] != "Z" and
                all(current[key] == saved[key] for key in ("pid", "boot_id", "start_ticks")))


class Run:
    def __init__(self, root, kind, config, formal=False, baseline_run_id=None, previous_run_id=None):
        self.root = Path(root).resolve()
        code = git_state(self.root)
        if formal and (code["sha"] is None or code["dirty"]):
            raise ValueError("formal runs require an existing commit and a clean working tree")
        run_id = datetime.now(TZ).strftime("%Y%m%dT%H%M%S%z") + "-" + uuid.uuid4().hex[:10]
        self.path = self.root / "experiments" / "runs" / run_id
        self.path.mkdir(parents=True, exist_ok=False)
        env = environment(self.root)
        atomic_json(self.path / "environment.json", env)
        self.manifest = {"schema_version": 1, "run_id": run_id, "kind": kind, "stage": config.get("stage", "S1"),
                         "requirement_ids": config.get("requirement_ids", []), "hypothesis": config.get("hypothesis", "foundation verification"),
                         "baseline_run_id": baseline_run_id, "previous_run_id": previous_run_id,
                         "started_at": now(), "finished_at": None, "timezone": "Asia/Shanghai",
                         "status": "running", "mode": "formal" if formal else "exploratory",
                         "code": code, "aggregator_version": "driveserve.benchmark-v1",
                         "vllm_source": self._optional("configs/upstream.json"),
                         "environment_id": file_hash(self.path / "environment.json"),
                         "model": config.get("model", "not applicable: no model execution"),
                         "data": config.get("data", "not applicable"), "config": config,
                         "process": process_identity(), "assets": [], "result": None,
                         "limitations": list(config.get("limitations", [])) + [
                             "Each run belongs to its recorded environment; actual host migration and physical 24GB GPU validation are not implied."]}
        if code["dirty"]:
            diff = command(["git", "diff", "HEAD"], self.root)
            atomic_json(self.path / "working-tree.json", {"status": code["status"], "diff": diff})
            # Hash all untracked and tracked source files; archive the dirty source separately.
            import tarfile
            names = subprocess.check_output(["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"], cwd=self.root).decode().split("\0")
            with tarfile.open(self.path / "source-snapshot.tar.gz", "w:gz") as archive:
                for name in sorted(set(names)):
                    if name and not name.startswith("experiments/") and (self.root / name).is_file():
                        archive.add(self.root / name, arcname=name, recursive=False)
        self.save()

    def _optional(self, path):
        file = self.root / path
        return json.loads(file.read_text()) if file.exists() else "unknown"

    def save(self):
        atomic_json(self.path / "manifest.json", self.manifest)

    def finish(self, status, result):
        if status not in ("completed", "failed", "interrupted"):
            raise ValueError("invalid terminal status")
        self.manifest.update(status=status, result=result, finished_at=now())
        self.manifest["assets"] = [{"path": str(path.relative_to(self.root)), "bytes": path.stat().st_size,
                                    "sha256": file_hash(path)}
                                   for path in sorted(self.path.rglob("*"))
                                   if path != self.path / "manifest.json" and path.is_file()]
        self.save()
        return self.manifest


def verify_assets(root, manifest):
    root = Path(root).resolve()
    for asset in manifest["assets"]:
        path = (root / asset["path"]).resolve()
        if not path.is_relative_to(root) or path.stat().st_size != asset["bytes"] or file_hash(path) != asset["sha256"]:
            raise ValueError(f"asset verification failed: {asset['path']}")
    return len(manifest["assets"])
