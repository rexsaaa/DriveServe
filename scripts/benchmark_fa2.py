"""Equivalent FP16 causal GQA Prefill: vLLM FA2 and PyTorch flash SDPA."""

import argparse
import json
from pathlib import Path
import random
import statistics
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from driveserve.evidence import Run, atomic_json

p=argparse.ArgumentParser();p.add_argument("--stage",choices=["S2","S3","S5"],default="S2");p.add_argument("--repeat",type=int,default=0);args=p.parse_args()
root = Path(__file__).resolve().parents[1]
config = {"stage": args.stage, "repeat": args.repeat, "requirement_ids": ["M6-01"], "seed": 17,
          "shapes": [[batch, length] for batch in [1, 4] for length in [128, 512, 1024, 2048]],
          "q_heads": 28, "kv_heads": 4, "head_dim": 128, "dtype": "float16", "causal": True,
          "comparison": "vLLM fa_version=2 versus torch SDPBackend.FLASH_ATTENTION with native GQA",
          "hypothesis": "record actual supported Prefill costs without disabling native flash attention",
          "samples": 20, "calls_per_graph": 10, "atol": 0.003, "rtol": 0.003}
run = Run(root, "fa2-prefill-comparison", config, formal=True)
print(run.path, flush=True)
try:
    import torch
    from torch.nn.attention import sdpa_kernel, SDPBackend
    from torch.profiler import profile, ProfilerActivity
    from vllm.vllm_flash_attn import flash_attn_varlen_func

    torch.manual_seed(17)
    torch.backends.cuda.matmul.allow_tf32 = False
    order_rng, results = random.Random(17), []
    for batch, length in config["shapes"]:
        q = torch.randn(batch * length, 28, 128, device="cuda", dtype=torch.float16)
        k = torch.randn(batch * length, 4, 128, device="cuda", dtype=torch.float16)
        v = torch.randn_like(k)
        cu = torch.arange(batch + 1, device="cuda", dtype=torch.int32) * length
        qt = q.view(batch, length, 28, 128).transpose(1, 2)
        kt = k.view(batch, length, 4, 128).transpose(1, 2)
        vt = v.view(batch, length, 4, 128).transpose(1, 2)

        def fa2():
            return flash_attn_varlen_func(q, k, v, max_seqlen_q=length, max_seqlen_k=length,
                cu_seqlens_q=cu, cu_seqlens_k=cu, causal=True, fa_version=2)

        def torch_flash():
            with sdpa_kernel(SDPBackend.FLASH_ATTENTION):
                return torch.nn.functional.scaled_dot_product_attention(qt, kt, vt, is_causal=True, enable_gqa=True)

        # Explicit FP32 reference has no hidden SDPA dispatch. Compute one
        # sequence at a time to bound memory, while checking every output.
        errors = []
        a, b = fa2().view(batch, length, 28, 128).transpose(1, 2), torch_flash()
        for item in range(batch):
            kf, vf = kt[item].float().repeat_interleave(7, dim=0), vt[item].float().repeat_interleave(7, dim=0)
            scores = (qt[item].float() @ kf.transpose(-1, -2)) / (128 ** 0.5)
            mask = torch.ones(length, length, device="cuda", dtype=torch.bool).triu(1)
            reference = scores.masked_fill(mask, float("-inf")).softmax(-1) @ vf
            for name, actual in [("vllm_fa2", a[item]), ("torch_flash_sdpa", b[item])]:
                torch.testing.assert_close(actual.float(), reference, atol=0.003, rtol=0.003)
                errors.append({"sequence": item, "variant": name, "max_abs_error": (actual.float() - reference).abs().max().item()})
        del scores, reference, kf, vf, a, b
        operations, graphs, kernel_names = {"vllm_fa2": fa2, "torch_flash_sdpa": torch_flash}, {}, {}
        for name, operation in operations.items():
            stream = torch.cuda.Stream()
            stream.wait_stream(torch.cuda.current_stream())
            with torch.cuda.stream(stream):
                for _ in range(10): operation()
            torch.cuda.current_stream().wait_stream(stream)
            torch.cuda.synchronize()
            with profile(activities=[ProfilerActivity.CPU, ProfilerActivity.CUDA]) as prof:
                operation()
                torch.cuda.synchronize()
            prof.export_chrome_trace(str(run.path / f"batch{batch}-length{length}-{name}.json"))
            kernel_names[name] = sorted({e.name for e in prof.events() if e.device_type == torch.autograd.DeviceType.CUDA})
            if not any("flash" in n.lower() for n in kernel_names[name]):
                raise AssertionError(f"No flash kernel observed for {name}")
            graph = torch.cuda.CUDAGraph()
            with torch.cuda.graph(graph):
                for _ in range(config["calls_per_graph"]): operation()
            graphs[name] = graph
            for _ in range(5): graph.replay()
        torch.cuda.synchronize()
        raw = []
        start, end = torch.cuda.Event(enable_timing=True), torch.cuda.Event(enable_timing=True)
        for sample in range(config["samples"]):
            order = list(graphs)
            order_rng.shuffle(order)
            for name in order:
                start.record()
                graphs[name].replay()
                end.record()
                end.synchronize()
                raw.append({"sample": sample, "variant": name, "us": start.elapsed_time(end) * 1000 / config["calls_per_graph"]})
        row = {"batch": batch, "length": length, "errors": errors, "kernels": kernel_names, "raw": raw,
               "median_us": {name: statistics.median(r["us"] for r in raw if r["variant"] == name) for name in graphs}}
        results.append(row)
        atomic_json(run.path / "results.json", results)
        print(json.dumps({"batch": batch, "length": length, "median_us": row["median_us"]}), flush=True)
        del graphs, graph, operations, q, k, v, qt, kt, vt, cu
    run.finish("completed", {"shapes": len(results), "limitations": [
        "Standalone fixed-shape attention; no HTTP, scheduler, KV append, model MLP or end-to-end latency.",
        "Both flash implementations are upstream capabilities, not a project attention algorithm.",
        "Graph Event measurements exclude compilation, allocation, warmup and profiling; 20 samples are one run.",
        "Independent processes and concurrent work must be checked from the stage protocol/run registry; within-run samples alone are not independent repeats."]})
except BaseException as exc:
    run.finish("failed", {"error": str(exc)})
    raise
