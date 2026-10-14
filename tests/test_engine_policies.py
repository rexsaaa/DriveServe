import os
import unittest
from collections import deque
from types import SimpleNamespace
from unittest.mock import patch
from driveserve.engine_policies import ColdHotEvictor, order_waiting


class PolicyTests(unittest.TestCase):
    def test_hot_protection_expiry_and_metadata_cleanup(self):
        clock = [0.0]
        e = ColdHotEvictor(hot_threshold=2, hot_ttl_s=10, clock=lambda: clock[0])
        e.add(0, 100, 16, 0)
        e.add(1, 101, 16, 1)
        e.record_reuse(100)
        e.record_reuse(100)
        self.assertEqual(e.evict(), (1, 101))
        e.remove(0)
        self.assertIn(100, e.reuse)  # Active sharing keeps history.
        e.add(0, 100, 16, 0)
        e.add(2, 102, 16, 2)
        clock[0] = 11
        self.assertEqual(e.evict(), (0, 100))
        self.assertNotIn(100, e.reuse)
        self.assertEqual(e.evict(), (2, 102))
        with self.assertRaises(ValueError):
            e.evict()

    def test_old_long_request_precedes_new_short_requests(self):
        def group(name, length, arrived):
            return SimpleNamespace(request_id=name, _driveserve_enqueued_at=arrived,
                get_seqs=lambda: [SimpleNamespace(get_prompt_len=lambda: length)])
        long = group('long', 1024, 1.0)
        short = group('short', 16, 1.4)
        medium = group('medium', 256, 1.45)
        scheduler = SimpleNamespace(waiting=deque([long, medium, short]),
            scheduler_config=SimpleNamespace(is_multi_step=False, policy='fcfs'))
        with patch('driveserve.engine_policies.time.monotonic', return_value=1.49), patch.dict(os.environ, {'DRIVESERVE_AGING_S': '0.5'}):
            order_waiting(scheduler, False)
            self.assertEqual([g.request_id for g in scheduler.waiting], ['short', 'medium', 'long'])
        with patch('driveserve.engine_policies.time.monotonic', return_value=1.6), patch.dict(os.environ, {'DRIVESERVE_AGING_S': '0.5'}):
            order_waiting(scheduler, False)
            self.assertEqual([g.request_id for g in scheduler.waiting], ['long', 'short', 'medium'])
        with self.assertRaises(ValueError):
            order_waiting(scheduler, True)
