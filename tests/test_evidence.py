import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from driveserve.evidence import Run, atomic_json, file_hash, process_alive, process_identity, verify_assets


class EvidenceTest(unittest.TestCase):
    def test_formal_requires_commit_and_clean_tree(self):
        with tempfile.TemporaryDirectory() as temp:
            subprocess.run(["git", "init", "-q", "-b", "main", temp], check=True)
            with self.assertRaisesRegex(ValueError, "clean working tree"):
                Run(temp, "test", {}, formal=True)

    def test_hash_readback_and_tamper(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            file = root / "asset.json"
            atomic_json(file, {"valid": 1})
            manifest = {"assets": [{"path": file.name, "bytes": file.stat().st_size, "sha256": file_hash(file)}]}
            self.assertEqual(verify_assets(root, manifest), 1)
            atomic_json(file, {"valid": 2})
            with self.assertRaisesRegex(ValueError, "verification failed"):
                verify_assets(root, manifest)

    def test_process_identity_prevents_pid_reuse(self):
        identity = process_identity()
        self.assertTrue(process_alive(identity))
        identity["start_ticks"] = "-1"
        self.assertFalse(process_alive(identity))

    def test_nested_trace_is_sealed_and_tampering_detected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            run = Run.__new__(Run)
            run.root, run.path, run.manifest = root, root / "run", {}
            trace = run.path / "engine-trace" / "events.jsonl"
            trace.parent.mkdir(parents=True)
            trace.write_text('{"event":"allocate"}\n')
            manifest = run.finish("completed", {})
            self.assertEqual(verify_assets(root, manifest), 1)
            self.assertEqual(manifest["assets"][0]["path"], "run/engine-trace/events.jsonl")
            trace.write_text('{"event":"tampered"}\n')
            with self.assertRaisesRegex(ValueError, "verification failed"):
                verify_assets(root, manifest)
