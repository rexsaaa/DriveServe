"""Actual SIGTERM/resume against uninterrupted training under one fixed schedule."""
import argparse,json,os,signal,subprocess,sys,time
from pathlib import Path
sys.path.insert(0,str(Path.cwd()))
from driveserve.evidence import Run,atomic_json,process_identity,now
p=argparse.ArgumentParser();p.add_argument('--teacher',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--gpu',default='0');args=p.parse_args()
if args.output.exists():raise ValueError('choose a fresh recovery-drill root')
args.output.mkdir(parents=True)
run=Run(Path.cwd(),'training-recovery-drill',{'stage':'S2','requirement_ids':['M3-04'],
 'hypothesis':'SIGTERM after at least eight completed steps resumes full state to same step16 as uninterrupted reference',
 'schedule_steps':128,'reference_prefix':16,'signal_after_at_least_step':8,'gpu':args.gpu,
 'output':str(args.output),'teacher':str(args.teacher),
 'limitations':['planned SIGTERM at optimizer-step boundary; does not simulate host loss mid-checkpoint write']},formal=True)
print(run.path,flush=True);child=None
try:
 base=[sys.executable,'scripts/train_draft.py','--teacher',str(args.teacher),'--gpu',args.gpu,'--steps','128','--stop-after','16']
 for phase in ['reference','interrupt','resume']:
  folder=args.output/('reference' if phase=='reference' else 'resumed')
  cmd=base+['--output',str(folder)]
  with (run.path/(phase+'.log')).open('w',buffering=1) as log:
   child=subprocess.Popen(cmd,stdout=log,stderr=subprocess.STDOUT)
   run.manifest['phase']=phase;run.manifest['child_process']=process_identity(child.pid);run.save()
   deadline=time.monotonic()+900;sent=False
   while child.poll() is None:
    if time.monotonic()>deadline:raise TimeoutError('training drill phase exceeded 900 seconds')
    if phase=='interrupt' and not sent and (folder/'latest.json').exists():
     latest=json.load(open(folder/'latest.json'))
     if latest['step']>=8:
      identity=process_identity(child.pid);os.kill(child.pid,signal.SIGTERM);sent=True
      atomic_json(run.path/'signal.json',{'at':now(),'signal':'SIGTERM','process':identity,'checkpoint_before_signal':latest})
    run.manifest['heartbeat_at']=now();run.save();time.sleep(1)
   code=child.wait();child=None
  assert code==(75 if phase=='interrupt' else 0),(phase,code)
  if phase=='interrupt':assert sent
 comparison=run.path/'state-comparison.json'
 subprocess.run([sys.executable,'scripts/compare_training_states.py','--reference',str(args.output/'reference'),
   '--resumed',str(args.output/'resumed'),'--output',str(comparison)],check=True)
 report=json.load(open(comparison));run.finish('completed',{'bitwise_training_state_equal':report['all_equal'],'step':report['step'],
 'resume_root':str(args.output/'resumed'),'reference_root':str(args.output/'reference')})
except BaseException as exc:
 if child is not None and child.poll() is None:
  child.terminate()
  try:child.wait(timeout=30)
  except subprocess.TimeoutExpired:child.kill();child.wait()
 run.finish('failed',{'error':str(exc)});raise
