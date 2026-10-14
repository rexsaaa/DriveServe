"""Retrieve the pinned upstream archive, verify hash, safely extract; never edits site-packages."""

import argparse
import hashlib
import json
from pathlib import Path
import tarfile
import urllib.request

parser = argparse.ArgumentParser()
parser.add_argument("--proxy")
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
lock = json.loads((root / "configs/upstream.json").read_text())
archive = root / "artifacts/upstream" / f"vllm-{lock['commit']}.tar.gz"
if not archive.exists():
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({"http": args.proxy, "https": args.proxy})) if args.proxy else urllib.request.build_opener()
    with opener.open(lock["archive_url"], timeout=30) as response:
        data = response.read(50_000_001)
    if hashlib.sha256(data).hexdigest() != lock["archive_sha256"]:
        raise SystemExit("upstream archive checksum mismatch")
    archive.parent.mkdir(parents=True, exist_ok=True)
    archive.write_bytes(data)
if hashlib.sha256(archive.read_bytes()).hexdigest() != lock["archive_sha256"]:
    raise SystemExit("local archive checksum mismatch")
destination = root / "third_party" / f"vllm-{lock['commit']}"
if destination.exists():
    raise SystemExit(f"Source already exists: {destination}; preserving any edits. Use a fresh checkout to rebuild.")
with tarfile.open(archive) as stream:
    stream.extractall(root / "third_party", filter="data")
print(destination)
