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
from scripts.restore_models_oss import select_items


class BackupArchiveTests(unittest.TestCase):
    def test_restore_requires_verified_matching_objects_and_safe_names(self):
        import copy
        item = {"name": "target/config.json", "object": "oss://DriveServe/test/target--config.json.tar",
                "bytes": 2, "sha256": "a" * 64, "archive_bytes": 10240}
        state = {"plan": {"items": [item], "destination": "oss://DriveServe/test"},
                 "verified": {item["object"]: {"content_bytes": 2, "content_sha256": "a" * 64,
                                             "archive_bytes": 10240, "archive_sha256": "b" * 64}}}
        self.assertEqual(select_items(state, ["target/config.json"]), [item])
        for change in ("missing_receipt", "wrong_hash", "outside_namespace", "traversal", "duplicate"):
            bad = copy.deepcopy(state)
            if change == "missing_receipt": bad["verified"] = {}
            elif change == "wrong_hash": bad["verified"][item["object"]]["content_sha256"] = "0" * 64
            elif change == "outside_namespace": bad["plan"]["items"][0]["object"] = "oss://another/file.tar"
            elif change == "traversal": bad["plan"]["items"][0]["name"] = "../config.json"
            else: bad["plan"]["items"].append(item)
            with self.subTest(change=change), self.assertRaises(ValueError):
                select_items(bad, None)
        with self.assertRaises(ValueError):
            select_items(state, ["not-in-receipt"])

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
