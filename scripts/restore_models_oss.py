"""Restore selected objects from a readback receipt, without replacing user files."""

import argparse
import fcntl
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from driveserve.evidence import atomic_json, file_hash, now
from scripts.backup_models_oss import verify_archive


def select_items(state, names):
    items = state["plan"]["items"]
    if len({item["name"] for item in items}) != len(items):
        raise ValueError("duplicate receipt names")
    selected = [item for item in items if not names or item["name"] in names]
    if names and set(names) != {item["name"] for item in selected}:
        raise ValueError("requested name absent from receipt")
    for item in selected:
        name = Path(item["name"])
        if name.is_absolute() or ".." in name.parts or str(name) != item["name"]:
            raise ValueError("unsafe receipt member name")
        expected_object = state["plan"]["destination"].rstrip("/") + "/" + item["name"].replace("/", "--") + ".tar"
        if item["object"] != expected_object:
            raise ValueError("object is outside receipt namespace")
        receipt = state["verified"].get(item["object"])
        if not receipt or receipt["content_sha256"] != item["sha256"] or receipt["content_bytes"] != item["bytes"] or receipt["archive_bytes"] != item["archive_bytes"]:
            raise ValueError("object has no matching completed readback receipt")
    return selected


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--include", action="append", help="Exact inventory name; repeat to restore a subset")
    parser.add_argument("--oss", default="oss")
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    state = json.loads(args.receipt.read_text())
    items = select_items(state, args.include)
    args.destination.mkdir(parents=True, exist_ok=True)
    destination = args.destination.resolve()
    report = {"started_at": now(), "receipt_sha256": file_hash(args.receipt),
              "destination": str(destination), "subset": bool(args.include),
              "selected_items": len(items), "restored": [], "status": "running"}
    atomic_json(args.report, report)
    with (destination / ".restore.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        for item in items:
            target = destination / item["name"]
            # Do not follow a symlink into another directory, including on resume.
            if any(p.is_symlink() for p in [target, *target.parents] if p != destination.parent):
                raise ValueError("symlink in restore destination")
            target.parent.mkdir(parents=True, exist_ok=True)
            receipt = state["verified"][item["object"]]
            if target.exists():
                if target.stat().st_size != item["bytes"] or file_hash(target) != item["sha256"]:
                    raise ValueError(f"existing file differs; refusing to overwrite {target}")
                action = "existing_hash_verified"
            else:
                if shutil.disk_usage(destination).free < item["archive_bytes"] + item["bytes"] + 1024 ** 3:
                    raise ValueError("insufficient local space for downloaded archive, extracted file and reserve")
                with tempfile.TemporaryDirectory(prefix=".restore-", dir=target.parent) as temporary:
                    temporary = Path(temporary)
                    archive = temporary / "readback.tar"
                    result = subprocess.run([args.oss, "cp", item["object"], str(archive), "-p=2"],
                                            input=b"n\n", stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
                    # Only log OSS operation status, never credential files or login argv.
                    log_dir = args.report.parent / (args.report.stem + "-logs")
                    log_dir.mkdir(parents=True, exist_ok=True)
                    (log_dir / (item["name"].replace("/", "--") + ".log")).write_bytes(result.stdout)
                    result.check_returncode()
                    if archive.stat().st_size != receipt["archive_bytes"] or file_hash(archive) != receipt["archive_sha256"]:
                        raise ValueError("downloaded archive differs from backup receipt")
                    verify_archive(archive, item["name"], item["bytes"], item["sha256"])
                    extracted = temporary / "verified-content"
                    with tarfile.open(archive, "r:") as stream, stream.extractfile(item["name"]) as source, extracted.open("wb") as output:
                        shutil.copyfileobj(source, output)
                    if file_hash(extracted) != item["sha256"]:
                        raise ValueError("extracted content checksum mismatch")
                    # Exclusive creation via hard link cannot overwrite a concurrently created file.
                    target.hardlink_to(extracted)
                action = "downloaded_and_restored"
            report["restored"].append({"name": item["name"], "bytes": item["bytes"],
                                      "sha256": item["sha256"], "action": action, "verified_at": now()})
            atomic_json(args.report, report)
            print(f"Verified {len(report['restored'])}/{len(items)} {item['name']}", flush=True)
    report.update(status="completed", completed_at=now())
    atomic_json(args.report, report)


if __name__ == "__main__":
    main()
