"""Audit saved training/calibration provenance without opening final-test inputs."""
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path.cwd()))
from driveserve.evidence import Run,atomic_json,file_hash,verify_assets
from driveserve.task import audit_dataset,score

root=Path.cwd()
run=Run(root,'data-isolation-audit',{'stage':'S3','requirement_ids':['M3-04','M3-05','M4-02'],
 'hypothesis':'retained teacher rows, optimizer batches and calibration sources respect the frozen data purposes',
 'scope':'read train/calibration/dev and manifests only; final-test contents not opened',
 'limitations':['exact group/content isolation does not establish unseen-template or real-road generalization',
 'this audit checks retained records and source contracts, not arbitrary unrecorded activity']},formal=True)
print(run.path,flush=True)
try:
 manifest_path=Path('data/frozen-v1/manifest.json');manifest=json.load(open(manifest_path))
 selected={};files=[]
 for split in ['train','calibration','dev']:
  entry=manifest['files'][split];path=Path(entry['path']);assert file_hash(path)==entry['sha256']
  rows=[json.loads(line) for line in path.read_text().splitlines()];assert len(rows)==entry['records']
  assert all(row['split']==split for row in rows)
  selected[split]={r['scene']['scene_id']:r for r in rows};assert len(selected[split])==len(rows)
  files.append({'path':str(path),'sha256':file_hash(path)})
 audit=audit_dataset([r for by_id in selected.values() for r in by_id.values()])
 teacher_path=Path('artifacts/teacher/proxy-v1-frozen/state.json');teacher=json.load(open(teacher_path))
 assert len(teacher['records'])==640==teacher['next_index']
 assert len({r['scene_id'] for r in teacher['records']})==640
 eligible=set();teacher_counts={'train':0,'dev':0}
 for row in teacher['records']:
  assert row['split'] in ['train','dev'];source=selected[row['split']][row['scene_id']]
  assert row['quality']==score(source['scene'],row['completion_text'])
  expected=row['split']=='train' and not row['filter_reasons']
  assert row['train_eligible']==expected
  if expected:eligible.add(row['scene_id'])
  teacher_counts[row['split']]+=1
 assert len(eligible)==472
 training=[]
 for path in sorted(Path('experiments/runs').glob('*/steps.jsonl')):
  m=json.load(open(path.parent/'manifest.json'))
  if m['kind']!='draft-distillation':continue
  verify_assets(root,m)
  assert m['config']['data']['teacher_sha256']==file_hash(teacher_path)
  steps=[json.loads(line) for line in path.read_text().splitlines()]
  for row in steps:assert len(row['sample_ids'])==8 and set(row['sample_ids']).issubset(eligible)
  training.append({'run_id':m['run_id'],'status':m['status'],'steps':len(steps),
                   'sample_occurrences':sum(len(row['sample_ids']) for row in steps),'steps_sha256':file_hash(path)})
 assert len(training)==4
 awq_path=Path('data/manifests/awq-calibration-v1.json');awq=json.load(open(awq_path))
 assert awq['domain_manifest_sha256']==file_hash(manifest_path)
 used=awq['files']['domain']['source_rows_including_last_partially_used']
 assert set(used).issubset(selected['calibration'])
 for entry in awq['files'].values():assert file_hash(entry['path'])==entry['sha256']
 result={'frozen_manifest_sha256':file_hash(manifest_path),'read_split_audit':audit,'files':files,
  'teacher':{'sha256':file_hash(teacher_path),'counts':teacher_counts,'eligible_train':len(eligible)},
  'training_logs':training,'awq':{'manifest_sha256':file_hash(awq_path),'domain_source_scenes':len(used),'source_split':'calibration','tokens_each':16384},
  'final_test':{'opened_by_this_audit':False,'frozen_manifest_entry':manifest['files']['test'],
                'isolation_basis':'S2 full freeze audit plus no final-test inputs in retained teacher, optimizer batches or domain calibration IDs'}}
 atomic_json(run.path/'isolation.json',result);run.finish('completed',result)
except BaseException as exc:run.finish('failed',{'error':str(exc)});raise
