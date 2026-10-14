"""Actual native CUDA rejection sampler versus a known target categorical law."""
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from driveserve.evidence import Run,atomic_json
from driveserve.spec_control import accepted_prefix
import torch
from vllm.model_executor.layers.rejection_sampler import RejectionSampler
root=Path(__file__).resolve().parents[1]
run=Run(root,'rejection-distribution',{'stage':'S2','requirement_ids':['M3-03'],
 'hypothesis':'unchanged native rejection sampling with varying K preserves the known one-step target law',
 'model':'not applicable: categorical probabilities, actual CUDA sampler',
 'seed':71,'samples_per_k':30000,'k_values':[1,2,3,4],
 'target_probs':[.05,.15,.30,.50],'draft_probs':[.50,.25,.15,.10],
 'criterion':'max absolute first-output frequency error < 0.015 per K; no multiple-testing significance claim',
 'limitations':['controlled independent categorical law, not a proof for every model distribution',
   'real model random outputs separately smoke tested; no identical-seed equality requirement']},formal=True)
print(run.path,flush=True)
try:
 torch.manual_seed(71);torch.cuda.manual_seed_all(71)
 target=torch.tensor([.05,.15,.30,.50],device='cuda');draft=torch.tensor([.50,.25,.15,.10],device='cuda')
 results=[]
 for k in [1,2,3,4]:
  b=30000
  sampler=RejectionSampler(strict_mode=True,use_flashinfer=False);sampler.init_tensors('cuda')
  proposed=torch.multinomial(draft.expand(b*k,-1),1).reshape(b,k)
  bonus=torch.multinomial(target.expand(b,-1),1)
  out=sampler(target.expand(b,k+1,-1).contiguous(),bonus,draft.expand(b,k,-1).contiguous(),proposed)
  counts=torch.bincount(out[:,0],minlength=4).cpu();freq=counts.double()/b
  error=(freq-target.cpu().double()).abs().max().item()
  rows=out.cpu().tolist();accepted=sum(accepted_prefix(row,k) for row in rows)
  assert error<.015
  results.append({'k':k,'samples':b,'counts':counts.tolist(),'max_abs_frequency_error':error,
   'continuous_accepted':accepted,'proposed':b*k,'upstream_noncausal_accepted':sampler.num_accepted_tokens.item()})
 atomic_json(run.path/'distribution.json',results)
 run.finish('completed',{'total_samples':120000,'all_frequency_checks_passed':True})
except BaseException as exc:run.finish('failed',{'error':str(exc)});raise
