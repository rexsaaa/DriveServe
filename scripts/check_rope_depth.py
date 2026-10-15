"""S4 head-tile/half2 ablation against unchanged v1 and native separate kernels."""

import argparse
import json
from pathlib import Path
import random
import statistics
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from driveserve.evidence import Run, atomic_json

parser = argparse.ArgumentParser()
parser.add_argument("--stage", choices=["S2","S3","S4","S5"], default="S4")
parser.add_argument("--repeat", type=int, default=0)
parser.add_argument("--quick", action="store_true", help="boundary subset for compute-sanitizer")
parser.add_argument("--benchmark", action="store_true")
parser.add_argument("--sanitizer", action="store_true")
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
lengths = [0, 1, 17, 33] if args.quick else [0, 1, 2, 15, 16, 17, 31, 32, 33, 127, 512, 2048]
config = {"stage": args.stage, "repeat": args.repeat, "requirement_ids": ["M5-02", "M5-03", "M5-04"], "seed": 23,
          "dtype": "float16", "q_heads": 28, "kv_heads": 4, "head_dim": 128,
          "lengths": lengths, "block_sizes": [16, 32], "row_padding": [0, 1, 128],
          "benchmark": args.benchmark, "sanitizer": args.sanitizer,
          "reference_atol": 0.002, "reference_rtol": 0.002,
          "hypothesis": "head tiling and half2 change parallelism and instruction work while retaining FP16 rounding", "variants": ["upstream_separate","project_v1","tiled_scalar","tiled_half2","dispatch"], "dispatch_cutoff":32}
run = Run(root, "rope-cache-depth-validation", config, formal=True)
print(run.path, flush=True)
try:
    import torch
    from vllm import _custom_ops as ops
    from driveserve.rope_cache import extension_v2, fused_v2, half2_compatible, validate_indices

    torch.manual_seed(config["seed"])
    module = extension_v2()
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
    def candidate(variant, projection, positions, cache, slots):
        if variant=='v1':module.fused(projection,positions,table,cache,slots)
        elif variant=='scalar':module.tiled(projection,positions,table,cache,slots,False)
        elif variant=='half2':module.tiled(projection,positions,table,cache,slots,True)
        else:fused_v2(projection,positions,table,cache,slots,variant='auto')

    for length in lengths:
        for block_size in config["block_sizes"]:
            for padding in config["row_padding"]:
                storage, projection, positions, cache, slots = make_inputs(length, block_size, padding)
                pristine = storage.clone()
                expected_projection, expected_cache = reference(projection, positions, cache, slots)
                baseline_storage, baseline_cache = storage.clone(), cache.clone()
                baseline_projection = baseline_storage[:, :36 * 128].view(length, 36, 128)
                upstream(baseline_projection, positions, baseline_cache, slots)
                variants=['v1','scalar','auto']
                if half2_compatible(projection,table,cache):variants.append('half2')
                for variant in variants:
                    data=pristine.clone();actual_cache=cache.clone()
                    actual=data[:,:36*128].view(length,36,128)
                    candidate(variant,actual,positions,actual_cache,slots)
                    torch.cuda.synchronize()
                    torch.testing.assert_close(actual,baseline_projection,atol=0,rtol=0)
                    torch.testing.assert_close(actual_cache,baseline_cache,atol=0,rtol=0)
                    torch.testing.assert_close(actual,expected_projection,atol=0.002,rtol=0.002)
                    torch.testing.assert_close(actual_cache,expected_cache,atol=0.002,rtol=0.002)
                    torch.testing.assert_close(data[:,36*128:],pristine[:,36*128:],atol=0,rtol=0)
                    torch.testing.assert_close(actual[:,32:],pristine[:,32*128:36*128].view(length,4,128),atol=0,rtol=0)
                    unused=torch.ones(cache.shape[1]*block_size,dtype=torch.bool,device='cuda')
                    unused[slots[slots>=0]]=False
                    assert (actual_cache.view(2,-1,4,128)[:,unused]==-19.5).all().item()
                    cases.append({'tokens':length,'block_size':block_size,'padding':padding,'variant':variant,
                        'exact_upstream_agreement':True,'untouched_slots_and_padding':True,
                        'reference_max_abs_error':(actual-expected_projection).abs().max().item() if length else 0.0})
                atomic_json(run.path/'correctness.json',cases)
    # Pointer alignment is distinct from contiguity. Exercise half-offset
    # storage for each half2 input, reject the explicit vector path, and keep
    # the auto scalar fallback equivalent to the native separate operations.
    for aliased_name in ['projection','table','cache']:
        source,projection,positions,cache,slots=make_inputs(17,16,0)
        original_table=table
        if aliased_name=='projection':
            storage=torch.empty(projection.numel()+1,device='cuda',dtype=torch.float16)
            storage[1:].copy_(projection.reshape(-1));projection=storage[1:].view_as(projection)
        elif aliased_name=='table':
            storage=torch.empty(table.numel()+1,device='cuda',dtype=torch.float16)
            storage[1:].copy_(table.reshape(-1));table=storage[1:].view_as(table)
        else:
            storage=torch.empty(cache.numel()+1,device='cuda',dtype=torch.float16)
            storage[1:].copy_(cache.reshape(-1));cache=storage[1:].view_as(cache)
        expected=projection.clone();expected_cache=cache.clone()
        saved_table=table;table=table.clone()
        upstream(expected,positions,expected_cache,slots)
        table=saved_table
        pristine_projection=projection.clone();pristine_cache=cache.clone()
        try:module.tiled(projection,positions,table,cache,slots,True)
        except RuntimeError as exc:assert 'half2 requires aligned' in str(exc)
        else:raise AssertionError('unaligned vector path accepted')
        torch.testing.assert_close(projection,pristine_projection,atol=0,rtol=0)
        torch.testing.assert_close(cache,pristine_cache,atol=0,rtol=0)
        fused_v2(projection,positions,table,cache,slots,variant='auto')
        torch.cuda.synchronize()
        torch.testing.assert_close(projection,expected,atol=0,rtol=0)
        torch.testing.assert_close(cache,expected_cache,atol=0,rtol=0)
        cases.append({'unaligned_input':aliased_name,'half2_rejected':True,'auto_matches_upstream':True})
        table=original_table
    source,_,positions,cache,slots=make_inputs(17,16,0)
    values=torch.tensor([0.0,-0.0,2**-24,-2**-24,2**-14,-2**-14,.33325,-.33325,65504.,-65504.],device='cuda',dtype=torch.float16)
    source.copy_(values.repeat((source.numel()+len(values)-1)//len(values))[:source.numel()].view_as(source))
    expected=source.view(17,36,128).clone();expected_cache=cache.clone()
    upstream(expected,positions,expected_cache,slots)
    for variant in ['v1','scalar','half2','auto']:
        actual=source.view(17,36,128).clone();actual_cache=cache.clone()
        candidate(variant,actual,positions,actual_cache,slots);torch.cuda.synchronize()
        torch.testing.assert_close(actual,expected,atol=0,rtol=0,equal_nan=True)
        torch.testing.assert_close(actual_cache,expected_cache,atol=0,rtol=0,equal_nan=True)
        cases.append({'case':'finite_extremes_subnormals_signed_zero','variant':variant,'matches_upstream':True,
            'note':'finite inputs can overflow after FP16 arithmetic; equal infinities/NaNs are accepted as upstream semantics, not finite-output guarantees'})
    atomic_json(run.path/'correctness.json',cases)

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
            for variant in ('upstream_separate','project_v1','tiled_scalar','tiled_half2','dispatch'):
                data, cache = source.clone(), template_cache.clone()
                projection = data.view(length,36,128)
                if variant=='upstream_separate': execute=lambda:upstream(projection,positions,cache,slots)
                elif variant=='project_v1': execute=lambda:module.fused(projection,positions,table,cache,slots)
                elif variant=='tiled_scalar': execute=lambda:module.tiled(projection,positions,table,cache,slots,False)
                elif variant=='tiled_half2': execute=lambda:module.tiled(projection,positions,table,cache,slots,True)
                else:
                    # Dispatch is fixed from tensor metadata before graph capture;
                    # host validation/dispatch is excluded, as in S2/S3 timing.
                    execute=(lambda:module.tiled(projection,positions,table,cache,slots,True)) if length<=32 else (
                            lambda:module.fused(projection,positions,table,cache,slots))
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
                "dispatch_vs_separate_latency_reduction": 1 - medians["dispatch"] / medians["upstream_separate"]})
            atomic_json(run.path / "timings.json", timing)
            print(json.dumps({"tokens": length, "median_us": medians}), flush=True)
    result = {"correctness_cases": len(cases), "invalid_inputs_rejected": invalid_rejected,
              "benchmark_shapes": len(timing), "limitations": [
                  "Standalone operator; no vLLM service integration or end-to-end TPOT claim.",
                  "Only FP16 NeoX full-dimension RoPE, packed Q28/KV4 D128 projection and contiguous FA-layout cache.",
                  "Graph microbenchmark is exploratory; 20 samples within one process are not independent experiment repeats.",
                  "Pinned upstream audit from S2/S3 is reused; no claim about later upstream versions.",
                  "Half2 requires 4-byte alignment and even row stride; auto falls back on unaligned small-token data.",
                  "This script retains the S2/S3 v1 kernel as an ablation; no service integration."]}
    run.finish("completed", result)
except BaseException as exc:
    run.finish("failed", {"error": str(exc)})
    raise
print(json.dumps({"run_id": run.manifest["run_id"], "result": result}), flush=True)
