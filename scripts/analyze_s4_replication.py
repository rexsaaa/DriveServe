"""S4 engine, complete CPU-policy operation, and CUDA ablation reaggregation."""
import argparse,hashlib,json,statistics,subprocess,sys
from collections import defaultdict
from pathlib import Path
sys.path.insert(0,str(Path.cwd()))
from driveserve.evidence import atomic_json,file_hash,verify_assets
from scripts.analyze_policies import analyze
p=argparse.ArgumentParser();p.add_argument('--states',nargs='+',type=Path,required=True);p.add_argument('--report',type=Path,required=True);a=p.parse_args()
root=Path.cwd();records=[];seen=set();states=[];fingerprints={};policy_outputs={}
def fingerprint(sha,script):
 key=sha,script
 if key not in fingerprints:
  paths=subprocess.check_output(['git','ls-tree','-r','--name-only',sha,'driveserve','csrc','patches',script],text=True).splitlines();h=hashlib.sha256()
  for path in paths:h.update(path.encode()+b'\0');h.update(subprocess.check_output(['git','show',sha+':'+path]))
  fingerprints[key]=h.hexdigest()
 return fingerprints[key]
def stats(v):return {'independent_runs':len(v),'values':v,'mean':statistics.mean(v),'sample_stdev':statistics.stdev(v) if len(v)>1 else None,'min':min(v),'max':max(v)}
for sp in a.states:
 state=json.load(open(sp));assert state['status']=='completed' and state['stage']=='S4'
 plan=json.load(open(state['plan']));assert file_hash(state['plan'])==state['plan_sha256'];repeat=plan['repeat'];states.append({'path':str(sp),'sha256':file_hash(sp),'source_sha':state['code_sha']})
 for task in plan['tasks']:
  completed=[x for x in state['attempts'] if x['label']==task['label'] and x['status']=='completed'];assert len(completed)==1
  x=completed[0];wm=json.load(open(x['wrapper_manifest']));verify_assets(root,wm);assert wm['status']=='completed' and wm['result']['returncode']==0
  assert len(x['inner_manifests'])==1;ip=Path(x['inner_manifests'][0]);m=json.load(open(ip));verify_assets(root,m);folder=ip.parent;cfg=m['config']
  assert m['status']=='completed' and m['stage']=='S4' and not m['code']['dirty'] and not wm['code']['dirty']
  assert m['code']['sha']==wm['code']['sha']==state['code_sha'] and cfg['repeat']==repeat
  assert m['run_id'] not in seen;seen.add(m['run_id'])
  env=json.load(open(folder/'environment.json'));label=task['label'].split('-',2)[2]
  comparable={k:v for k,v in cfg.items() if k!='repeat'}
  base={'label':label,'repeat':repeat,'run_id':m['run_id'],'code_sha':m['code']['sha'],'source_fingerprint':fingerprint(m['code']['sha'],task['argv'][1]),'comparison_config_sha256':hashlib.sha256(json.dumps(comparable,sort_keys=True).encode()).hexdigest(),'environment':{k:env[k] for k in ['gpu','packages']}}
  if m['kind']=='vllm-policy-core':
   d,_=analyze(folder.resolve(),root);assert not cfg['trace'] and not cfg['eager'] and cfg['max_num_seqs']==4
   assert d['groups']['all']['completed']==36 and d['groups']['all']['failed']==0
   metrics={k:d['groups']['all'][k] for k in ['elapsed_s','output_tokens_per_s','completed','failed']}
   for group in ['short','long']:
    for k in ['wait_ms','ttft_ms','e2e_ms']:metrics[group+'_'+k+'_mean']=d['groups'][group][k]['mean']
   metrics['hot_probe_cached_tokens']=d['groups']['hot_probe']['cached_tokens_sum'];metrics['selection_ns_final_scenario']=d['final_pool'].get('selection_ns',0)
   records.append({**base,'kind':'policy','implementation':cfg['cache_implementation'],'workload_sha256':d['workload_sha256'],'metrics':metrics,'details':d})
   policy_outputs[(repeat,label)]={r['request_id']:r for r in json.load(open(folder/'results.json'))}
  elif m['kind']=='heap-policy-comparison':
   diff=json.load(open(folder/'differential.json'));assert diff['steps']==20000 and diff['same_metadata_and_victims']
   bound=json.load(open(folder/'bounded-index.json'));assert bound['updates']==5000 and bound['empty_eviction_rejected']
   data=json.load(open(folder/'maintenance.json'));assert len(data)==8
   for cell in data:
    raw=cell['raw'];assert len(raw)==256 and all(x['all_ns']==x['evict_ns']+x['other_operations_ns'] for x in raw)
    assert cell['median_all_ns']==statistics.median(x['all_ns'] for x in raw) and cell['sum_all_ns']==sum(x['all_ns'] for x in raw)
    metrics={k:cell[k] for k in ['median_all_ns','sum_all_ns','p99_all_ns','max_all_ns','resident_traced_bytes','initialization_peak_traced_bytes','initialization_ns_with_tracemalloc']}
    metrics['median_evict_ns']=statistics.median(x['evict_ns'] for x in raw);metrics['median_other_ns']=statistics.median(x['other_operations_ns'] for x in raw)
    records.append({**base,'kind':'cpu-policy','label':f"heap-cpu-{cell['capacity']}-{cell['variant']}",'metrics':metrics})
  elif m['kind']=='rope-cache-depth-validation':
   assert not cfg['sanitizer'] and cfg['benchmark'] and m['result']['correctness_cases']==275
   data=json.load(open(folder/'timings.json'));assert len(data)==6
   for cell in data:
    assert cell['calls_per_graph']==100 and cell['samples_per_variant']==20 and len(cell['raw'])==100
    medians={v:statistics.median(x['microseconds_per_call'] for x in cell['raw'] if x['variant']==v) for v in cell['median_us']};assert medians==cell['median_us']
    assert set(medians)=={'upstream_separate','project_v1','tiled_scalar','tiled_half2','dispatch'}
    records.append({**base,'kind':'cuda','label':'rope-depth-tokens'+str(cell['tokens']),'metrics':medians})
  else:raise ValueError(m['kind'])
grouped=defaultdict(list)
for r in records:grouped[r['label']].append(r)
summary={}
for label,rows in grouped.items():
 assert len({r['repeat'] for r in rows})==len(rows)==len(states)
 assert len({r['source_fingerprint'] for r in rows})==1 and len({r['comparison_config_sha256'] for r in rows})==1
 assert all(r['environment']==rows[0]['environment'] for r in rows)
 if 'workload_sha256' in rows[0]:assert len({r['workload_sha256'] for r in rows})==1
 summary[label]={'runs':[r['run_id'] for r in rows],'metrics':{k:stats([r['metrics'][k] for r in rows]) for k in rows[0]['metrics']}}
comparisons=[];paired=[]
for (repeat,label),rows in policy_outputs.items():
 reference=policy_outputs[(repeat,'policy-native')];assert rows.keys()==reference.keys()
 differences=[rid for rid,v in rows.items() if v['status']!=reference[rid]['status'] or v.get('output_token_ids')!=reference[rid].get('output_token_ids')]
 comparisons.append({'repeat':repeat,'label':label,'total':len(rows),'same_tokens_and_status':len(rows)-len(differences),'different_ids':differences})
for repeat in sorted({r['repeat'] for r in records}):
 cur={r['label']:r for r in records if r['repeat']==repeat}
 for suffix in ['cache','both']:
  baseline=cur[f'policy-{suffix}-scan'];candidate=cur[f'policy-{suffix}-heap'];assert baseline['workload_sha256']==candidate['workload_sha256']
  left=policy_outputs[(repeat,baseline['label'])];right=policy_outputs[(repeat,candidate['label'])]
  same_reuse=all(v['num_cached_tokens']==right[k]['num_cached_tokens'] for k,v in left.items())
  before=baseline['metrics']['elapsed_s'];after=candidate['metrics']['elapsed_s']
  paired.append({'repeat':repeat,'candidate':candidate['label'],'baseline':baseline['label'],'same_cached_tokens_each_request':same_reuse,'elapsed_reduction':1-after/before,'throughput_gain':before/after-1})
atomic_json(a.report,{'aggregator_sha256':file_hash(Path(__file__)),'state_evidence':states,'independent_inner_runs':len(seen),'records':records,'run_level_statistics':summary,'policy_output_comparisons':comparisons,'paired_policy_comparisons':paired,'limits':['Three runs on one environment, not a population performance guarantee.','CPU median and P99 are descriptive within 256 correlated operation bundles; independent units are process repeats.','CPU timing includes evict, add, reuse, touch, remove and re-add; initialization is separately measured under tracemalloc.','Tracemalloc is Python allocation, not full process RSS; heap memory and compaction costs are retained.','CUDA Event times exclude Python validation/dispatch and do not measure serving TPOT.','All policy requests are synthetic barriers; no HTTP/quality/SLO or final-test conclusion.','Fixed candidate auto cutoff32 is not claimed globally optimal; all ablations retained including regressions.']})
print(json.dumps({'independent_runs':len(seen),'metric_groups':len(summary),'rounds':len(states)}))
