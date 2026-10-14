"""Download immutable model files with resume and verify upstream content hashes."""

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from driveserve.evidence import Run, atomic_json, file_hash

parser = argparse.ArgumentParser()
parser.add_argument("--role", choices=("target", "draft"), required=True)
parser.add_argument("--destination", type=Path, required=True)
parser.add_argument("--proxy", default=None)
parser.add_argument("--weight-mirror", choices=("modelscope",), default=None,
                    help="Use mirror only when its advertised LFS hash matches the fixed upstream revision")
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
model = json.loads((root / "configs/models.json").read_text())[args.role]
run = Run(root, "model-download", {"model": model, "destination": str(args.destination),
                                  "role": args.role, "resume": True, "weight_mirror": args.weight_mirror})
try:
    args.destination.mkdir(parents=True, exist_ok=True)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({"https": args.proxy})) if args.proxy else urllib.request.build_opener()
    url = f"https://huggingface.co/api/models/{model['id']}/revision/{model['revision']}?blobs=true"
    with opener.open(url, timeout=30) as response:
        info = json.load(response)
    if info["sha"] != model["revision"]:
        raise ValueError("model revision mismatch")
    atomic_json(run.path / "source-metadata.json", info)
    files = [item for item in info["siblings"] if item["rfilename"].endswith((".json", ".safetensors", ".txt"))]
    if not files or not any(item["rfilename"].endswith(".safetensors") for item in files):
        raise ValueError("no model weights found")
    needed = sum(item["size"] for item in files if not (args.destination / item["rfilename"]).exists())
    if shutil.disk_usage(args.destination).free < needed + 3 * 1024 ** 3:
        raise ValueError(f"insufficient free space: need {needed} bytes plus 3 GiB reserve")
    verified = []
    for item in files:
        name = item["rfilename"]
        if Path(name).name != name:
            raise ValueError("nested or unsafe path in model manifest")
        final = args.destination / name
        part = args.destination / (name + ".part")
        if not final.exists():
            source = f"https://huggingface.co/{model['id']}/resolve/{model['revision']}/{name}"
            mirror = args.weight_mirror == "modelscope" and item.get("lfs")
            if mirror:
                source = f"https://modelscope.cn/models/{model['id']}/resolve/master/{name}"
                direct = urllib.request.build_opener(urllib.request.ProxyHandler({}))
                with direct.open(urllib.request.Request(source, method="HEAD"), timeout=20) as response:
                    advertised_hash = response.headers.get("X-Linked-Etag", "").strip('"')
                if advertised_hash != item["lfs"]["sha256"]:
                    raise ValueError(f"mirror content does not match pinned upstream: {name}")
            command = ["curl", "--fail", "--location", "--silent", "--show-error", "--retry", "4",
                       "--retry-all-errors", "--connect-timeout", "15", "--max-time", "1800",
                       "--speed-limit", "1024", "--speed-time", "60", "--continue-at", "-",
                       "--output", str(part), source]
            if mirror:
                command.extend(["--noproxy", "*"])
            elif args.proxy:
                command.extend(["--proxy", args.proxy])
            print(f"Downloading {args.role}/{name}: {item['size']} bytes", flush=True)
            subprocess.run(command, check=True)
            candidate = part
        else:
            candidate = final
        if candidate.stat().st_size != item["size"]:
            raise ValueError(f"size mismatch: {name}")
        sha256 = file_hash(candidate)
        if item.get("lfs"):
            if sha256 != item["lfs"]["sha256"]:
                raise ValueError(f"LFS sha256 mismatch: {name}; partial file retained for diagnosis")
        else:
            raw = candidate.read_bytes()
            git_blob = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
            if git_blob != item["blobId"]:
                raise ValueError(f"git blob hash mismatch: {name}")
        if candidate != final:
            candidate.replace(final)
        verified.append({"path": str(final), "bytes": final.stat().st_size, "sha256": sha256,
                         "source": source if not final.exists() or candidate == part else "existing verified local file"})
        atomic_json(run.path / "download-state.json", {"verified_files": verified, "model": model})
        print(f"Verified {name}: {sha256}", flush=True)
    atomic_json(args.destination / "driveserve-provenance.json", {"model": model, "files": verified, "run_id": run.manifest["run_id"]})
    run.finish("completed", {"files": verified, "bytes": sum(x["bytes"] for x in verified),
                             "limitation": "download verified; no inference or migration validation"})
except BaseException as exc:
    run.finish("failed", {"error": str(exc), "resume": "rerun with same pinned revision and destination; retains .part files"})
    raise
print(run.manifest["run_id"], flush=True)
