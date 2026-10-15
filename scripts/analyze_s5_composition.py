"""Reaggregate completed S5 model-composition runs and retain output differences."""
import argparse,hashlib,json,statistics,subprocess,sys
from collections import defaultdict
from pathlib import Path
sys.path.insert(0,str(Path.cwd()))
from driveserve.evidence import file_hash,verify_assets,atomic_json
from driveserve.benchmark import percentile
p=argparse.ArgumentParser();p.add_argument('--states',type=Path,nargs='+',required=True);p.add_argument('--report',type=Path,required=True);a=p.parse_args()
records=[];raw={};states=[];seen=set();fingerprints={}
def fingerprint(sha):
 if sha not in fingerprints:
  paths=subprocess.check_output(['git','ls-tree','-r','--name-only',sha,'driveserve','patches','scripts/benchmark_speculation.py'],text=True).splitlines();h=hashlib.sha256()
  for path in paths:h.update(path.encode()+b'\0');h.update(subprocess.check_output(['git','show',sha+':'+path]))
  fingerprints[sha]=h.hexdigest()
 return fingerprints[sha]
for path in a.states:
 state=json.load(open(path));assert state['status']=='completed' and state['stage']=='S5'
 plan=json.load(open(state['plan']));assert file_hash(state['plan'])==state['plan_sha256']
 states.append(dict(path=str(path),sha256=file_hash(path),code_sha=state['code_sha']))
 for task in plan['tasks']:
  complete=[x for x in state['attempts'] if x['label']==task['label'] and x['status']=='completed'];assert len(complete)==1
  attempt=complete[0];wm=json.load(open(attempt['wrapper_manifest']));verify_assets(Path.cwd(),wm)
  assert wm['status']=='completed' and wm['code']['sha']==state['code_sha'] and not wm['code']['dirty']
  for ip in attempt['inner_manifests']:
   folder=Path(ip).parent;m=json.load(open(ip));verify_assets(Path.cwd(),m)
   assert m['status']=='completed' and m['code']['sha']==state['code_sha'] and not m['code']['dirty']
   if m['kind']!='vllm-speculation':continue
   assert m['run_id'] not in seen;seen.add(m['run_id']);cfg=m['config'];work=json.load(open(folder/'workload.json'));results=json.load(open(folder/'results.json'))
   assert len(work)==len(results)==m['result']['requests']==len({r['request_id'] for r in results})
   assert file_hash(folder/'workload.json')==m['result']['workload_sha256']
   quality=[r for r in results if r['quality'] is not None]
   assert len(quality)==cfg['data']['selected']==m['result']['quality_total']
   correct=sum(r['quality']['exact_match'] for r in quality);assert correct==m['result']['quality_correct']
   resolved=json.load(open(folder/'resolved-model-config.json'));assert resolved['draft_quantization'] is None
   waves=json.load(open(folder/'waves.json'));total_s=sum(w['elapsed_ns'] for w in waves)/1e9
   ttft=[];tpot=[]
   for r in results:
    content=[o for o in r['observations'] if o['tokens']>0]
    assert content and r['status']=='completed'
    ttft.append(content[0]['elapsed_ns']/1e9)
    n=len(r['output_token_ids'])
    if n>1:tpot.append((content[-1]['elapsed_ns']-content[0]['elapsed_ns'])/1e9/(n-1))
   raw[m['run_id']]={r['request_id']:r for r in results}
   comparable={k:v for k,v in cfg.items() if k not in ['repeat','initial_gpu_usage']}
   env=json.load(open(folder/'environment.json'))
   records.append(dict(execution_source_fingerprint=fingerprint(m['code']['sha']),
     comparison_config_sha256=hashlib.sha256(json.dumps(comparable,sort_keys=True).encode()).hexdigest(),
     environment={k:env[k] for k in ['gpu','packages']},label=task['label'],run_id=m['run_id'],source_sha=m['code']['sha'],repeat=cfg['repeat'],purpose=cfg['purpose'],
     mode=cfg['mode'],policy=cfg.get('policy'),quantization=cfg['quantization'],prefix_cache=cfg['prefix_caching'],temperature=cfg['temperature'],
     data=cfg['data'],quality_only=cfg['quality_only'],wave_size=cfg.get('wave_size',4),workload_sha256=file_hash(folder/'workload.json'),
     target_provenance_sha256=__import__('hashlib').sha256(json.dumps(cfg['model']['target'],sort_keys=True).encode()).hexdigest(),
     resolved_model_config=resolved,requests=len(results),quality_correct=correct,quality_total=len(quality),
     json_valid=sum(r['quality']['json_valid'] for r in quality),sum_wave_s=total_s,output_tokens=sum(len(r['output_token_ids']) for r in results),
     ttft_mean_s=sum(ttft)/len(ttft),ttft_p99_s=percentile(ttft,.99),tpot_mean_s=sum(tpot)/len(tpot),
     cached_tokens=sum(r.get('num_cached_tokens',0) for r in results),
     controller=json.load(open(folder/'controller-summary.json')) if (folder/'controller-summary.json').exists() else None))
comparisons=[]
for row in records:
 if row['mode']=='target' and row['policy'] in [None,'native']:continue
 candidates=[r for r in records if r['mode']=='target' and r['policy'] in [None,'native'] and
   all(r[k]==row[k] for k in ['repeat','target_provenance_sha256','workload_sha256','prefix_cache','temperature','wave_size'])]
 if not candidates:continue
 reference=candidates[0];left=raw[reference['run_id']];right=raw[row['run_id']];assert left.keys()==right.keys()
 different=[rid for rid,r in right.items() if r['output_token_ids']!=left[rid]['output_token_ids'] or r['finish_reason']!=left[rid]['finish_reason']]
 comparisons.append(dict(baseline_run=reference['run_id'],candidate_run=row['run_id'],label=row['label'],total=len(right),
    same_tokens_and_finish=len(right)-len(different),different_ids=different,
    quality_correct_difference=row['quality_correct']-reference['quality_correct'],
    elapsed_reduction=1-row['sum_wave_s']/reference['sum_wave_s'],
    timing_eligible=row['purpose']==reference['purpose']=='timing',
    limitation='Random sampling sequences need not be token-identical; all comparison timing requires independent matched repeats.'))
grouped=defaultdict(list)
for row in records:
 if row['purpose']=='timing':
  name='/'.join([row['quantization'] or 'fp16',row['mode'],row['policy'] or 'no-policy','apc'+str(row['prefix_cache'])])
  grouped[name].append(row)
summary={}
for name,rows in grouped.items():
 assert len({r['repeat'] for r in rows})==len(rows)
 assert len({r['execution_source_fingerprint'] for r in rows})==1
 assert len({r['comparison_config_sha256'] for r in rows})==1
 assert len({r['workload_sha256'] for r in rows})==1 and all(r['environment']==rows[0]['environment'] for r in rows)
 metrics={}
 for k in ['quality_correct','json_valid','sum_wave_s','output_tokens','ttft_mean_s','ttft_p99_s','tpot_mean_s','cached_tokens']:
  vals=[r[k] for r in rows];metrics[k]=dict(values=vals,mean=statistics.mean(vals),sample_stdev=statistics.stdev(vals) if len(vals)>1 else None)
 summary[name]=dict(independent_processes=len(rows),run_ids=[r['run_id'] for r in rows],metrics=metrics)
atomic_json(a.report,dict(aggregator_sha256=file_hash(__file__),states=states,records=records,comparisons=comparisons,run_level_statistics=summary,
 limits=['Only completed state plans enter this report; failed/interrupted attempts remain in source state and manifests.',
 'Quantized speculative outputs compare to the same quantized Target, not an FP16 distribution claim.',
 'Development timings and finite greedy equality are not stable speedups or universal sampling proofs.',
 'No real driving safety, physical24GB or cross-template generalization conclusion.']))
print(json.dumps(dict(runs=len(records),comparisons=len(comparisons))))
