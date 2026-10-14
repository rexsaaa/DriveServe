"""Preserve an idle venv body as a verified OSS archive, in addition to rebuild locks."""

import argparse
import fcntl
import hashlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from driveserve.evidence import atomic_json, file_hash, now


def inventory(source):
    entries = []
    for path in sorted(source.rglob("*")):
        name = str(Path("venv") / path.relative_to(source))
        if path.is_symlink():
            entries.append({"name": name, "type": "symlink", "target": str(path.readlink())})
        elif path.is_file():
            entries.append({"name": name, "type": "file", "bytes": path.stat().st_size, "sha256": file_hash(path)})
        elif not path.is_dir():
            raise ValueError(f"unsupported environment entry: {path}")
    return entries


def verify_snapshot(archive, manifest):
    expected = {item["name"]: item for item in manifest["entries"]}
    seen = set()
    with tarfile.open(archive, "r|gz") as stream:
        for member in stream:
            if member.name in seen:
                raise ValueError("duplicate snapshot member")
            seen.add(member.name)
            if member.name == "snapshot-manifest.json":
                if not member.isfile() or json.load(stream.extractfile(member)) != manifest:
                    raise ValueError("snapshot inventory mismatch")
                continue
            item = expected.get(member.name)
            if item is None:
                raise ValueError("unexpected snapshot member")
            if item["type"] == "symlink":
                if not member.issym() or member.linkname != item["target"]:
                    raise ValueError("symlink target mismatch")
            else:
                if not member.isfile() or member.size != item["bytes"]:
                    raise ValueError("file type/size mismatch")
                digest = hashlib.sha256()
                with stream.extractfile(member) as contents:
                    for block in iter(lambda: contents.read(1024 * 1024), b""):
                        digest.update(block)
                if digest.hexdigest() != item["sha256"]:
                    raise ValueError("snapshot file checksum mismatch")
    if seen != set(expected) | {"snapshot-manifest.json"}:
        raise ValueError("incomplete snapshot")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--directory", type=Path, required=True, help="Local archive, inventory and receipt directory")
    parser.add_argument("--readback-directory", type=Path, required=True)
    parser.add_argument("--destination", required=True, help="Dedicated OSS parent directory")
    parser.add_argument("--upload", action="store_true")
    args = parser.parse_args()
    if not args.destination.startswith("oss://DriveServe/"):
        raise ValueError("snapshot must remain in the project OSS namespace")
    source = args.source.resolve()
    if not (source / "pyvenv.cfg").is_file():
        raise ValueError("source is not a venv")
    args.directory.mkdir(parents=True, exist_ok=True)
    args.readback_directory.mkdir(parents=True, exist_ok=True)
    with (args.directory / ".snapshot.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        manifest_path = args.directory / "snapshot-manifest.json"
        archive = args.directory / "gpu-environment.tar.gz"
        ready = args.directory / "archive-ready.json"
        if ready.exists():
            manifest = json.loads(manifest_path.read_text())
            prepared = json.loads(ready.read_text())
            if manifest["source"] != str(source) or file_hash(archive) != prepared["sha256"]:
                raise ValueError("saved snapshot identity changed")
        else:
            entries = inventory(source)
            manifest = {"created_at": now(), "source": str(source), "entries": entries,
                        "limitations": ["Venv binaries and absolute shebangs/links are not universally portable.",
                                        "Host Python, libc, NVIDIA driver and project editable-install path remain external dependencies.",
                                        "Use locked rebuild scripts when restoring to a different host or path."]}
            total = sum(item.get("bytes", 0) for item in entries)
            if shutil.disk_usage(args.directory).free < total + 1024 ** 3:
                raise ValueError("insufficient archive space for worst-case uncompressed size")
            atomic_json(manifest_path, manifest)
            temporary = archive.with_suffix(".partial")
            with tarfile.open(temporary, "w:gz", compresslevel=1, format=tarfile.PAX_FORMAT) as stream:
                data = json.dumps(manifest, ensure_ascii=False, sort_keys=True).encode()
                header = tarfile.TarInfo("snapshot-manifest.json")
                header.size = len(data)
                stream.addfile(header, io.BytesIO(data))
                for item in entries:
                    path = source / Path(item["name"]).relative_to("venv")
                    member = stream.gettarinfo(str(path), arcname=item["name"])
                    member.uid = member.gid = 0
                    member.uname = member.gname = ""
                    # Preserve each file's actual bytes; do not encode hardlink
                    # relationships that may refer outside this archive.
                    if item["type"] == "file":
                        member.type, member.linkname, member.size = tarfile.REGTYPE, "", item["bytes"]
                        with path.open("rb") as contents: stream.addfile(member, contents)
                    else:
                        stream.addfile(member)
            verify_snapshot(temporary, manifest)
            temporary.replace(archive)
            prepared = {"archive": str(archive), "bytes": archive.stat().st_size, "sha256": file_hash(archive),
                        "manifest_sha256": file_hash(manifest_path), "uncompressed_file_bytes": total,
                        "file_entries": len(entries), "locally_verified_at": now()}
            atomic_json(ready, prepared)
        print(json.dumps(prepared), flush=True)
        if not args.upload: return
        object_uri = args.destination.rstrip("/") + "/gpu-environment-" + prepared["sha256"][:12] + ".tar.gz"
        receipt_path = args.directory / "oss-receipt.json"
        if receipt_path.exists():
            receipt = json.loads(receipt_path.read_text())
            if receipt["object"] != object_uri or receipt["sha256"] != prepared["sha256"]:
                raise ValueError("existing snapshot receipt differs")
            print("Snapshot already uploaded and fully readback verified", flush=True)
            return
        if shutil.disk_usage(args.readback_directory).free < prepared["bytes"] + 3 * 1024 ** 3:
            raise ValueError("insufficient readback space")
        downloaded = args.readback_directory / ("environment-" + prepared["sha256"][:12] + ".tar.gz")
        for name, command in [("upload", [str(archive), object_uri, "-u", "-p=2"]),
                              ("readback", [object_uri, str(downloaded), "-p=2"])]:
            if name == "readback" and downloaded.exists():
                downloaded.unlink()  # Disposable readback only; retained archive and source remain.
            with (args.directory / f"{name}.log").open("a") as log:
                subprocess.run(["oss", "cp", *command], input=b"n\n", stdout=log, stderr=subprocess.STDOUT, check=True)
        if downloaded.stat().st_size != prepared["bytes"] or file_hash(downloaded) != prepared["sha256"]:
            raise ValueError("remote environment archive checksum mismatch")
        verify_snapshot(downloaded, manifest)
        atomic_json(receipt_path, {**prepared, "object": object_uri, "verified_at": now(),
                                  "estimated_storage_CNY_per_day": prepared["bytes"] / 1e9 * 0.0004 * 24})
        downloaded.unlink()
        print(f"Environment readback verified: {object_uri}", flush=True)


if __name__ == "__main__":
    main()
