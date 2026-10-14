import io
import json
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest

from scripts.snapshot_environment import verify_snapshot


class EnvironmentSnapshotTests(unittest.TestCase):
    def test_local_roundtrip_and_symlink_preservation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "venv"
            source.mkdir()
            (source / "pyvenv.cfg").write_text("home = /usr/bin\n")
            (source / "library.bin").write_bytes(b"environment data" * 200)
            (source / "python").symlink_to("/usr/bin/python3.11")
            command = [sys.executable, "scripts/snapshot_environment.py", "--source", str(source),
                       "--directory", str(root / "snapshot"), "--readback-directory", str(root / "readback"),
                       "--destination", "oss://DriveServe/local-test-only"]
            subprocess.run(command, check=True, capture_output=True)
            manifest = json.loads((root / "snapshot/snapshot-manifest.json").read_text())
            verify_snapshot(root / "snapshot/gpu-environment.tar.gz", manifest)
            self.assertIn({"name": "venv/python", "type": "symlink", "target": "/usr/bin/python3.11"}, manifest["entries"])
            self.assertFalse((root / "snapshot/oss-receipt.json").exists())
            subprocess.run(command, check=True, capture_output=True)  # Reuse verified archive, no OSS calls.
            broken = root / "bad.tar.gz"
            with tarfile.open(broken, "w:gz") as stream:
                data = json.dumps(manifest).encode()
                header = tarfile.TarInfo("snapshot-manifest.json")
                header.size = len(data)
                stream.addfile(header, io.BytesIO(data))
            with self.assertRaisesRegex(ValueError, "incomplete"):
                verify_snapshot(broken, manifest)
