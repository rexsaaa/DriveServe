import copy
import json
import unittest

from driveserve.task import audit_dataset, generate, label, score, messages


class TaskTest(unittest.TestCase):
    def setUp(self):
        self.scene = {"scene_id": "s", "group_id": "g", "ego_speed_mps": 10,
                      "speed_limit_mps": 20, "lead_distance_m": None, "signal": "green",
                      "pedestrian": False, "lane_closed": False, "visibility": "clear"}

    def test_rules_and_exact_boundary(self):
        self.assertEqual(label(self.scene)["action"], "proceed")
        self.scene["lead_distance_m"] = 8
        self.assertEqual(label(self.scene)["action"], "stop")
        self.scene["lead_distance_m"] = 8.001
        self.assertEqual(label(self.scene)["action"], "slow")
        self.scene["lead_distance_m"] = 25
        self.assertEqual(label(self.scene)["action"], "proceed")
        self.scene["signal"] = "red"
        self.assertEqual(label(self.scene)["action"], "stop")

    def test_scoring_rejects_malformed_and_ambiguous_outputs(self):
        self.assertTrue(score(self.scene, json.dumps(label(self.scene)))["exact_match"])
        invalid = ['{"action":"proceed","action":"stop","speed_band":"stopped","must_yield":true}',
                   '{"action":"proceed","speed_band":"road_limit","must_yield":0}',
                   '{"action":"proceed","speed_band":"road_limit","must_yield":false,"extra":0}',
                   '```json\n{}\n```', 'null', '[]', '{"action":NaN}', '{}']
        for raw in invalid:
            with self.subTest(raw=raw):
                self.assertFalse(score(self.scene, raw)["json_valid"])
        wrong = '{"action":"stop","speed_band":"stopped","must_yield":true}'
        self.assertTrue(score(self.scene, wrong)["json_valid"])
        self.assertFalse(score(self.scene, wrong)["exact_match"])

    def test_no_labels_or_split_ids_in_prompt(self):
        prompt = messages(self.scene)[1]["content"]
        self.assertNotIn("scene_id", prompt)
        self.assertNotIn("group_id", prompt)
        self.assertNotIn("label", prompt)

    def test_splits_and_mutation_detection(self):
        records = generate()
        self.assertEqual(records, generate())
        self.assertEqual(audit_dataset(records)["splits"], dict.fromkeys(("train", "calibration", "dev", "test"), 32))
        bad = copy.deepcopy(records)
        bad[1]["split"] = "test"
        with self.assertRaisesRegex(ValueError, "leaks"):
            audit_dataset(bad)
        bad = copy.deepcopy(records)
        bad[0]["label"]["action"] = "unknown"
        with self.assertRaisesRegex(ValueError, "label mismatch"):
            audit_dataset(bad)

    def test_invalid_numeric_inputs(self):
        for value in (float("nan"), True, -1, 61):
            self.scene["ego_speed_mps"] = value
            with self.assertRaises(ValueError):
                label(self.scene)
