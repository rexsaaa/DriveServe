"""Real V0 engine diagnostic with fixed synthetic mixed-length, repeated-prefix inputs."""

import argparse
import json
import os
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from driveserve.evidence import Run, atomic_json, file_hash


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--overlay", type=Path, required=True)
    parser.add_argument("--trace", action="store_true")
    parser.add_argument("--model", type=Path, default=Path("/hy-tmp/driveserve/models/target"))
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    overlay = args.overlay.resolve()
    overlay_manifest = json.loads((overlay / "overlay-manifest.json").read_text())
    if overlay_manifest["patch_sha256"] != file_hash(root / "patches/vllm-v0.8.5-observers.patch"):
        raise ValueError("overlay patch differs from current source")
    for entry in overlay_manifest["lock"]["files"]:
        if file_hash(overlay / entry["path"]) != entry["patched_sha256"]:
            raise ValueError("overlay source changed")
    provenance = json.loads((args.model / "driveserve-provenance.json").read_text())
    for entry in provenance["files"]:
        if file_hash(args.model / Path(entry["path"]).name) != entry["sha256"]:
            raise ValueError("model artifact changed")
    config = {"stage": "S2", "requirement_ids": ["M1-01", "M1-02", "M1-03"],
              "hypothesis": "optional engine observers expose real scheduling, prefix reuse and KV lifetime",
              "trace": args.trace, "overlay": overlay_manifest, "model": provenance,
              "seed": 23, "prompt_lengths": [1024, 96, 768, 128, 1536, 96, 512, 256],
              "waves": 3, "output_tokens": 32, "hot_indices": [0, 3, 6],
              "max_num_seqs": 4, "max_model_len": 2048, "num_gpu_blocks_override": 512,
              "block_size": 16, "dtype": "float16", "prefix_caching": True, "eager": True,
              "data_scope": "synthetic token-length/cache diagnostic; no business quality score or final test",
              "measurement_scope": "host engine execution; not HTTP service latency or GPU kernel time"}
    run = Run(root, "vllm-engine-diagnostic", config, formal=True)
    print(run.path, flush=True)
    try:
        os.environ.update(VLLM_USE_V1="0", VLLM_ATTENTION_BACKEND="FLASH_ATTN",
                          CUDA_VISIBLE_DEVICES="0", HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1",
                          PYTHONPATH=os.pathsep.join([str(overlay), str(root)]))
        if args.trace:
            os.environ["DRIVESERVE_TRACE_DIR"] = str(run.path / "engine-trace")
        else:
            os.environ.pop("DRIVESERVE_TRACE_DIR", None)
        sys.path.insert(0, str(overlay))
        from vllm import EngineArgs, LLMEngine, SamplingParams
        from vllm.core import scheduler
        if Path(scheduler.__file__).resolve() != overlay / "vllm/core/scheduler.py":
            raise ValueError("engine did not import isolated patched source")
        engine = LLMEngine.from_engine_args(EngineArgs(
            model=str(args.model), dtype="half", max_model_len=2048, max_num_seqs=4,
            max_num_batched_tokens=2048, gpu_memory_utilization=0.4,
            num_gpu_blocks_override=512, block_size=16, enable_prefix_caching=True,
            enforce_eager=True, seed=23, disable_log_stats=True))
        tokenizer = engine.get_tokenizer()
        sampling = SamplingParams(temperature=0, max_tokens=32, ignore_eos=True, seed=23,
                                  repetition_penalty=1.05)
        # A separate prefix warms the execution path without warming measured prefixes.
        engine.add_request("warmup", {"prompt_token_ids": tokenizer.encode("Warmup scenario. " * 20)}, sampling)
        while engine.has_unfinished_requests():
            engine.step()
        workload, results, steps = [], [], []
        for wave in range(config["waves"]):
            submitted = {}
            wave_start = time.perf_counter_ns()
            for index, length in enumerate(config["prompt_lengths"]):
                group = f"hot-{index}" if index in config["hot_indices"] else f"novel-{wave}-{index}"
                # Put group identity near the beginning so novel traffic does not
                # unintentionally share all full prefix blocks with hot traffic.
                tokens = tokenizer.encode(f"Scene {group}: " + "road dry lane clear speed moderate. " * 400)[:length]
                if len(tokens) != length:
                    raise ValueError("synthetic prompt construction too short")
                request_id = f"wave-{wave}-item-{index}"
                workload.append({"request_id": request_id, "wave": wave, "group": group,
                                 "tokens": tokens, "hot": index in config["hot_indices"]})
                submitted[request_id] = time.perf_counter_ns()
                engine.add_request(request_id, {"prompt_token_ids": tokens}, sampling)
            atomic_json(run.path / "workload.json", workload)
            while engine.has_unfinished_requests():
                before = time.perf_counter_ns()
                outputs = engine.step()
                after = time.perf_counter_ns()
                steps.append({"wave": wave, "started_ns": before, "host_step_ns": after - before})
                for output in outputs:
                    if not output.finished:
                        continue
                    results.append({"request_id": output.request_id, "wave": wave,
                                    "elapsed_ns": after - submitted[output.request_id],
                                    "num_cached_tokens": getattr(output, "num_cached_tokens", None),
                                    "output_token_ids": list(output.outputs[0].token_ids),
                                    "finish_reason": output.outputs[0].finish_reason})
            atomic_json(run.path / "results.json", results)
            atomic_json(run.path / "steps.json", steps)
            print(json.dumps({"wave": wave, "completed": len(results),
                              "wave_elapsed_s": (time.perf_counter_ns() - wave_start) / 1e9}), flush=True)
        if len(results) != len(workload) or len({r["request_id"] for r in results}) != len(workload):
            raise AssertionError("missing or duplicate finished requests")
        if any(len(r["output_token_ids"]) != 32 for r in results):
            raise AssertionError("unexpected output length")
        from driveserve.engine_trace import close_traces
        os.environ.pop("DRIVESERVE_TRACE_DIR", None)
        close_traces()
        run.finish("completed", {"requests": len(results), "host_steps": len(steps),
                                "trace": args.trace, "safety_scope": "Synthetic inference diagnostics only"})
    except BaseException as exc:
        from driveserve.engine_trace import close_traces
        os.environ.pop("DRIVESERVE_TRACE_DIR", None)
        close_traces()
        run.finish("failed", {"error": str(exc)})
        raise


if __name__ == "__main__":
    main()
