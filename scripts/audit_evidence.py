"""Check local immutable evidence, Git inclusion, and saved OSS readback receipts.

This audit verifies recorded facts, not semantic stage acceptance or a new cloud
download. Restore probes and stage-specific analysis remain separate evidence.
"""
import argparse
import json
from pathlib import Path
import re
import subprocess
import sys

sys.path.insert(0, str(Path.cwd()))
from driveserve.evidence import atomic_json, file_hash, git_state, now, process_alive, verify_assets

p = argparse.ArgumentParser()
p.add_argument('--through-stage', choices=[f'S{i}' for i in range(1, 7)], required=True)
p.add_argument('--receipt', action='append', type=Path, default=[])
p.add_argument('--document', action='append', type=Path, default=[])
p.add_argument('--require-tracked', action='store_true')
p.add_argument('--report', type=Path, required=True)
args = p.parse_args()
root = Path.cwd()
tracked = set(subprocess.check_output(['git', 'ls-files', '-z'], text=True).split('\0'))
runs, active, errors, receipts, links = [], [], [], [], []
objects = {}

def check_tracked(path):
    relative = str(path.resolve().relative_to(root))
    if args.require_tracked and relative not in tracked:
        raise ValueError(f'not in Git index: {relative}')

for path in sorted((root / 'experiments/runs').glob('*/manifest.json')):
    m = json.loads(path.read_text())
    if int(m['stage'][1:]) > int(args.through_stage[1:]):
        continue
    try:
        if m['status'] == 'running':
            active.append({'run_id': m['run_id'], 'alive': process_alive(m.get('process'))})
            raise ValueError('unfinished run must be resolved before stage evidence audit')
        count = verify_assets(root, m)
        assert m['environment_id'] == file_hash(path.parent / 'environment.json')
        if m['mode'] == 'formal':
            assert not m['code']['dirty']
        sha = m['code']['sha']
        if sha:
            subprocess.run(['git', 'cat-file', '-e', sha + '^{commit}'], check=True,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        check_tracked(path)
        for item in m['assets']:
            check_tracked(root / item['path'])
        runs.append({'run_id': m['run_id'], 'stage': m['stage'], 'status': m['status'],
                     'sha': sha, 'assets': count, 'manifest_sha256': file_hash(path)})
    except Exception as exc:
        errors.append({'path': str(path.relative_to(root)), 'error': str(exc)})

for path in args.receipt:
    try:
        check_tracked(path)
        d = json.loads(path.read_text())
        if 'plan' in d:
            assert d['status'] == 'completed'
            items = d['plan']['items']
            assert {i['object'] for i in items} == set(d['verified'])
            assert sum(i['archive_bytes'] for i in items) == d['plan']['planned_archive_bytes']
            for item in items:
                v = d['verified'][item['object']]
                assert v['content_sha256'] == item['sha256']
                assert v['content_bytes'] == item['bytes']
                assert v['archive_bytes'] == item['archive_bytes'] and v['verified_at']
                value = {'bytes': v['archive_bytes'], 'sha256': v['archive_sha256']}
                assert item['object'] not in objects or objects[item['object']] == value
                objects[item['object']] = value
        else:
            assert d['object'].startswith('oss://') and d['verified_at']
            objects[d['object']] = {'bytes': d['bytes'], 'sha256': d['sha256']}
        receipts.append({'path': str(path), 'sha256': file_hash(path)})
    except Exception as exc:
        errors.append({'path': str(path), 'error': str(exc)})

for path in args.document:
    try:
        check_tracked(path)
        for target in re.findall(r'\]\(([^)]+)\)', path.read_text()):
            if '://' in target or target.startswith('#'):
                continue
            target = target.split('#')[0]
            actual = (path.parent / target).resolve()
            assert actual.exists(), f'broken link: {target}'
            if actual.is_file():
                check_tracked(actual)
            links.append({'document': str(path), 'target': target})
    except Exception as exc:
        errors.append({'path': str(path), 'error': str(exc)})

total = sum(v['bytes'] for v in objects.values())
result = {'captured_at': now(), 'code': git_state(root), 'through_stage': args.through_stage,
          'status': 'passed' if not errors else 'failed', 'runs': runs, 'active': active,
          'receipts': receipts, 'verified_links': links, 'errors': errors,
          'storage': {'objects': len(objects), 'archive_bytes': total,
                      'estimated_CNY_per_day': total / 1e9 * .0004 * 24},
          'limits': ['Local hash and Git-index verification; not a new remote download.',
                     'Saved full readback receipts checked; cloud restore probes are separate runs.',
                     'Stage acceptance requires workload/quality/coverage/material review as well.']}
atomic_json(args.report, result)
print(json.dumps({'status': result['status'], 'runs': len(runs), 'errors': errors,
                  'storage': result['storage']}, ensure_ascii=False))
sys.exit(bool(errors))
