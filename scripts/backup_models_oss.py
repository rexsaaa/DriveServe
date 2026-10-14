"""Back up a verified inventory with a durable per-object readback receipt.

Run under record_command.py to supervise the complete process group. This
script writes only into the explicitly selected, project-specific OSS prefix.
It never deletes cloud objects or source model files.
"""

import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from driveserve.evidence import atomic_json, file_hash, now


def archive_size(size):
    # One USTAR header, padded data, two EOF blocks, then a tar record boundary.
    return ((512 + ((size + 511) // 512) * 512 + 1024 + 10239) // 10240) * 10240


def verify_archive(path, expected_name, expected_size, expected_hash):
    with tarfile.open(path, "r:") as archive:
        members = archive.getmembers()
        if len(members) != 1 or not members[0].isfile():
            raise ValueError("unexpected archive members")
        member = members[0]
        if member.name != expected_name or member.size != expected_size:
            raise ValueError("archive member name/size mismatch")
        digest = hashlib.sha256()
        with archive.extractfile(member) as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        if digest.hexdigest() != expected_hash:
            raise ValueError("downloaded member checksum mismatch")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--destination", required=True)
    parser.add_argument("--staging", type=Path, required=True)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--cap-bytes", type=int, default=None,
                        help="Optional per-run byte limit; omitted means no fixed capacity cap")
    parser.add_argument("--oss", default="oss")
    parser.add_argument("--upload", action="store_true")
    args = parser.parse_args()
    if not args.destination.startswith("oss://") or "/DriveServe/" not in args.destination:
        raise ValueError("use a dedicated oss://bucket/DriveServe/unique-prefix destination")
    if args.cap_bytes is not None and args.cap_bytes <= 0:
        raise ValueError("an optional cap must be a positive number of bytes")
    inventory = json.loads(args.inventory.read_text())
    inventory_hash = file_hash(args.inventory)
    items = [{"name": "inventory.json", "source": str(args.inventory.resolve()),
              "bytes": args.inventory.stat().st_size, "sha256": inventory_hash}]
    for model in inventory["models"]:
        role = model["role"]
        provenance = Path(model["provenance_path"])
        items.append({"name": f"{role}/driveserve-provenance.json", "source": str(provenance),
                      "bytes": provenance.stat().st_size, "sha256": model["provenance_sha256"]})
        # Small metadata before weights: the first upload/readback is a real probe.
        for asset in sorted(model["files"], key=lambda x: (x["bytes"], x["name"])):
            items.append({"name": f"{role}/{asset['name']}", "source": asset["source"],
                          "bytes": asset["bytes"], "sha256": asset["sha256"]})
    for item in items:
        if any(part in ("..", "") for part in item["name"].split("/")) or item["name"].startswith("/"):
            raise ValueError("unsafe member name")
        if len(item["name"].encode()) > 100:
            raise ValueError("member name exceeds supported USTAR field")
        item["archive_bytes"] = archive_size(item["bytes"])
        item["object"] = args.destination.rstrip("/") + "/" + item["name"].replace("/", "--") + ".tar"
    if len({item["object"] for item in items}) != len(items):
        raise ValueError("duplicate object names")
    total = sum(item["archive_bytes"] for item in items)
    if args.cap_bytes is not None and total > args.cap_bytes:
        raise ValueError(f"planned {total} bytes exceeds authorized cap {args.cap_bytes}")
    plan = {"inventory_sha256": inventory_hash, "destination": args.destination,
            "planned_archive_bytes": total, "cap_bytes": args.cap_bytes, "items": items}
    print(json.dumps({"destination": args.destination, "objects": len(items),
                      "planned_archive_bytes": total, "cap_bytes": args.cap_bytes,
                      "estimated_incremental_storage_CNY_per_day": total / 1e9 * 0.0004 * 24,
                      "upload": args.upload}), flush=True)
    if not args.upload:
        return

    args.state.parent.mkdir(parents=True, exist_ok=True)
    args.staging.mkdir(parents=True, exist_ok=True)
    with args.state.with_suffix(".lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if args.state.exists():
            state = json.loads(args.state.read_text())
            if state["plan"] != plan:
                raise ValueError("backup identity changed; do not create duplicate paid copies")
        else:
            state = {"schema_version": 1, "created_at": now(), "plan": plan,
                     "verified": {}, "status": "in_progress"}
            atomic_json(args.state, state)
        if set(state["verified"]) - {item["object"] for item in items}:
            raise ValueError("receipt contains unexpected objects")
        logs = args.state.parent / "command-logs"
        logs.mkdir(exist_ok=True)
        def invoke(arguments, label):
            with (logs / f"{label}.log").open("a") as stream:
                subprocess.run([args.oss] + arguments, stdout=stream, stderr=subprocess.STDOUT,
                               input=b"n\n", check=True)
        for index, item in enumerate(items):
            if item["object"] in state["verified"]:
                receipt = state["verified"][item["object"]]
                if receipt["content_sha256"] != item["sha256"] or receipt["archive_bytes"] != item["archive_bytes"]:
                    raise ValueError("saved receipt differs from plan")
                print(f"Already verified {index + 1}/{len(items)} {item['name']}", flush=True)
                continue
            source = Path(item["source"])
            if source.stat().st_size != item["bytes"] or file_hash(source) != item["sha256"]:
                raise ValueError(f"source changed: {source}")
            if shutil.disk_usage(args.staging).free < 2 * item["archive_bytes"] + 3 * 1024 ** 3:
                raise ValueError("not enough staging space for archive + readback + 3 GiB reserve")
            # Deterministic, unique staging paths; an interrupted package is rebuilt.
            package = args.staging / f"{index:03d}-{inventory_hash[:12]}.tar"
            downloaded = args.staging / f"{index:03d}-{inventory_hash[:12]}.readback.tar"
            with tarfile.open(package, "w", format=tarfile.USTAR_FORMAT) as archive:
                member = tarfile.TarInfo(item["name"])
                member.size, member.mode, member.mtime = item["bytes"], 0o644, 0
                with source.open("rb") as stream:
                    archive.addfile(member, stream)
            if package.stat().st_size != item["archive_bytes"]:
                raise ValueError("archive size differs from cap accounting")
            package_hash = file_hash(package)
            # -u affects only this task's deterministic, isolated prefix.
            invoke(["cp", str(package), item["object"], "-u", "-p=2"], f"{index:03d}-upload")
            if downloaded.exists():
                downloaded.unlink()  # Only our disposable readback, never model assets.
            invoke(["cp", item["object"], str(downloaded), "-p=2"], f"{index:03d}-readback")
            if downloaded.stat().st_size != item["archive_bytes"] or file_hash(downloaded) != package_hash:
                raise ValueError("remote readback archive checksum mismatch")
            verify_archive(downloaded, item["name"], item["bytes"], item["sha256"])
            state["verified"][item["object"]] = {"verified_at": now(), "archive_bytes": item["archive_bytes"],
                "archive_sha256": package_hash, "content_bytes": item["bytes"], "content_sha256": item["sha256"]}
            atomic_json(args.state, state)
            package.unlink()
            downloaded.unlink()
            print(f"Readback verified {index + 1}/{len(items)} {item['name']}", flush=True)
        state.update(status="completed", completed_at=now())
        atomic_json(args.state, state)
        print(f"Completed {len(state['verified'])} verified remote objects; {total} bytes", flush=True)


if __name__ == "__main__":
    main()
