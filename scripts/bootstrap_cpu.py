"""Build an isolated CPU environment, including on hosts lacking ensurepip."""

import argparse
from pathlib import Path
import subprocess
import sys

parser = argparse.ArgumentParser()
parser.add_argument("--env", type=Path, default=Path(".venv-cpu"))
parser.add_argument("--proxy", default=None)
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
env_path = args.env.resolve()
subprocess.run([sys.executable, "-m", "venv", "--without-pip", str(env_path)], check=True)
python = str(env_path / "bin/python")
install = [sys.executable, "-m", "pip", "--python", python, "install", "--no-cache-dir",
           "--index-url", "https://pypi.org/simple", "-r", str(root / "requirements/cpu-build.txt")]
if args.proxy:
    install.extend(["--proxy", args.proxy])
subprocess.run(install, check=True)
subprocess.run([python, "-m", "pip", "install", "--no-build-isolation", "--no-deps", "-e", str(root)], check=True)
subprocess.run([python, "-m", "unittest", "discover", "-s", str(root / "tests"), "-v"], cwd=root, check=True)
print(f"CPU environment ready: {python}; GPU dependencies are separate and not installed.")
