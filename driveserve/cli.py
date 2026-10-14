import argparse
import json
from pathlib import Path

from .evidence import Run, atomic_json, environment, file_hash, process_alive, verify_assets
from .task import audit_dataset, canonical, generate, label, messages, score


def main():
    parser = argparse.ArgumentParser(prog="driveserve")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("doctor")
    commands.add_parser("status")
    gpu = commands.add_parser("gpu-smoke")
    gpu.add_argument("--formal", action="store_true")
    data = commands.add_parser("data")
    data.add_argument("--output", type=Path, required=True)
    data.add_argument("--seed", type=int, default=20261014)
    data.add_argument("--groups", type=int, default=8)
    data.add_argument("--variants", type=int, default=4)
    demo = commands.add_parser("demo")
    demo.add_argument("--dataset", type=Path, required=True)
    bench = commands.add_parser("bench")
    bench.add_argument("--dataset", type=Path, required=True)
    bench.add_argument("--endpoint", default="http://127.0.0.1:8000/v1")
    bench.add_argument("--model", required=True)
    bench.add_argument("--concurrency", type=int, default=1)
    bench.add_argument("--limit", type=int, default=16)
    bench.add_argument("--split", default="dev", choices=("dev", "test"))
    bench.add_argument("--timeout", type=float, default=120)
    bench.add_argument("--max-tokens", type=int, default=128)
    bench.add_argument("--service-manifest", type=Path)
    recovery = commands.add_parser("recovery")
    recovery.add_argument("--dataset", type=Path, required=True)
    recovery.add_argument("--state-dir", type=Path, required=True)
    recovery.add_argument("--delay", type=float, default=0)
    recovery.add_argument("--stop-after", type=int)
    verify = commands.add_parser("verify")
    verify.add_argument("manifest", type=Path)
    args = parser.parse_args()
    if args.command == "status":
        result = []
        for path in sorted((args.root / "experiments/runs").glob("*/manifest.json")):
            manifest = json.loads(path.read_text())
            result.append({"run_id": manifest["run_id"], "kind": manifest["kind"],
                           "recorded_status": manifest["status"],
                           "owner_alive": process_alive(manifest.get("process")),
                           "child_alive": process_alive(manifest.get("child_process")),
                           "heartbeat_at": manifest.get("heartbeat_at"), "manifest": str(path)})
    elif args.command == "doctor":
        result = environment(args.root)
    elif args.command == "gpu-smoke":
        run = Run(args.root, "gpu-matmul-smoke", {"model": "not applicable: tensor arithmetic only"}, formal=args.formal)
        try:
            import torch
            if not torch.cuda.is_available():
                raise RuntimeError("no CUDA device")
            devices = []
            for index in range(torch.cuda.device_count()):
                with torch.cuda.device(index):
                    expected = torch.arange(256, dtype=torch.float32).reshape(16, 16)
                    data = expected.to(f"cuda:{index}")
                    actual = data @ data.T
                    torch.cuda.synchronize()
                    torch.testing.assert_close(actual.cpu(), expected @ expected.T)
                    devices.append({"index": index, "name": torch.cuda.get_device_name(index),
                                    "total_memory": torch.cuda.get_device_properties(index).total_memory,
                                    "matmul": "passed"})
            result = {"torch": torch.__version__, "cuda": torch.version.cuda, "devices": devices,
                      "limitation": "tensor arithmetic in the recorded interpreter; no vLLM model execution"}
            atomic_json(run.path / "result.json", result)
            run.finish("completed", result)
        except BaseException as exc:
            run.finish("failed", {"error": str(exc)})
            raise
        result = {"run_id": run.manifest["run_id"], "result": result}
    elif args.command == "data":
        records = generate(args.seed, args.groups, args.variants)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        text = "".join(canonical(row) + "\n" for row in records)
        if args.output.exists() and args.output.read_text() != text:
            raise ValueError("refusing to replace a different dataset; choose a new version/path")
        args.output.write_text(text)
        result = {**audit_dataset(records), "sha256": file_hash(args.output), "seed": args.seed,
                  "source": "self-generated synthetic proxy-v1 rules; no teacher labels",
                  "generator": "driveserve.task.generate", "groups_per_split": args.groups,
                  "variants_per_group": args.variants, "frozen_final_test": False,
                  "limitation": "small development fixture; no real driving validity"}
        atomic_json(args.output.with_suffix(".manifest.json"), result)
    elif args.command == "demo":
        record = json.loads(args.dataset.read_text().splitlines()[0])
        response = canonical(label(record["scene"]))
        result = {"mode": "rule-oracle-demo-no-model", "messages": messages(record["scene"]),
                  "response": response, "score": score(record["scene"], response)}
    elif args.command == "bench":
        from .benchmark import benchmark
        service = json.loads(args.service_manifest.read_text()) if args.service_manifest else None
        if service and service["config"]["served_model_name"] != args.model:
            raise ValueError("service manifest model name differs from client model")
        run = benchmark(args.root, args.dataset, args.endpoint, args.model, args.split,
                        args.concurrency, args.limit, args.timeout, args.max_tokens, service_manifest=service)
        result = {"run_id": run.manifest["run_id"], "status": run.manifest["status"]}
    elif args.command == "recovery":
        from .recovery import recoverable_job
        run = recoverable_job(args.root, args.dataset, args.state_dir, args.delay, args.stop_after)
        result = {"run_id": run.manifest["run_id"], "status": run.manifest["status"], "result": run.manifest["result"]}
    else:
        manifest = json.loads(args.manifest.read_text())
        result = {"verified_assets": verify_assets(args.root, manifest), "status": manifest["status"],
                  "original_process_alive": process_alive(manifest["process"])}
    print(json.dumps(result, ensure_ascii=False, indent=2))
