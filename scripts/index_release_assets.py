"""Generate the final asset index from versioned full-readback receipts and locks."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from driveserve.evidence import atomic_json,file_hash

p=argparse.ArgumentParser()
p.add_argument('--output',type=Path,required=True)
a=p.parse_args()
contract=json.load(open('configs/s5-asset-receipts.json'))
entries=[];objects={}
for name in contract['receipts']:
    receipt=json.load(open(name))
    if 'plan' in receipt:
        assert receipt['status']=='completed'
        items=receipt['plan']['items'];assert set(receipt['verified'])=={x['object'] for x in items}
        for item in items:
            proof=receipt['verified'][item['object']]
            assert proof['content_sha256']==item['sha256'] and proof['content_bytes']==item['bytes']
            assert proof['archive_bytes']==item['archive_bytes']
            assert item['object'] not in objects
            objects[item['object']]=dict(bytes=proof['archive_bytes'],sha256=proof['archive_sha256'])
        entries.append(dict(receipt=name,receipt_sha256=file_hash(name),prefix=receipt['plan']['destination'],
            objects=len(items),archive_bytes=sum(x['archive_bytes'] for x in items),
            members=[dict(name=x['name'],bytes=x['bytes'],sha256=x['sha256'],object=x['object']) for x in items]))
    else:
        assert receipt['verified_at'] and receipt['object'] not in objects
        objects[receipt['object']]=dict(bytes=receipt['bytes'],sha256=receipt['sha256'])
        entries.append(dict(receipt=name,receipt_sha256=file_hash(name),objects=1,archive_bytes=receipt['bytes'],
            object=receipt['object'],archive_sha256=receipt['sha256'],type='environment snapshot; absolute-path/host dependencies remain'))
total=sum(x['bytes'] for x in objects.values())
assert len(objects)==contract['expected_objects'] and total==contract['expected_archive_bytes']
locks=['configs/models.json','configs/upstream.json','requirements/gpu.lock.txt','requirements/cpu-build.txt',
       'requirements/cpu-http.txt','requirements/tools.txt','requirements/training-layer.json','requirements/awq-layer.json',
       'patches/vllm-v0.8.5-observers.json','patches/vllm-v0.8.5-policies.json','patches/vllm-v0.8.5-spec.json',
       'data/frozen-v1/manifest.json','configs/final-profiles.json','configs/s5-final-quality.json']
data=[]
for split in ['train','calibration','dev','test']:
    path=Path('data/frozen-v1')/(split+'.jsonl')
    rows=[json.loads(x) for x in path.read_text().splitlines()]
    assert all(x['split']==split for x in rows)
    data.append(dict(split=split,path=str(path),records=len(rows),groups=len({x['scene']['group_id'] for x in rows}),sha256=file_hash(path)))
atomic_json(a.output,dict(generator_sha256=file_hash(__file__),objects=len(objects),archive_bytes=total,
    estimated_CNY_per_day=total/1e9*.0004*24,receipts=entries,
    definitions=[dict(path=x,sha256=file_hash(x)) for x in locks],data=data,
    limits=['This is a deterministic inventory of saved full-readback receipts; current small probes are reports/s5-assets.json.',
            'OSS access requires the project account; no credential is stored in this repository.',
            '36 base local wheels are archived; other pinned index dependencies still require a package index.',
            'Environment snapshot excludes host Python, driver and CUDA toolkit; rebuild overlays/extensions after migration.',
            'No physical 24GB or host migration was performed.']))
print(json.dumps(dict(objects=len(objects),archive_bytes=total,data_records=sum(x['records'] for x in data))))
