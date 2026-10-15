"""Actual CUDA correctness and equivalent-work CUDA Event microbenchmark."""

import argparse
import json
from pathlib import Path
import random
import statistics
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from driveserve.evidence import Run, atomic_json

parser = argparse.ArgumentParser()
parser.add_argument("--stage", choices=["S2","S3","S4","S5"], default="S2")
parser.add_argument("--repeat", type=int, default=0)
parser.add_argument("--quick", action="store_true", help="boundary subset for compute-sanitizer")
parser.add_argument("--benchmark", action="store_true")
parser.add_argument("--sanitizer", action="store_true")
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
lengths = [0, 1, 17, 33] if args.quick else [0, 1, 2, 15, 16, 17, 31, 32, 33, 127, 512, 2048]
config = {"stage": args.stage, "repeat": args.repeat, "requirement_ids": ["M5-02", "M5-03", "M5-04"], "seed": 23,
          "dtype": "float16", "q_heads": 28, "kv_heads": 4, "head_dim": 128,
          "lengths": lengths, "block_sizes": [16, 32], "row_padding": [0, 128],
          "benchmark": args.benchmark, "sanitizer": args.sanitizer,
          "reference_atol": 0.002, "reference_rtol": 0.002,
          "hypothesis": "one custom CUDA launch reproduces upstream NeoX RoPE plus FA-layout KV append"}
run = Run(root, "rope-cache-cuda-validation", config, formal=True)
print(run.path, flush=True)
try:
    import torch
    from vllm import _custom_ops as ops
    from driveserve.rope_cache import extension, fused, validate_indices

    torch.manual_seed(config["seed"])
    module = extension()
    positions_capacity = 4096
    freqs = torch.outer(torch.arange(positions_capacity, device="cuda", dtype=torch.float32),
                        1.0 / (1_000_000 ** (torch.arange(0, 128, 2, device="cuda").float() / 128)))
    table = torch.cat((freqs.cos(), freqs.sin()), dim=1).half()
    scale = torch.tensor(1.0, device="cuda")

    def upstream(projection, positions, cache, slots):
        if projection.shape[0] == 0:
            return
        ops.rotary_embedding(positions, projection[:, :28], projection[:, 28:32], 128, table, True)
        ops.reshape_and_cache_flash(projection[:, 28:32], projection[:, 32:], cache[0], cache[1],
                                    slots, "auto", scale, scale)

    def make_inputs(length, block_size, padding):
        storage = torch.randn(length, 36 * 128 + padding, device="cuda", dtype=torch.float16)
        projection = storage[:, :36 * 128].view(length, 36, 128)
        blocks = (length + block_size - 1) // block_size + 3
        cache = torch.full((2, blocks, block_size, 4, 128), -19.5, device="cuda", dtype=torch.float16)
        capacity = blocks * block_size
        slots = torch.randperm(capacity - 2, device="cuda")[:length] + 1
        positions = torch.randint(0, positions_capacity, (length,), device="cuda")
        if length:
            positions[0] = 0
            positions[-1] = positions_capacity - 1
            slots[-1] = capacity - 1
        if length > 1:
            slots[0] = -1
        if length > 2:
            slots[1] = 0
        validate_indices(positions, slots, positions_capacity, capacity)
        return storage, projection, positions, cache, slots

    def reference(projection, positions, cache, slots):
        output = projection.clone()
        for segment in (slice(None, 28), slice(28, 32)):
            x, y = projection[:, segment, :64], projection[:, segment, 64:]
            cosine, sine = table[positions, :64, None].transpose(1, 2), table[positions, 64:, None].transpose(1, 2)
            output[:, segment, :64] = x * cosine - y * sine
            output[:, segment, 64:] = y * cosine + x * sine
        result = cache.clone()
        valid = slots >= 0
        result[0].view(-1, 4, 128)[slots[valid]] = output[valid, 28:32]
        result[1].view(-1, 4, 128)[slots[valid]] = projection[valid, 32:]
        return output, result

    cases = []
    for length in lengths:
        for block_size in config["block_sizes"]:
            for padding in config["row_padding"]:
                storage, projection, positions, cache, slots = make_inputs(length, block_size, padding)
                pristine = storage.clone()
                expected_projection, expected_cache = reference(projection, positions, cache, slots)
                baseline_storage, baseline_cache = storage.clone(), cache.clone()
                baseline_projection = baseline_storage[:, :36 * 128].view(length, 36, 128)
                upstream(baseline_projection, positions, baseline_cache, slots)
                fused(projection, positions, table, cache, slots)
                torch.cuda.synchronize()
                torch.testing.assert_close(projection, baseline_projection, atol=0, rtol=0)
                torch.testing.assert_close(cache, baseline_cache, atol=0, rtol=0)
                torch.testing.assert_close(projection, expected_projection, atol=0.002, rtol=0.002)
                torch.testing.assert_close(cache, expected_cache, atol=0.002, rtol=0.002)
                torch.testing.assert_close(storage[:, 36 * 128:], pristine[:, 36 * 128:], atol=0, rtol=0)
                torch.testing.assert_close(projection[:, 32:], pristine[:, 32 * 128:36 * 128].view(length, 4, 128), atol=0, rtol=0)
                unused = torch.ones(cache.shape[1] * block_size, dtype=torch.bool, device="cuda")
                unused[slots[slots >= 0]] = False
                assert (cache.view(2, -1, 4, 128)[:, unused] == -19.5).all().item()
                case = {"tokens": length, "block_size": block_size, "padding": padding,
                        "exact_upstream_agreement": True, "untouched_slots_and_padding": True,
                        "reference_max_abs_error": (projection - expected_projection).abs().max().item() if length else 0.0}
                cases.append(case)
                atomic_json(run.path / "correctness.json", cases)
    # Deliberately invalid index data must fail before a kernel launch.
    invalid_rejected = []
    for name, positions_list, slots_list in [("negative_position", [-1], [0]),
        ("past_position_table", [4096], [0]), ("past_cache", [0], [48]),
        ("duplicate_writable_slot", [0, 1], [2, 2])]:
        try:
            validate_indices(torch.tensor(positions_list), torch.tensor(slots_list), 4096, 48)
        except ValueError:
            invalid_rejected.append(name)
        else:
            raise AssertionError(f"invalid input accepted: {name}")
    atomic_json(run.path / "invalid-inputs.json", invalid_rejected)
    print(f"Correctness passed: {len(cases)} CUDA cases and {len(invalid_rejected)} rejected invalid inputs", flush=True)

    timing = []
    if args.benchmark:
        if args.sanitizer:
            raise ValueError("sanitizer runs must not be used for performance measurement")
        order_rng = random.Random(101)
        repetitions_per_graph, samples = 100, 20
        for length in [1, 8, 32, 128, 512, 2048]:
            source, _, positions, template_cache, slots = make_inputs(length, 16, 0)
            states, graphs = {}, {}
            for variant in ("upstream_separate", "project_fused"):
                data, cache = source.clone(), template_cache.clone()
                projection = data.view(length, 36, 128)
                execute = (lambda: upstream(projection, positions, cache, slots)) if variant == "upstream_separate" else (
                    lambda: module.fused(projection, positions, table, cache, slots))
                stream = torch.cuda.Stream()
                stream.wait_stream(torch.cuda.current_stream())
                with torch.cuda.stream(stream):
                    for _ in range(10): execute()
                torch.cuda.current_stream().wait_stream(stream)
                graph = torch.cuda.CUDAGraph()
                with torch.cuda.graph(graph):
                    for _ in range(repetitions_per_graph): execute()
                graphs[variant], states[variant] = graph, (data, cache)
                for _ in range(5): graph.replay()
            torch.cuda.synchronize()
            start, end = torch.cuda.Event(enable_timing=True), torch.cuda.Event(enable_timing=True)
            raw = []
            for sample in range(samples):
                order = list(graphs)
                order_rng.shuffle(order)
                for variant in order:
                    states[variant][0].copy_(source)
                    start.record()
                    graphs[variant].replay()
                    end.record()
                    end.synchronize()
                    raw.append({"sample": sample, "variant": variant,
                                "microseconds_per_call": start.elapsed_time(end) * 1000 / repetitions_per_graph})
            medians = {variant: statistics.median(x["microseconds_per_call"] for x in raw if x["variant"] == variant)
                       for variant in graphs}
            timing.append({"tokens": length, "block_size": 16, "padding": 0,
                "method": "CUDA Event around graph replay of 100 calls; reset/compile/allocation/warmup excluded",
                "samples_per_variant": samples, "calls_per_graph": repetitions_per_graph,
                "median_us": medians, "raw": raw,
                "relative_latency_reduction": 1 - medians["project_fused"] / medians["upstream_separate"]})
            atomic_json(run.path / "timings.json", timing)
            print(json.dumps({"tokens": length, "median_us": medians}), flush=True)
    result = {"correctness_cases": len(cases), "invalid_inputs_rejected": invalid_rejected,
              "benchmark_shapes": len(timing), "limitations": [
                  "Standalone operator; no vLLM service integration or end-to-end TPOT claim.",
                  "Only FP16 NeoX full-dimension RoPE, packed Q28/KV4 D128 projection and contiguous FA-layout cache.",
                  "Graph microbenchmark is exploratory; 20 samples within one process are not independent experiment repeats.",
                  "Applicable upstream fused alternatives still need a final compatibility audit."]}
    run.finish("completed", result)
except BaseException as exc:
    run.finish("failed", {"error": str(exc)})
    raise
print(json.dumps({"run_id": run.manifest["run_id"], "result": result}), flush=True)
