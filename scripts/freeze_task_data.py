"""Freeze independent scene groups for distillation, calibration, dev and final test."""
import argparse,json,subprocess
from collections import Counter
from pathlib import Path
import sys
sys.path.insert(0,str(Path.cwd()))
from driveserve.task import generate,audit_dataset,canonical,digest,messages
from driveserve.evidence import atomic_json,file_hash,now

p=argparse.ArgumentParser();p.add_argument('--destination',type=Path,required=True);args=p.parse_args()
seed=2026101501
# Distinct generated groups and independent scene contents; one shared task contract.
all_rows=generate(seed=seed,groups_per_split=128,variants=4)
counts={'train':512,'calibration':256,'dev':128,'test':256}
selected=[]
for split,n in counts.items():selected.extend([r for r in all_rows if r['split']==split][:n])
audit=audit_dataset(selected)
old=[json.loads(line) for line in Path('data/samples/proxy-v1.jsonl').read_text().splitlines()]
def content(row):return digest({k:v for k,v in row['scene'].items() if k not in ('scene_id','group_id')})
assert not set(map(content,old)) & set(map(content,selected))
if args.destination.exists():raise ValueError('immutable data destination already exists')
args.destination.mkdir(parents=True)
files={}
for split,n in counts.items():
 rows=[r for r in selected if r['split']==split]
 path=args.destination/(split+'.jsonl')
 path.write_text(''.join(canonical(row)+'\n' for row in rows))
 files[split]={'path':str(path),'sha256':file_hash(path),'records':len(rows),'groups':len({r['scene']['group_id'] for r in rows}),
  'label_counts':dict(Counter(row['label']['action'] for row in rows)),
  'prompt_sha256':digest([messages(row['scene']) for row in rows])}
manifest={'version':'proxy-v1-frozen-20261015','created_at':now(),'code_sha':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
 'seed':seed,'generator':'driveserve.task.generate; 128 groups/split then fixed prefix counts','counts':counts,
 'audit':audit,'files':files,'fixture_overlap':0,
 'source':'self-generated structured proxy scenes, independent rule oracle, no teacher labels',
 'license':'project-authored synthetic records, no external dataset content',
 'frozen_final_test':True,'final_test_usage':'S5 final quality evaluation; never training/calibration/hyperparameter selection',
 'purpose':{'train':'teacher sequence distillation only','calibration':'domain AWQ calibration only','dev':'quality/acceptance and training validation; no gradient updates','test':'independent final quality at S5'},
 'limitations':['synthetic proxy rules, no real-road validity','same task/system schema across splits; does not prove unseen-template or unseen-domain generalization',
               'groups and exact scene contents isolated; continuous features can still be close by chance']}
atomic_json(args.destination/'manifest.json',manifest)
print(json.dumps(manifest,ensure_ascii=False,indent=2))
