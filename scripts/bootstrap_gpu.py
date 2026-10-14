"""Rebuild the frozen GPU environment in a fresh directory; never replace an existing one."""

import argparse
from pathlib import Path
import subprocess
import sys

parser = argparse.ArgumentParser()
parser.add_argument("--env", type=Path, required=True)
parser.add_argument("--uv", type=Path, required=True)
parser.add_argument("--cache", type=Path, required=True)
parser.add_argument("--index", default="https://mirrors.cloud.tencent.com/pypi/simple")
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
if args.env.exists():
    raise SystemExit("destination already exists; select a fresh directory, no environment is deleted")
uv = [str(args.uv), "--cache-dir", str(args.cache)]
subprocess.run(uv + ["venv", "--python", sys.executable, str(args.env)], check=True)
python = str(args.env / "bin/python")
subprocess.run(uv + ["pip", "sync", "--python", python, "--index-url", args.index,
                    str(root / "requirements/gpu.lock.txt")], check=True)
subprocess.run([python, "-m", "pip", "check"], check=True)
subprocess.run([python, "-m", "driveserve", "gpu-smoke"], cwd=root, check=True)
subprocess.run([python, "-c", "import torch,vllm,transformers; print(torch.__version__,torch.version.cuda,vllm.__version__,transformers.__version__)"], check=True)
print("Fresh GPU environment rebuilt and smoke-tested; actual migration was not performed.")
