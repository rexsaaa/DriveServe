"""Restore selected frozen models into the image's expected mount layout."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
MODELS = {
    'target': ('s1-oss-models-receipt.json', 'target'),
    'draft': ('s1-oss-models-receipt.json', 'draft'),
    'draft-aligned-v1': ('s1-oss-models-receipt.json', 'draft_aligned'),
    'awq-smoke': ('s1-oss-models-receipt.json', 'awq_smoke'),
    'draft-distilled-v2': ('s2-trained-assets-oss.json', 'assets/distilled'),
    'awq-domain-g128-v1': ('s2-awq-g128-oss.json', 'assets/domain-g128'),
    'awq-general-g128-v1': ('s2-awq-g128-oss.json', 'assets/general-g128'),
    'awq-domain-g64-v1': ('s2-awq-g64-oss.json', 'assets/domain-g64'),
}


def file_hash(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for b in iter(lambda: stream.read(8 * 1024**2), b''):
            h.update(b)
    return h.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, required=True, help='New host storage root; models/ will be mounted into the container')
    parser.add_argument('--models', nargs='+', choices=sorted(MODELS), default=['target'])
    args = parser.parse_args()
    base = args.directory.resolve()
    (base / 'models').mkdir(parents=True, exist_ok=True)
    for model in dict.fromkeys(args.models):
        receipt_name, prefix = MODELS[model]
        receipt_path = ROOT / 'reports' / receipt_name
        receipt = json.loads(receipt_path.read_text())
        items = [x for x in receipt['plan']['items'] if x['name'].startswith(prefix + '/')]
        if not items:
            raise ValueError('Receipt has no model files')
        destination = base / 'models' / model
        if destination.is_symlink():
            raise ValueError('Refusing a symlink model destination')
        if not destination.exists():
            staging = base / 'restore-staging' / model
            report = base / 'restore-reports' / (model + '.json')
            command = [sys.executable, str(ROOT / 'scripts/restore_models_oss.py'), '--receipt', str(receipt_path),
                       '--destination', str(staging), '--report', str(report)]
            for item in items:
                command += ['--include', item['name']]
            subprocess.run(command, check=True)
            # Same-filesystem rename avoids keeping another copy of the weights.
            (staging / prefix).rename(destination)
        for item in items:
            path = destination / Path(item['name']).relative_to(prefix)
            if path.is_symlink() or path.stat().st_size != item['bytes'] or file_hash(path) != item['sha256']:
                raise ValueError('Restored model differs: ' + str(path))
        print(json.dumps(dict(model=model, files=len(items), status='verified', directory=str(destination))), flush=True)


if __name__ == '__main__':
    main()
