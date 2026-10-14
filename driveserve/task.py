"""Versioned, independently rule-labelled structured-text proxy task."""

import hashlib
import json
import math
import random

TASK_VERSION = "proxy-v1"
OUTPUT_KEYS = {"action", "speed_band", "must_yield"}
SCENE_KEYS = {"scene_id", "group_id", "ego_speed_mps", "speed_limit_mps",
              "lead_distance_m", "signal", "pedestrian", "lane_closed", "visibility"}
SPLITS = ("train", "calibration", "dev", "test")
SYSTEM_PROMPT = """You classify synthetic driving scenarios using these toy rules.
Return only one JSON object with exactly action, speed_band, must_yield.
Stop if signal is red, pedestrian is true, lane_closed is true, or a lead
vehicle distance is <= max(5, 0.8 * ego_speed_mps). For stop output:
{"action":"stop","speed_band":"stopped","must_yield":true}.
Otherwise slow if visibility is not clear, or lead distance is less than
2 * ego_speed_mps + 5. For slow output:
{"action":"slow","speed_band":"slow","must_yield":false}.
Otherwise output {"action":"proceed","speed_band":"road_limit","must_yield":false}.
A null lead distance means no lead vehicle. These are proxy classification
rules, not instructions for controlling a real vehicle."""


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def validate_scene(scene):
    if not isinstance(scene, dict) or set(scene) != SCENE_KEYS:
        raise ValueError("scene has missing or unknown fields")
    for key in ("scene_id", "group_id"):
        if not isinstance(scene[key], str) or not scene[key]:
            raise ValueError(f"invalid {key}")
    for key, maximum in (("ego_speed_mps", 60), ("speed_limit_mps", 60), ("lead_distance_m", 1000)):
        value = scene[key]
        if value is None and key == "lead_distance_m":
            continue
        if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= maximum:
            raise ValueError(f"invalid {key}")
    if scene["signal"] not in ("red", "green", "none"):
        raise ValueError("invalid signal")
    if scene["visibility"] not in ("clear", "rain", "fog"):
        raise ValueError("invalid visibility")
    if any(type(scene[key]) is not bool for key in ("pedestrian", "lane_closed")):
        raise ValueError("hazard fields must be booleans")


def label(scene):
    validate_scene(scene)
    distance, speed = scene["lead_distance_m"], scene["ego_speed_mps"]
    stop = (scene["signal"] == "red" or scene["pedestrian"] or scene["lane_closed"]
            or (distance is not None and distance <= max(5, 0.8 * speed)))
    slow = scene["visibility"] != "clear" or (distance is not None and distance < 2 * speed + 5)
    action = "stop" if stop else "slow" if slow else "proceed"
    return {"action": action, "speed_band": {"stop": "stopped", "slow": "slow", "proceed": "road_limit"}[action],
            "must_yield": stop}


def messages(scene):
    validate_scene(scene)
    inputs = {k: v for k, v in scene.items() if k not in ("scene_id", "group_id")}
    return [{"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": canonical(inputs)}]


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate key: {key}")
        result[key] = value
    return result


def score(scene, response):
    expected = label(scene)
    try:
        obj = json.loads(response, object_pairs_hook=_unique_object,
                         parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
        valid = (isinstance(obj, dict) and set(obj) == OUTPUT_KEYS
                 and obj["action"] in ("stop", "slow", "proceed")
                 and obj["speed_band"] in ("stopped", "slow", "road_limit")
                 and type(obj["must_yield"]) is bool)
    except (ValueError, TypeError):
        obj, valid = {}, False
    fields = {key: bool(valid and obj[key] == value) for key, value in expected.items()}
    return {"json_valid": valid, "exact_match": all(fields.values()), "fields": fields,
            "expected": expected}


def generate(seed=20261014, groups_per_split=8, variants=4):
    if groups_per_split < 1 or variants < 1:
        raise ValueError("dataset dimensions must be positive")
    rng = random.Random(seed)
    records = []
    for split in SPLITS:
        for group in range(groups_per_split):
            group_id = f"{TASK_VERSION}-{seed}-{split}-{group:04d}"
            # Variants of one route stay in one split; the template is deliberately shared.
            speed_limit = round(rng.uniform(8, 25), 3)
            for variant in range(variants):
                scene = {"scene_id": f"{group_id}-{variant:02d}", "group_id": group_id,
                         "ego_speed_mps": round(rng.uniform(0, speed_limit), 3),
                         "speed_limit_mps": speed_limit,
                         "lead_distance_m": None if rng.random() < .3 else round(rng.uniform(2, 100), 3),
                         "signal": rng.choice(("none", "none", "green", "red")),
                         "pedestrian": rng.random() < .1, "lane_closed": rng.random() < .05,
                         "visibility": rng.choice(("clear", "clear", "clear", "rain", "fog"))}
                records.append({"task_version": TASK_VERSION, "split": split, "scene": scene, "label": label(scene)})
    audit_dataset(records)
    return records


def audit_dataset(records):
    groups, ids, contents = {}, set(), set()
    for record in records:
        if record["task_version"] != TASK_VERSION or record["split"] not in SPLITS:
            raise ValueError("unknown task version or split")
        scene, split = record["scene"], record["split"]
        validate_scene(scene)
        if record["label"] != label(scene):
            raise ValueError("label mismatch")
        if scene["scene_id"] in ids:
            raise ValueError("duplicate scene ID")
        ids.add(scene["scene_id"])
        if scene["group_id"] in groups and groups[scene["group_id"]] != split:
            raise ValueError("group leaks across splits")
        groups[scene["group_id"]] = split
        content = digest({k: v for k, v in scene.items() if k not in ("scene_id", "group_id")})
        if content in contents:
            raise ValueError("duplicate scenario content")
        contents.add(content)
    return {"records": len(records), "groups": len(groups),
            "splits": {split: sum(r["split"] == split for r in records) for split in SPLITS}}
