"""Build a fresh CPU environment, optionally including all HTTP protocol fixtures."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
from relocate_lock import relocate, digest

parser = argparse.ArgumentParser()
parser.add_argument('--env', type=Path, default=Path('.venv-cpu'))
parser.add_argument('--proxy', default=None)
parser.add_argument('--index', default='https://pypi.org/simple')
parser.add_argument('--http-tests', action='store_true', help='install the pinned HTTP subset for all protocol fixtures')
parser.add_argument('--wheelhouse', type=Path, help='restored wheel tree for the hash-locked aiohttp wheel')
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
env_path = args.env.resolve()
if env_path.exists():
    raise SystemExit('destination already exists; choose a fresh CPU environment')
if args.http_tests:
    source_lock = root / 'requirements/cpu-http.txt'
    content, wheels = relocate(source_lock, args.wheelhouse)
subprocess.run([sys.executable, '-m', 'venv', '--without-pip', str(env_path)], check=True)
python = str(env_path / 'bin/python')
install = [sys.executable, '-m', 'pip', '--python', python, 'install', '--no-cache-dir',
           '--index-url', args.index, '-r', str(root / 'requirements/cpu-build.txt')]
if args.http_tests:
    lock = env_path / 'http-relocated.lock.txt'
    lock.write_text(content)
    (env_path / 'wheel-verification.json').write_text(json.dumps(dict(source_sha256=digest(source_lock),
        resolved_lock_sha256=digest(lock),verified_wheels=wheels),indent=2)+'\n')
    install.extend(['-r', str(lock)])
if args.proxy:
    install.extend(['--proxy', args.proxy])
subprocess.run(install, check=True)
subprocess.run([python, '-m', 'pip', 'install', '--no-build-isolation', '--no-deps', '-e', str(root)], check=True)
subprocess.run([python, '-m', 'pip', 'check'], check=True)
if args.http_tests:
    subprocess.run([python, '-c', 'import aiohttp; assert aiohttp.__version__ == "3.14.5"'], check=True)
subprocess.run([python, '-m', 'unittest', 'discover', '-s', str(root / 'tests'), '-v'], cwd=root, check=True)
print(f'CPU environment ready: {python}; HTTP subset installed: {args.http_tests}; GPU dependencies are separate.')
