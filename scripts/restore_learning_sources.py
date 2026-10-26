"""Restore pinned source references offline, preserving existing edits.

Only Python's standard library is needed. This does not install either framework.
"""

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import tarfile


def digest(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Verify without writing")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    manifest = json.loads(
        (root / "docs/interview-prep/assets/reference-sources.json").read_text()
    )
    pending = []
    checked = 0
    # Preflight every reference before writing any file.
    for ref in manifest["references"]:
        archive = root / ref["archive"]
        data = archive.read_bytes()
        if len(data) != ref["archive_bytes"] or digest(data) != ref["archive_sha256"]:
            raise ValueError(f"Archive checksum mismatch: {archive}")
        seen = set()
        with tarfile.open(archive) as stream:
            for member in stream.getmembers():
                name = PurePosixPath(member.name)
                if name.is_absolute() or ".." in name.parts:
                    raise ValueError(f"Unsafe archive path: {member.name}")
                if member.isdir():
                    continue
                if not member.isfile() or member.name in seen:
                    raise ValueError(f"Unsupported or duplicate member: {member.name}")
                seen.add(member.name)
                expected = ref["files"][member.name]
                data = stream.extractfile(member).read()
                if len(data) != expected["bytes"] or digest(data) != expected["sha256"]:
                    raise ValueError(f"Source checksum mismatch: {member.name}")
                relative = Path("third_party") / member.name
                if not relative.is_relative_to(Path(ref["directory"])):
                    raise ValueError(f"Member outside reference directory: {member.name}")
                target = root / relative
                if any(p.is_symlink() for p in [target, *target.parents] if p != root and root in p.parents):
                    raise ValueError(f"Refusing a symlink destination: {relative}")
                if target.exists():
                    if not target.is_file() or target.read_bytes() != data:
                        raise ValueError(f"Existing file differs; preserved: {relative}")
                else:
                    pending.append((target, data, member.mode & 0o777))
                checked += 1
        if seen != set(ref["files"]) or len(seen) != ref["file_count"]:
            raise ValueError(f"Source inventory mismatch: {archive}")
    if args.check and pending:
        raise ValueError(f"{len(pending)} source files missing; run without --check to restore")
    for target, data, mode in pending:
        target.parent.mkdir(parents=True, exist_ok=True)
        # Exclusive creation also protects files created since preflight.
        with target.open("xb") as stream:
            stream.write(data)
        target.chmod(mode)
    print(json.dumps({"status": "passed", "source_files_verified": checked,
                      "files_restored": len(pending), "offline": True}))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, KeyError, tarfile.TarError) as exc:
        raise SystemExit(str(exc)) from exc
