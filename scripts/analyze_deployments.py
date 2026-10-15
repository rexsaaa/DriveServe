"""Reaggregate matched deployments from every raw attempted request."""
import argparse,json,math,sys
from pathlib import Path
sys.path.insert(0,str(Path.cwd()))
from driveserve.evidence import atomic_json,verify_assets,file_hash
from driveserve.benchmark import aggregate
from driveserve.task import score
p=argparse.ArgumentParser();p.add_argument('--runs',nargs='+',type=Path,required=True);p.add_argument('--report',type=Path,required=True);args=p.parse_args()
results=[];hashes=set();raw_cells={}
for path in args.runs:
 m=json.load(open(path/'manifest.json'));assert m['status']=='completed';verify_assets(Path.cwd(),m)
 work=json.load(open(path/'workloads.json'));hashes.add(file_hash(path/'workloads.json'))
 for length in [512,1536]:
  by_id={r['request_id']:r for r in work[str(length)]}
  for concurrency in [1,8]:
   name=f'p{length}-c{concurrency}';rows=[json.loads(l) for l in (path/(name+'-requests.jsonl')).read_text().splitlines()]
   assert len(rows)==len({r['request_id'] for r in rows})==64
   for r in rows:
    w=by_id[r['request_id']];assert r['quality']==score(w['scene'],r['text'])
    assert r['prompt_sha256']==w['prompt_sha256']
   raw_cells[(m['config']['deployment'],length,concurrency)]={r['request_id']:r for r in rows}
   saved=json.load(open(path/(name+'-summary.json')));elapsed=(saved['finished_ns']-saved['started_ns'])/1e9
   recomputed=aggregate(rows,elapsed)
   for k,v in recomputed.items():assert v==saved[k],(name,k,v,saved[k])
   results.append({'run_id':m['run_id'],'sha':m['code']['sha'],'deployment':m['config']['deployment'],'prompt_length':length,
     'concurrency':concurrency,'summary':recomputed,'per_replica':saved['per_replica'],
     'gpu_count':2 if m['config']['deployment']!='single' else 1,
     'output_tokens_per_gpu_s':recomputed['output_token_per_s']/(2 if m['config']['deployment']!='single' else 1)})
assert len(hashes)==1
comparisons=[];output_comparisons=[]
for length in [512,1536]:
 for concurrency in [1,8]:
  cells={r['deployment']:r for r in results if r['prompt_length']==length and r['concurrency']==concurrency}
  if all(k in cells for k in ['single','replica','tp2']):
   baseline=raw_cells[('single',length,concurrency)]
   for candidate in ['replica','tp2']:
    differences=[]
    for rid,a in baseline.items():
     b=raw_cells[(candidate,length,concurrency)][rid]
     if a['text']!=b['text']:
      differences.append({'request_id':rid,'baseline_text':a['text'],'candidate_text':b['text'],
       'baseline_quality':a['quality'],'candidate_quality':b['quality']})
    output_comparisons.append({'length':length,'concurrency':concurrency,'baseline':'single','candidate':candidate,
      'same_text':len(baseline)-len(differences),'total':len(baseline),'differences':differences})
   replica,tp=[cells[k]['summary'] for k in ['replica','tp2']]
   comparisons.append({'length':length,'concurrency':concurrency,'replica_to_tp2_output_throughput_ratio':replica['output_token_per_s']/tp['output_token_per_s'],
      'replica_to_tp2_p50_ttft_ratio':replica['ttft_s']['p50']/tp['ttft_s']['p50'],
      'observed_fastest_two_gpu':max(['replica','tp2'],key=lambda k:cells[k]['summary']['output_token_per_s'])})
atomic_json(args.report,{'cells':results,'matched_comparisons':comparisons,'output_comparisons':output_comparisons,'workload_sha256':next(iter(hashes)),
 'limits':['64 attempts/cell; nearest-rank P99 is exploratory, not a stable SLO','closed-loop concurrency, not controlled arrival rate',
 'Graph native V0 fixed budgets; no prefix caching; no assertion this configuration is globally optimal',
 'compare replica/TP2 at same two-GPU budget, single as one-GPU efficiency reference','one run per deployment; independent repeats at S3']})
print(json.dumps({'cells':len(results),'requests':sum(r['summary']['requests'] for r in results),'matched_comparisons':comparisons},indent=2))
