"""Rebuild the frozen GPU environment in a fresh directory with verified wheels."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
from relocate_lock import relocate, digest

parser = argparse.ArgumentParser()
parser.add_argument('--env', type=Path, required=True)
parser.add_argument('--uv', type=Path, required=True)
parser.add_argument('--cache', type=Path, required=True)
parser.add_argument('--wheelhouse', type=Path, help='restored wheel tree; searched recursively by unique basename')
parser.add_argument('--index', default='https://mirrors.cloud.tencent.com/pypi/simple')
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
args.env = args.env.resolve()
if args.env.exists():
    raise SystemExit('destination already exists; select a fresh directory, no environment is deleted')
source_lock = root / 'requirements/gpu.lock.txt'
content, wheels = relocate(source_lock, args.wheelhouse)
uv = [str(args.uv), '--cache-dir', str(args.cache)]
subprocess.run(uv + ['venv', '--python', sys.executable, str(args.env)], check=True)
lock = args.env / 'requirements-relocated.lock.txt'
lock.write_text(content)
(args.env / 'wheel-verification.json').write_text(json.dumps(dict(source_sha256=digest(source_lock),
    resolved_lock_sha256=digest(lock),verified_wheels=wheels),indent=2)+'\n')
python = str(args.env / 'bin/python')
subprocess.run(uv + ['pip', 'sync', '--python', python, '--index-url', args.index, str(lock)], check=True)
subprocess.run([python, '-m', 'pip', 'check'], check=True)
subprocess.run([python, '-m', 'driveserve', 'gpu-smoke'], cwd=root, check=True)
subprocess.run([python, '-c', 'import torch,vllm,transformers; print(torch.__version__,torch.version.cuda,vllm.__version__,transformers.__version__)'], check=True)
print('Fresh GPU environment rebuilt and smoke-tested; actual migration was not performed.')
