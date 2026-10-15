"""Relocate hash-locked local wheel references; never alter the source lock."""
import argparse
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import urlsplit, unquote


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def relocate(lock, wheelhouse):
    paths = {}
    if wheelhouse is not None:
        if not wheelhouse.is_dir():
            raise ValueError('wheelhouse is not an existing directory')
        for path in wheelhouse.rglob('*.whl'):
            paths.setdefault(path.name, []).append(path.resolve())
    lines, verified = [], []
    for line in lock.read_text().splitlines():
        match = re.fullmatch(r'([^@]+?)\s*@\s*(file://\S+)', line)
        if match is None:
            if 'file:' in line:
                raise ValueError('unsupported local requirement syntax')
            lines.append(line)
            continue
        name, url = match.groups()
        parsed = urlsplit(url)
        if parsed.netloc not in ['', 'localhost'] or parsed.query:
            raise ValueError('unsupported file URL')
        hash_match = re.fullmatch(r'sha256=([0-9a-f]{64})', parsed.fragment)
        if hash_match is None:
            raise ValueError('every local wheel needs its original SHA256')
        original = Path(unquote(parsed.path))
        if original.suffix != '.whl':
            raise ValueError('local dependency is not a wheel')
        if wheelhouse is None:
            candidates = [original]
        else:
            candidates = paths.get(original.name, [])
        if len(candidates) != 1:
            raise ValueError(f'expected one wheel named {original.name}; found {len(candidates)}')
        candidate = candidates[0]
        if not candidate.is_file():
            raise ValueError(f'missing wheel {candidate}; restore the OSS wheelhouse first')
        expected = hash_match.group(1)
        if digest(candidate) != expected:
            raise ValueError(f'wheel hash mismatch: {candidate.name}')
        lines.append(f'{name.strip()} @ {candidate.resolve().as_uri()}#sha256={expected}')
        verified.append(dict(package=name.strip(),wheel=candidate.name,bytes=candidate.stat().st_size,sha256=expected))
    return '\n'.join(lines)+'\n', verified


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--lock', type=Path, required=True)
    parser.add_argument('--wheelhouse', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or args.report.exists():
        raise ValueError('use new output/report paths; existing files are never overwritten')
    content, wheels = relocate(args.lock, args.wheelhouse)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open('x') as stream: stream.write(content)
    args.report.parent.mkdir(parents=True,exist_ok=True)
    with args.report.open('x') as stream:
        json.dump(dict(source=str(args.lock),source_sha256=digest(args.lock),output=str(args.output),
                       output_sha256=digest(args.output),verified_wheels=wheels,
                       note='Only local paths relocated; versions and wheel hashes unchanged. Other pinned dependencies still require an index.'),stream,indent=2)
        stream.write('\n')
    print(json.dumps(dict(verified_wheels=len(wheels),output=str(args.output))))

if __name__ == '__main__': main()
