"""Record a subprocess independently of a chat session; argv must contain no secrets."""

import argparse
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from driveserve.evidence import Run, process_identity, now

parser = argparse.ArgumentParser()
parser.add_argument("--kind", required=True)
parser.add_argument("--formal", action="store_true")
parser.add_argument("--stage", choices=("S1", "S2", "S3", "S4", "S5", "S6"), default="S1")
parser.add_argument("argv", nargs=argparse.REMAINDER)
args = parser.parse_args()
command = args.argv[1:] if args.argv and args.argv[0] == "--" else args.argv
if not command:
    parser.error("a command is required")
root = Path(__file__).resolve().parents[1]
run = Run(root, args.kind, {"argv": command, "stage": args.stage}, formal=args.formal)
print(run.path, flush=True)
child = None
def stop_group(pgid):
    def active():
        for process in Path("/proc").iterdir():
            if not process.name.isdigit():
                continue
            try:
                stat = (process / "stat").read_text()
                fields = stat[stat.rfind(")") + 2:].split()
                if int(fields[2]) == pgid and fields[0] != "Z":
                    return True
            except (OSError, ValueError, IndexError):
                continue
        return False
    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(pgid, sig)
        except ProcessLookupError:
            return
        deadline = time.monotonic() + 5
        while active() and time.monotonic() < deadline:
            time.sleep(.05)
        if not active():
            return
    raise RuntimeError("command process group still active; do not trust a finalized log")

def interrupted(signum, frame):
    raise KeyboardInterrupt(f"signal {signum}")
signal.signal(signal.SIGTERM, interrupted)
try:
    with (run.path / "command.log").open("w", buffering=1) as stream:
        child = subprocess.Popen(command, cwd=root, stdout=stream, stderr=subprocess.STDOUT, start_new_session=True)
        run.manifest["child_process"] = process_identity(child.pid)
        run.manifest["child_process_group"] = child.pid
        run.save()
        while True:
            try:
                code = child.wait(timeout=30)
                break
            except subprocess.TimeoutExpired:
                run.manifest["heartbeat_at"] = now()
                run.save()
        # The command may have spawned a grandchild; do not finalize a log while it can still write.
        stop_group(child.pid)
    run.finish("completed" if code == 0 else "failed", {"returncode": code})
except BaseException as exc:
    if child is not None:
        stop_group(child.pid)
        child.wait(timeout=10)
    run.finish("interrupted", {"error": str(exc)})
    raise
print(f"{run.manifest['run_id']}: {run.manifest['status']}", flush=True)
sys.exit(code)
