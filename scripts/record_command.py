"""Record a subprocess independently of a chat session; argv must contain no secrets."""

import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from driveserve.evidence import Run, process_identity, now

parser = argparse.ArgumentParser()
parser.add_argument("--kind", required=True)
parser.add_argument("--formal", action="store_true")
parser.add_argument("argv", nargs=argparse.REMAINDER)
args = parser.parse_args()
command = args.argv[1:] if args.argv and args.argv[0] == "--" else args.argv
if not command:
    parser.error("a command is required")
root = Path(__file__).resolve().parents[1]
run = Run(root, args.kind, {"argv": command}, formal=args.formal)
print(run.path, flush=True)
try:
    with (run.path / "command.log").open("w", buffering=1) as stream:
        child = subprocess.Popen(command, cwd=root, stdout=stream, stderr=subprocess.STDOUT)
        run.manifest["child_process"] = process_identity(child.pid)
        run.save()
        while True:
            try:
                code = child.wait(timeout=30)
                break
            except subprocess.TimeoutExpired:
                run.manifest["heartbeat_at"] = now()
                run.save()
    run.finish("completed" if code == 0 else "failed", {"returncode": code})
except BaseException as exc:
    # An interruption is not evidence that the child exited; recovery must inspect child_process.
    run.finish("interrupted", {"error": str(exc)})
    raise
print(f"{run.manifest['run_id']}: {run.manifest['status']}", flush=True)
sys.exit(code)
