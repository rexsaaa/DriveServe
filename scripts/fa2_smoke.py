"""Exercise vLLM's FA2 prefill kernel against an FP32 causal GQA reference."""

import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from driveserve.evidence import Run, atomic_json

root = Path(__file__).resolve().parents[1]
config = {"seed": 17, "dtype": "float16", "device": "cuda:0", "q_heads": 28,
          "kv_heads": 4, "head_dim": 128, "lengths": [127, 512], "causal": True,
          "fa_version": 2, "atol": 0.003, "rtol": 0.003,
          "hypothesis": "the installed vLLM FA2 prefill kernel executes and agrees with FP32 math"}
run = Run(root, "fa2-kernel-smoke", config, formal=True)
try:
    import torch
    from torch.profiler import profile, ProfilerActivity
    from vllm.vllm_flash_attn import flash_attn_varlen_func

    torch.manual_seed(config["seed"])
    torch.backends.cuda.matmul.allow_tf32 = False
    results = []
    for length in config["lengths"]:
        q = torch.randn(length, 28, 128, device="cuda", dtype=torch.float16)
        k = torch.randn(length, 4, 128, device="cuda", dtype=torch.float16)
        v = torch.randn_like(k)
        cu = torch.tensor([0, length], device="cuda", dtype=torch.int32)
        def execute():
            return flash_attn_varlen_func(q, k, v, max_seqlen_q=length,
                                         max_seqlen_k=length, cu_seqlens_q=cu,
                                         cu_seqlens_k=cu, causal=True, fa_version=2)
        # The reference explicitly expands GQA and uses FP32 matmul/softmax,
        # so it cannot silently dispatch to the same attention kernel.
        qf = q.float().transpose(0, 1)
        kf = k.float().repeat_interleave(7, dim=1).transpose(0, 1)
        vf = v.float().repeat_interleave(7, dim=1).transpose(0, 1)
        logits = (qf @ kf.transpose(-1, -2)) / (128 ** 0.5)
        mask = torch.ones(length, length, device="cuda", dtype=torch.bool).triu(1)
        reference = (logits.masked_fill(mask, float("-inf")).softmax(-1) @ vf).transpose(0, 1)
        execute()
        torch.cuda.synchronize()
        with profile(activities=[ProfilerActivity.CPU, ProfilerActivity.CUDA]) as prof:
            actual = execute()
            torch.cuda.synchronize()
        prof.export_chrome_trace(str(run.path / f"fa2-{length}-trace.json"))
        names = sorted({event.name for event in prof.events()
                        if event.device_type == torch.autograd.DeviceType.CUDA})
        error = (actual.float() - reference).abs()
        row = {"length": length, "max_abs_error": error.max().item(),
               "mean_abs_error": error.mean().item(), "cuda_kernel_names": names,
               "allclose": torch.allclose(actual.float(), reference, atol=0.003, rtol=0.003)}
        results.append(row)
        atomic_json(run.path / "results.json", results)
        if not row["allclose"]:
            raise AssertionError(f"FA2 reference mismatch for length {length}")
        if not any("flash" in name.lower() and "fwd" in name.lower() for name in names):
            raise AssertionError("profiler did not observe a FlashAttention forward CUDA kernel")
    result = {"cases": results, "limitations": [
        "Synthetic single-sequence causal FP16 GQA prefill only; not a performance comparison.",
        "This calls the upstream kernel; no custom attention or fused RoPE/KV implementation.",
        "PyTorch profiler evidence is not a substitute for the required Nsight Systems timeline."]}
    run.finish("completed", result)
except BaseException as exc:
    run.finish("failed", {"error": str(exc)})
    raise
print(json.dumps({"run_id": run.manifest["run_id"], "result": result}, indent=2))
