"""Sequential, resumable experiment orchestration; never resumes partial timing.

The state records process identity and completed wrappers. This is a foreground
runner, not a machine/service supervisor or an automatic agent wakeup facility.
"""
import argparse
import fcntl
import json
import os
import re
from pathlib import Path
import signal
import subprocess
import sys

sys.path.insert(0, str(Path.cwd()))
from driveserve.evidence import atomic_json, file_hash, git_state, now, process_alive, process_identity, verify_assets

p=argparse.ArgumentParser()
p.add_argument('--plan',type=Path,required=True)
p.add_argument('--state',type=Path,required=True)
p.add_argument('--retry-failed',action='store_true')
args=p.parse_args()
root=Path.cwd();plan=json.loads(args.plan.read_text());plan_hash=file_hash(args.plan)
assert plan['stage'] in ['S3','S4','S5']
assert plan['tasks'] and len({t['label'] for t in plan['tasks']})==len(plan['tasks'])
code=git_state(root);assert code['sha'] and not code['dirty'],'clean committed source required'
args.state.parent.mkdir(parents=True,exist_ok=True)
lock=args.state.with_suffix('.lock').open('a')
fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
if args.state.exists():
 state=json.loads(args.state.read_text());assert state['plan_sha256']==plan_hash
 assert state['code_sha']==code['sha'],'changed source requires a new plan state, retaining prior runs'
 for record in state['attempts']:
  if record['status']=='running':
   assert not process_alive(record.get('wrapper_process')),'prior wrapper is still running; take over instead of duplicating'
   record.update(status='interrupted',observed_at=now())
else:
 state={'created_at':now(),'plan':str(args.plan),'plan_sha256':plan_hash,'code_sha':code['sha'],
        'stage':plan['stage'],'attempts':[],'status':'running'}
def gpu_state():
 return {'captured_at':now(),'query':subprocess.check_output(['nvidia-smi','--query-gpu=index,uuid,memory.used,utilization.gpu,temperature.gpu,power.draw,power.limit,clocks.current.sm,clocks.current.memory','--format=csv'],text=True)}
child=None
def interrupted(*_):
 raise KeyboardInterrupt('SIGTERM')
signal.signal(signal.SIGTERM,interrupted)
def save():
 state['updated_at']=now();state['runner_process']=process_identity();atomic_json(args.state,state)
save()
try:
 for task in plan['tasks']:
  previous=[a for a in state['attempts'] if a['label']==task['label']]
  complete=[a for a in previous if a['status']=='completed']
  if complete:
   manifest=json.load(open(complete[-1]['wrapper_manifest']))
   assert manifest['status']=='completed';verify_assets(root,manifest)
   for mpath in complete[-1]['inner_manifests']:
    m=json.load(open(mpath));assert m['status']=='completed';verify_assets(root,m)
   print('Already verified '+task['label'],flush=True);continue
  if previous and not args.retry_failed:raise RuntimeError('prior failed/interrupted task needs explicit --retry-failed after inspection')
  if task.get('exclusive',True):
   usage=subprocess.check_output(['nvidia-smi','--query-gpu=index,memory.used,utilization.gpu','--format=csv,noheader,nounits'],text=True)
   assert all(int(line.split(',')[1])<100 for line in usage.strip().splitlines()),'GPU still occupied'
   for pth in (root/'experiments/runs').glob('*/manifest.json'):
    m=json.loads(pth.read_text())
    assert not (m['status']=='running' and process_alive(m.get('process'))),'another experiment/backup is active: '+m['run_id']
  else:usage='diagnostic task: no exclusive timing assertion'
  assert git_state(root)==code,'source changed while plan was running'
  command=[sys.executable,'scripts/record_command.py','--stage',plan['stage'],'--kind',task['label'],'--formal','--']+task['argv']
  env={**os.environ,**task.get('env',{})}
  record={'label':task['label'],'argv':command,'started_at':now(),'status':'running',
          'gpu_before':usage,'gpu_state_before':gpu_state(),'wrapper_process':None,'inner_manifests':[]}
  state['attempts'].append(record);save()
  child=subprocess.Popen(command,env=env,start_new_session=True)
  record['wrapper_process']=process_identity(child.pid);save()
  while True:
   try:ret=child.wait(timeout=30);break
   except subprocess.TimeoutExpired:save()
  wrappers=[]
  for mpath in (root/'experiments/runs').glob('*/manifest.json'):
   m=json.loads(mpath.read_text())
   if m.get('process')==record['wrapper_process']:wrappers.append((mpath,m))
   # process state may change between captures, identity is PID/boot/start ticks only.
   elif m.get('process') and all(m['process'].get(k)==record['wrapper_process'].get(k) for k in ['pid','boot_id','start_ticks']):wrappers.append((mpath,m))
  assert len(wrappers)==1,'wrapper manifest not uniquely identified'
  mpath,m=wrappers[0];record['wrapper_manifest']=str(mpath.relative_to(root));verify_assets(root,m)
  for ipath in (root/'experiments/runs').glob('*/manifest.json'):
   inner=json.loads(ipath.read_text());identity=inner.get('process')
   if identity and all(identity.get(k)==m.get('child_process',{}).get(k) for k in ['pid','boot_id','start_ticks']):
    record['inner_manifests'].append(str(ipath.relative_to(root)));verify_assets(root,inner)
  if task.get('inner_kind') and not record['inner_manifests']:
   # Sanitizers can insert an intermediate process. Keep direct process
   # matching as the primary source; recover an explicitly expected inner
   # run from the immutable wrapper log when the child identity differs.
   log=(mpath.parent/'command.log').read_text()
   ids=re.findall(r'(?m)^/[^\n]*experiments/runs/(\d{8}T\d{6}\+\d{4}-[0-9a-f]{10})$',log)
   for rid in dict.fromkeys(ids):
    ipath=root/'experiments/runs'/rid/'manifest.json';inner=json.load(open(ipath))
    if inner['kind']!=task['inner_kind']:continue
    assert inner['stage']==plan['stage'] and inner['code']['sha']==code['sha'] and not inner['code']['dirty']
    assert inner['started_at']>=m['started_at'] and inner['finished_at']<=m['finished_at']
    verify_assets(root,inner);record['inner_manifests'].append(str(ipath.relative_to(root)))
   record['inner_discovery']='expected kind in verified wrapper log'
  if task.get('inner_kind') and ret==0:
   assert len(record['inner_manifests'])==1,'expected inner manifest absent or ambiguous'
   inner=json.load(open(record['inner_manifests'][0]));assert inner['kind']==task['inner_kind'] and inner['status']=='completed'
  record.update(gpu_state_after=gpu_state(),returncode=ret,finished_at=now(),status='completed' if ret==0 and m['status']=='completed' else 'failed');child=None;save()
  if record['status']!='completed':raise RuntimeError('failed task retained: '+task['label'])
  print('Plan completed '+task['label'],flush=True)
 state['status']='completed';save()
except BaseException as exc:
 if child is not None and child.poll() is None:
  os.killpg(child.pid,signal.SIGTERM)
  try:child.wait(timeout=30)
  except subprocess.TimeoutExpired:os.killpg(child.pid,signal.SIGKILL);child.wait()
 state.update(status='interrupted' if isinstance(exc,KeyboardInterrupt) else 'failed',error=str(exc));save()
 raise
