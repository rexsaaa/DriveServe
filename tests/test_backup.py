"""Protect the paid-storage byte cap and readback integrity, without network I/O."""

import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest

spec = importlib.util.spec_from_file_location("backup_models_oss", Path(__file__).resolve().parents[1] / "scripts/backup_models_oss.py")
backup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backup)


class BackupArchiveTests(unittest.TestCase):
    def test_dry_run_over_30_gb_and_optional_explicit_cap(self):
        # Only a planning fixture: no large files are created and no OSS call is made.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            provenance = root / "provenance.json"
            provenance.write_text("{}")
            inventory = root / "inventory.json"
            inventory.write_text(json.dumps({"models": [{"role": "target",
                "provenance_path": str(provenance), "provenance_sha256": hashlib.sha256(b"{}").hexdigest(),
                "files": [{"name": f"weights-{index}.safetensors", "source": str(root / str(index)),
                           "bytes": 8_000_000_000, "sha256": "0" * 64} for index in range(4)]}]}))
            command = [sys.executable, str(Path(backup.__file__)), "--inventory", str(inventory),
                       "--destination", "oss://planning-fixture/DriveServe/test", "--staging", str(root / "staging"),
                       "--state", str(root / "state.json")]
            result = subprocess.run(command, text=True, capture_output=True, check=True)
            plan = json.loads(result.stdout)
            self.assertGreater(plan["planned_archive_bytes"], 30_000_000_000)
            self.assertIsNone(plan["cap_bytes"])
            self.assertFalse(plan["upload"])
            limited = subprocess.run(command + ["--cap-bytes", "30000000000"], text=True, capture_output=True)
            self.assertNotEqual(limited.returncode, 0)
            self.assertIn("exceeds authorized cap", limited.stderr)
            self.assertFalse((root / "state.json").exists())

    def test_cap_matches_real_tar_record_boundaries(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source"
            package = Path(directory) / "archive.tar"
            for size in (0, 1, 511, 512, 513, 8704, 9216, 10240, 1048577):
                source.write_bytes(b"a" * size)
                with tarfile.open(package, "w", format=tarfile.USTAR_FORMAT) as archive:
                    member = tarfile.TarInfo("target/weights")
                    member.size = size
                    with source.open("rb") as stream:
                        archive.addfile(member, stream)
                self.assertEqual(package.stat().st_size, backup.archive_size(size))
                backup.verify_archive(package, "target/weights", size, hashlib.sha256(source.read_bytes()).hexdigest())

    def test_readback_rejects_corrupted_content_and_extra_members(self):
        with tempfile.TemporaryDirectory() as directory:
            import io
            package = Path(directory) / "archive.tar"
            with tarfile.open(package, "w", format=tarfile.USTAR_FORMAT) as archive:
                member = tarfile.TarInfo("target/weights")
                member.size = 3
                archive.addfile(member, io.BytesIO(b"bad"))
            with self.assertRaisesRegex(ValueError, "checksum"):
                backup.verify_archive(package, "target/weights", 3, hashlib.sha256(b"yes").hexdigest())
            with tarfile.open(package, "a") as archive:
                member = tarfile.TarInfo("unexpected")
                archive.addfile(member)
            with self.assertRaisesRegex(ValueError, "unexpected"):
                backup.verify_archive(package, "target/weights", 3, hashlib.sha256(b"bad").hexdigest())


if __name__ == "__main__":
    unittest.main()
