"""Derive a tied-embedding Qwen Draft with zero-filled extra rows; never modify Target."""

import argparse
import json
from pathlib import Path
import shutil
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from driveserve.evidence import Run, atomic_json, file_hash

parser = argparse.ArgumentParser()
parser.add_argument("--source", type=Path, required=True)
parser.add_argument("--target", type=Path, required=True)
parser.add_argument("--destination", type=Path, required=True)
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
if args.destination.exists():
    raise SystemExit("destination exists; choose a new version, no weights are overwritten")
source = json.loads((args.source / "driveserve-provenance.json").read_text())
target = json.loads((args.target / "config.json").read_text())
draft = json.loads((args.source / "config.json").read_text())
if draft.get("model_type") != "qwen2" or draft.get("tie_word_embeddings") is not True:
    raise SystemExit("supported scope is Qwen2 with tied embeddings")
if any(draft[key] != target[key] for key in ("bos_token_id", "eos_token_id")):
    raise SystemExit("special token IDs differ")
if file_hash(args.source / "tokenizer.json") != file_hash(args.target / "tokenizer.json"):
    raise SystemExit("tokenizers differ")
old, new = draft["vocab_size"], target["vocab_size"]
if new <= old:
    raise SystemExit("only strictly extending the Draft vocabulary is supported")
if shutil.disk_usage(args.destination.parent).free < 7 * 1024 ** 3:
    raise SystemExit("need at least 7 GiB free space for artifact and reserve")
run = Run(root, "draft-vocabulary-alignment", {"model": source["model"], "old_vocab_size": old,
           "new_vocab_size": new, "fill": "zeros", "target_config_sha256": file_hash(args.target / "config.json"),
           "hypothesis": "equal logits dimensions permit the native rejection sampler; target weights remain unchanged"})
try:
    import torch
    from safetensors import safe_open
    from safetensors.torch import load_file, save_file
    for asset in source["files"]:
        file = args.source / Path(asset["path"]).name
        if file.stat().st_size != asset["bytes"] or file_hash(file) != asset["sha256"]:
            raise ValueError(f"source artifact checksum failed: {file.name}")
    weights = load_file(args.source / "model.safetensors", device="cpu")
    key = "model.embed_tokens.weight"
    if "lm_head.weight" in weights or weights[key].shape[0] != old:
        raise ValueError("unsupported untied/alternate weight layout")
    original = weights[key]
    padded = torch.zeros((new, original.shape[1]), dtype=original.dtype)
    padded[:old].copy_(original)
    weights[key] = padded
    args.destination.mkdir()
    for asset in source["files"]:
        name = Path(asset["path"]).name
        if name != "config.json" and not name.endswith(".safetensors"):
            shutil.copy2(args.source / name, args.destination / name)
    draft["vocab_size"] = new
    atomic_json(args.destination / "config.json", draft)
    save_file(weights, args.destination / "model.safetensors", metadata={"format": "pt"})
    with safe_open(args.source / "model.safetensors", framework="pt") as before, safe_open(args.destination / "model.safetensors", framework="pt") as after:
        if set(before.keys()) != set(after.keys()):
            raise ValueError("tensor key set changed")
        for name in before.keys():
            a, b = before.get_tensor(name), after.get_tensor(name)
            if not torch.equal(a, b[:old] if name == key else b):
                raise ValueError(f"existing tensor values changed: {name}")
        if torch.count_nonzero(after.get_tensor(key)[old:]).item() != 0:
            raise ValueError("extra embedding rows are not zero")
    files = [{"path": str(p), "bytes": p.stat().st_size, "sha256": file_hash(p)}
             for p in sorted(args.destination.iterdir()) if p.is_file()]
    provenance = {"model": source["model"], "files": files, "run_id": run.manifest["run_id"],
                  "derivation": {"operation": "extend tied draft embedding with zeros", "source_revision": source["model"]["revision"],
                                 "old_vocab_size": old, "new_vocab_size": new, "training_performed": False,
                                 "existing_tensor_values": "bitwise preserved", "target_modified": False,
                                 "limitation": "Draft proposal distribution may change; this is not distillation or measured acceleration"}}
    atomic_json(args.destination / "driveserve-provenance.json", provenance)
    atomic_json(run.path / "artifact-index.json", provenance)
    run.finish("completed", provenance["derivation"])
except BaseException as exc:
    run.finish("failed", {"error": str(exc)})
    raise
print(run.manifest["run_id"], flush=True)
