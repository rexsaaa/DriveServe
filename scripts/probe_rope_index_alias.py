"""Diagnose checked-wrapper index alias acceptance without launching a bad kernel."""
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import sys
sys.path.insert(0,str(Path.cwd()))
from driveserve.evidence import Run,atomic_json
run=Run(Path.cwd(),'rope-index-alias-probe',{'stage':'S3','requirement_ids':['M5-03'],
 'hypothesis':'index tensors can alias writable storage despite passing range checks',
 'method':'real CUDA storage views; intercept extension dispatch before any kernel call',
 'limits':['a boundary-validation diagnostic, not evidence of actual out-of-bounds execution or model corruption']},formal=True)
print(run.path,flush=True)
try:
 import torch
 import driveserve.rope_cache as operator
 rows=[]
 for index_name,index in [('positions',1),('slots',4)]:
  for target_name,target in [('projection',0),('cache',3)]:
   args=[torch.zeros(2,36,128,device='cuda',dtype=torch.float16),
         torch.tensor([0,31],device='cuda'),torch.ones(32,128,device='cuda',dtype=torch.float16),
         torch.zeros(2,2,16,4,128,device='cuda',dtype=torch.float16),torch.tensor([0,31],device='cuda')]
   args[index]=args[target].view(-1).view(torch.int64)[:2]
   args[index].copy_(torch.tensor([0,31],device='cuda'))
   dispatched=[]
   sentinel=SimpleNamespace(fused=lambda *a:dispatched.append(True))
   before=[x.clone() for x in args]
   error=None
   with patch.object(operator,'extension',return_value=sentinel):
    try:operator.fused(*args)
    except ValueError as exc:error=str(exc)
   torch.cuda.synchronize()
   for actual,expected in zip(args,before):torch.testing.assert_close(actual,expected,atol=0,rtol=0)
   rows.append({'case':index_name+'_'+target_name,'dispatch_reached':bool(dispatched),'rejected':error is not None,'error':error,'storage_unmodified':True})
 atomic_json(run.path/'alias-probe.json',rows)
 run.finish('completed',{'cases':4,'dispatch_reached':sum(r['dispatch_reached'] for r in rows),'rejected':sum(r['rejected'] for r in rows),
  'limitations':['extension intercepted; no unsafe kernel issued, no speed measurement']})
except BaseException as exc:run.finish('failed',{'error':str(exc)});raise
