"""Observer contract only; actual engine evidence must come from GPU runs."""

import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from driveserve.engine_trace import _observe, close_traces


class TraceTests(unittest.TestCase):
    def test_observer_preserves_return_identity_arguments_and_exceptions(self):
        calls = []

        class Subject:
            def execute(self, value, *, fail=False):
                calls.append((value, fail))
                if fail:
                    raise ValueError("original error")
                return value

        _observe(Subject, "execute", lambda self, args, kwargs: {"probe": 1},
                 lambda self, args, kwargs, result: {"returned": True})
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"DRIVESERVE_TRACE_DIR": directory}):
            subject, sentinel = Subject(), object()
            self.assertIs(subject.execute(sentinel, fail=False), sentinel)
            with self.assertRaisesRegex(ValueError, "original error"):
                subject.execute(sentinel, fail=True)
            close_traces()
            events = [json.loads(line) for p in Path(directory).glob("*.jsonl") for line in p.read_text().splitlines()]
        self.assertEqual(calls, [(sentinel, False), (sentinel, True)])
        self.assertEqual([row["outcome"] for row in events], ["ok", "error"])
        self.assertTrue(all(row["host_call_ns"] >= 0 for row in events))
        with self.assertRaisesRegex(RuntimeError, "twice"):
            _observe(Subject, "execute", lambda *args: {}, lambda *args: {})

