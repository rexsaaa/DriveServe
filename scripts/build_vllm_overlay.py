"""Replay a checked source patch into an isolated package overlay, never the wheel."""

import argparse
import importlib.metadata
import json
from pathlib import Path
import shutil
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from driveserve.evidence import atomic_json, file_hash, now


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--destination", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    lock = json.loads((root / "patches/vllm-v0.8.5-observers.json").read_text())
    distribution = importlib.metadata.distribution("vllm")
    if distribution.version != lock["version"]:
        raise ValueError("vLLM wheel version does not match patch")
    source = Path(distribution.locate_file("vllm")).resolve()
    changed = {entry["path"]: entry for entry in lock["files"]}
    for name, entry in changed.items():
        if file_hash(source.parent / name) != entry["upstream_sha256"]:
            raise ValueError(f"wheel source differs from pinned upstream: {name}")
    destination = args.destination.resolve()
    if destination.exists():
        raise ValueError("overlay already exists; preserve it and choose a new destination")
    destination.mkdir(parents=True)
    for path in source.rglob("*"):
        if "__pycache__" in path.parts or path.suffix == ".pyc":
            continue
        relative = Path("vllm") / path.relative_to(source)
        target = destination / relative
        if path.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            if str(relative) in changed:
                shutil.copyfile(path, target)
            else:
                target.symlink_to(path)
    patch = root / "patches" / lock["patch"]
    subprocess.run(["patch", "--batch", "--forward", "--fuzz=0", "-p1", "-i", str(patch)],
                   cwd=destination, check=True)
    for name, entry in changed.items():
        if file_hash(destination / name) != entry["patched_sha256"]:
            raise ValueError(f"patched file checksum mismatch: {name}")
        if file_hash(source.parent / name) != entry["upstream_sha256"]:
            raise ValueError(f"original wheel unexpectedly changed: {name}")
    manifest = {"created_at": now(), "source": str(source), "destination": str(destination),
                "vllm_version": distribution.version, "patch_sha256": file_hash(patch),
                "lock": lock, "limitation": "Local symlinks reuse the locked wheel; rebuild after environment migration."}
    atomic_json(destination / "overlay-manifest.json", manifest)
    print(json.dumps(manifest, indent=2), flush=True)


if __name__ == "__main__":
    main()
