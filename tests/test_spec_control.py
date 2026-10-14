import unittest
from driveserve.spec_control import DraftLengthController,accepted_prefix

class SpecControlTests(unittest.TestCase):
    def test_window_hysteresis_hold_reservation_and_fallback(self):
        c=DraftLengthController()
        for _ in range(7):c.observe(2,2)
        self.assertEqual(c.choose(4)['k'],2)
        c.observe(2,2);self.assertEqual(c.choose(4)['k'],3)
        self.assertEqual(c.choose(4)['k'],3)
        for _ in range(8):c.observe(0,3)
        self.assertEqual(c.choose(4)['k'],2)
        for _ in range(8):c.observe(1,2)
        self.assertEqual(c.choose(4)['reason'],'hysteresis-band')
        self.assertEqual(c.choose(1)['k'],1)
        c.observe(8,4)
        self.assertEqual(c.choose(4)['k'],4)
        self.assertTrue(c.fallback)

    def test_only_contiguous_accepted_prefix_excludes_recovery_or_bonus(self):
        self.assertEqual(accepted_prefix([9,-1,-1,-1,-1],4),0)
        self.assertEqual(accepted_prefix([1,2,9,-1,-1],4),2)
        self.assertEqual(accepted_prefix([1,2,3,4,9],4),4)
        self.assertEqual(accepted_prefix([9,-1,-1,-1,-1],0),0)
        with self.assertRaises(ValueError):accepted_prefix([1,-1,2,-1,-1],4)
        with self.assertRaises(ValueError):accepted_prefix([-1,-1],1)
