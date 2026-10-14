"""Exercise native and patched seeded categorical sampler on actual CUDA tensors."""
import argparse, importlib.util, json, sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0,str(Path.cwd()))
from driveserve.evidence import Run, atomic_json, file_hash
p=argparse.ArgumentParser(); p.add_argument('--overlay',type=Path,required=True);args=p.parse_args()
import torch
from vllm.model_executor.layers import sampler as native
lock=json.load(open(args.overlay/'overlay-manifest.json'))
changed=next(f for f in lock['lock']['files'] if f['path'].endswith('/sampler.py'))
assert file_hash(Path(native.__file__))==changed['upstream_sha256']
fixed_path=args.overlay/changed['path'];assert file_hash(fixed_path)==changed['patched_sha256']
spec=importlib.util.spec_from_file_location('driveserve_checked_sampler',fixed_path)
fixed=importlib.util.module_from_spec(spec);spec.loader.exec_module(fixed)
run=Run(Path.cwd(),'seeded-mqa-sampler',{'stage':'S2','requirement_ids':['M3-01','M3-03'],
 'hypothesis':'native seeded sampler initializes one row per seq_id but MQA emits query-length rows; corrected sample_indices covers all',
 'model':'not applicable; actual native CUDA categorical sampling', 'overlay':lock,
 'law':[.05,.15,.3,.5], 'criterion':'all fixed random rows finite; max frequency error < .025 over 10000 rows; seeded repeat identical',
 'limitations':['NaN sentinel replaces allocator garbage to prove incomplete writes, not a production output distribution',
 'bounded synthetic sampler test; real target-model inference checked separately']},formal=True)
print(run.path,flush=True)
try:
 rows=[]
 for name,module in [('native',native),('fixed',fixed)]:
  for lengths,num_samples in [([1,1,1,1],1),([5,5,5,5],1),([1,5,3,0],1),([1,5,3],2)]:
   total=sum(lengths);captured=[]
   groups=[SimpleNamespace(seq_ids=[i],sample_indices=list(range(n)),generator=torch.Generator(device='cuda').manual_seed(81+i)) for i,n in enumerate(lengths)]
   probs=torch.tensor([.05,.15,.3,.5],device='cuda').expand(total,-1).clone()
   def sentinel(tensor,*a,**kw):
    q=torch.full_like(tensor,float('nan'));captured.append(q);return q
   with patch.object(torch,'empty_like',side_effect=sentinel):
    module._multinomial(probs,num_samples,groups)
   q=captured[0];finite=torch.isfinite(q).all(-1)
   row={'variant':name,'query_lengths':lengths,'num_samples':num_samples,'rows':len(q),'initialized_rows':int(finite.sum()),'uninitialized_rows':int((~finite).sum())}
   if name=='fixed':assert row['uninitialized_rows']==0
   if name=='native' and lengths==[5,5,5,5]:assert row['uninitialized_rows']==16
   rows.append(row)
 samples=[]
 for repeat in range(2):
  groups=[SimpleNamespace(seq_ids=[i],sample_indices=list(range(5)),generator=torch.Generator(device='cuda').manual_seed(7001+i)) for i in range(2000)]
  probs=torch.tensor([.05,.15,.3,.5],device='cuda').expand(10000,-1).clone()
  samples.append(fixed._multinomial(probs,1,groups))
 assert torch.equal(*samples)
 counts=torch.bincount(samples[0].flatten(),minlength=4).cpu()
 error=max(abs(a/10000-b) for a,b in zip(counts.tolist(),[.05,.15,.3,.5]))
 assert error<.025
 report={'coverage':rows,'fixed_known_law':{'samples':10000,'counts':counts.tolist(),'max_abs_frequency_error':error,'seeded_repeat_equal':True}}
 atomic_json(run.path/'seeded-sampler.json',report);run.finish('completed',report)
except BaseException as exc:run.finish('failed',{'error':str(exc)});raise
