"""Reaggregate completed S3 plan rounds, preserving the independent run unit."""
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import statistics
import subprocess
import sys

sys.path.insert(0,str(Path.cwd()))
from driveserve.evidence import atomic_json,file_hash,verify_assets
from driveserve.benchmark import aggregate
from driveserve.task import score

p=argparse.ArgumentParser();p.add_argument('--states',nargs='+',type=Path,required=True)
p.add_argument('--report',type=Path,required=True);args=p.parse_args();root=Path.cwd()
records=[];seen=set();source_cache={};inference_raw={};policy_raw={};deployment_raw={}
state_evidence=[]

def source_fingerprint(sha,script):
 key=(sha,script)
 if key not in source_cache:
  paths=subprocess.check_output(['git','ls-tree','-r','--name-only',sha,'driveserve','csrc','patches',script],text=True).splitlines()
  h=hashlib.sha256()
  for path in paths:
   h.update(path.encode()+b'\0');h.update(subprocess.check_output(['git','show',sha+':'+path]))
  source_cache[key]=h.hexdigest()
 return source_cache[key]

def stats(values):
 return {'independent_runs':len(values),'values':values,'mean':statistics.mean(values),
         'sample_stdev':statistics.stdev(values) if len(values)>1 else None,'min':min(values),'max':max(values)}

for state_path in args.states:
 state=json.load(open(state_path));assert state['status']=='completed'
 state_evidence.append({'path':str(state_path),'sha256':file_hash(state_path),'code_sha':state['code_sha']})
 plan=json.load(open(state['plan']));assert file_hash(state['plan'])==state['plan_sha256']
 for task in plan['tasks']:
  attempts=[a for a in state['attempts'] if a['label']==task['label'] and a['status']=='completed'];assert len(attempts)==1
  a=attempts[0];wm=json.load(open(a['wrapper_manifest']));assert wm['status']=='completed';verify_assets(root,wm)
  assert len(a['inner_manifests'])==1,task['label']
  path=Path(a['inner_manifests'][0]);m=json.load(open(path));assert m['status']=='completed' and not m['code']['dirty'];verify_assets(root,m)
  assert m['run_id'] not in seen;seen.add(m['run_id']);folder=path.parent.resolve();cfg=m['config']
  assert cfg['repeat']==plan['repeat'] and m['stage']=='S3'
  assert m['code']['sha']==wm['code']['sha']==state['code_sha']
  comparable_config={k:v for k,v in cfg.items() if k not in ['repeat','initial_gpu_usage','fault_checks']}
  label=task['label'].split('-',2)[2]
  base={'label':label,'repeat':plan['repeat'],'run_id':m['run_id'],'code_sha':m['code']['sha'],
        'source_fingerprint':source_fingerprint(m['code']['sha'],task['argv'][1]),
        'environment_id':m['environment_id'],'metrics':{},
        'comparison_config_sha256':hashlib.sha256(json.dumps(comparable_config,sort_keys=True).encode()).hexdigest()}
  env=json.load(open(folder/'environment.json'));base['hardware_software']={k:env[k] for k in ['gpu','packages']}
  if m['kind']=='vllm-speculation':
   rows=json.load(open(folder/'results.json'));work={x['request_id']:x for x in json.load(open(folder/'workload.json'))}
   assert len(rows)==len(work)==137 and len({x['request_id'] for x in rows})==137
   assert all(r['status']=='completed' and 0<len(r['output_token_ids'])<=work[r['request_id']]['max_tokens'] for r in rows)
   assert cfg['purpose']=='timing' and not cfg['trace'] and not cfg['eager'] and not cfg['logprobs']
   checks=json.load(open(folder/'exclusive-gpu-check.json'));assert checks['before_engine'] and checks['after_warmup']
   q=[r for r in rows if work[r['request_id']]['kind']=='quality'];assert len(q)==128
   for r in q:assert r['quality']==score(work[r['request_id']]['scene'],r['text'])
   elapsed=sum(w['elapsed_ns'] for w in json.load(open(folder/'waves.json')))/1e9
   output_tokens=sum(len(r['output_token_ids']) for r in rows)
   ttft=[next(o['elapsed_ns'] for o in r['observations'] if o['tokens'])/1e6 for r in q]
   tpot=[(r['elapsed_ns']-next(o['elapsed_ns'] for o in r['observations'] if o['tokens']))/1e6/(len(r['output_token_ids'])-1) for r in q if len(r['output_token_ids'])>1]
   memory=json.load(open(folder/'memory-final.json'));assert memory['actual_gpu_blocks']==512
   base.update(kind='inference',workload_sha256=file_hash(folder/'workload.json'),quantization=cfg['quantization'],mode=cfg['mode'])
   base['metrics']={'elapsed_s':elapsed,'request_per_s':len(rows)/elapsed,'output_token_per_s':output_tokens/elapsed,
      'completed':len(rows),'failed':0,'output_tokens':output_tokens,'quality_correct':sum(r['quality']['exact_match'] for r in q),
      'json_valid':sum(r['quality']['json_valid'] for r in q),'quality_mean_ttft_ms':statistics.mean(ttft),
      'quality_mean_observed_tpot_ms':statistics.mean(tpot),'torch_allocated_bytes':memory['torch_allocated_bytes'],
      'torch_reserved_bytes':memory['torch_reserved_bytes'],'torch_peak_allocated_bytes':memory['torch_peak_allocated_bytes']}
   if (folder/'controller-summary.json').exists():
    c=json.load(open(folder/'controller-summary.json'));assert 0<=c['accepted_draft_prefix']<=c['proposed']
    base['controller']=c;base['metrics']['acceptance_rate']=c['accepted_draft_prefix']/c['proposed']
   inference_raw[(plan['repeat'],label)]={r['request_id']:r for r in rows}
   records.append(base)
  elif m['kind']=='vllm-policy-core':
   from scripts.analyze_policies import analyze
   data, _ = analyze(folder,root)
   base.update(kind='policy',trace=cfg['trace'],variant=cfg['variant'],reaggregated=data,workload_sha256=data['workload_sha256'])
   base['metrics']={k:data['groups']['all'][k] for k in ['elapsed_s','output_tokens_per_s','completed','failed']}
   for group in ['short','long','hot_probe']:
    for key in ['wait_ms','ttft_ms','e2e_ms']:base['metrics'][group+'_'+key+'_mean']=data['groups'][group][key]['mean']
   base['metrics']['hot_probe_cached_tokens']=data['groups']['hot_probe']['cached_tokens_sum']
   base['metrics']['evictor_selection_ns_final_scenario']=data['final_pool'].get('selection_ns',0)
   if cfg['trace']:base['metrics']['trace_order_total_ns']=sum(x['host_order_ns'] for f in (folder/'engine-trace').glob('*.jsonl') for x in map(json.loads,f.read_text().splitlines()) if x['event']=='policy.admission_order')
   # Keep the analyzer's complete per-group/maintenance observations verbatim.
   records.append(base);policy_raw[(plan['repeat'],label)]=json.load(open(folder/'results.json'))
  elif m['kind']=='deployment-matrix':
   assert cfg['purpose']=='timing';work=json.load(open(folder/'workloads.json'))
   for length in [512,1536]:
    by_id={r['request_id']:r for r in work[str(length)]}
    for concurrency in [1,8]:
     name=f'p{length}-c{concurrency}';rows=[json.loads(l) for l in (folder/(name+'-requests.jsonl')).read_text().splitlines()]
     assert len(rows)==len({r['request_id'] for r in rows})==64
     for r in rows:
      assert r['prompt_sha256']==by_id[r['request_id']]['prompt_sha256']
      assert r['quality']==score(by_id[r['request_id']]['scene'],r['text'])
     saved=json.load(open(folder/(name+'-summary.json')));re=aggregate(rows,(saved['finished_ns']-saved['started_ns'])/1e9)
     for k,v in re.items():assert saved[k]==v
     row={**base,'label':label+'-'+name,'kind':'deployment','prompt_length':length,'concurrency':concurrency,
          'workload_sha256':file_hash(folder/'workloads.json'),'summary':re,'metrics':{
          'request_per_s':re['request_per_s'],'output_token_per_s':re['output_token_per_s'],
          'per_gpu_output_token_per_s':re['output_token_per_s']/(1 if cfg['deployment']=='single' else 2),
          'success':re['success'],'failed':re['failed'],'timeout':re['timeout'],'quality_correct':round(re['exact_match_rate']*64)}}
     for metric in ['ttft_s','e2e_s','tpot_s']:
      for q in ['p50','p99']:row['metrics'][metric+'_'+q]=re[metric][q]
     records.append(row);deployment_raw[(plan['repeat'],cfg['deployment'],length,concurrency)]={r['request_id']:r for r in rows}
  elif m['kind']=='rope-cache-cuda-validation':
   assert m['result']['correctness_cases']==48
   timing=json.load(open(folder/'timings.json'));assert len(timing)==6
   for cell in timing:
    medians={v:statistics.median(r['microseconds_per_call'] for r in cell['raw'] if r['variant']==v) for v in cell['median_us']}
    assert medians==cell['median_us']
    records.append({**base,'kind':'rope','label':label+'-tokens'+str(cell['tokens']),'metrics':medians})
  elif m['kind']=='fa2-prefill-comparison':
   cells=json.load(open(folder/'results.json'));assert len(cells)==8
   for cell in cells:
    medians={v:statistics.median(r['us'] for r in cell['raw'] if r['variant']==v) for v in cell['median_us']};assert medians==cell['median_us']
    records.append({**base,'kind':'fa2','label':label+f"-b{cell['batch']}-l{cell['length']}",'metrics':medians})
  else:raise ValueError(m['kind'])

grouped=defaultdict(list)
for r in records:grouped[r['label']].append(r)
summary={}
for label,rows in grouped.items():
 assert len({r['repeat'] for r in rows})==len(rows)
 assert len({r['source_fingerprint'] for r in rows})==1,(label,'execution sources changed across repeats')
 assert len({r['comparison_config_sha256'] for r in rows})==1,(label,'measurement configuration changed')
 if 'workload_sha256' in rows[0]:assert len({r['workload_sha256'] for r in rows})==1,(label,'workload changed')
 assert all(r['hardware_software']==rows[0]['hardware_software'] for r in rows),(label,'environment changed')
 keys=set.intersection(*(set(r['metrics']) for r in rows))
 summary[label]={'runs':[r['run_id'] for r in rows],'metrics':{k:stats([r['metrics'][k] for r in rows]) for k in sorted(keys)}}
inference_comparisons=[]
for (repeat,label),rows in inference_raw.items():
 baseline=inference_raw[(repeat,'spec-target')];differences=[rid for rid,r in rows.items() if r['output_token_ids']!=baseline[rid]['output_token_ids']]
 inference_comparisons.append({'repeat':repeat,'label':label,'identical_to_fp16':137-len(differences),'total':137,'different_ids':differences})
policy_comparisons=[];observer_overhead=[]
for (repeat,label),rows in policy_raw.items():
 baseline={r['request_id']:r for r in policy_raw[(repeat,'policy-native')]}
 diffs=[r['request_id'] for r in rows if r['output_token_ids']!=baseline[r['request_id']]['output_token_ids'] or r['status']!=baseline[r['request_id']]['status']]
 policy_comparisons.append({'repeat':repeat,'label':label,'same_tokens_and_status':len(rows)-len(diffs),'total':len(rows),'different_ids':diffs})
for repeat in sorted({r['repeat'] for r in records}):
 off=next(r for r in records if r['repeat']==repeat and r['label']=='policy-native')['metrics']['elapsed_s']
 on=next(r for r in records if r['repeat']==repeat and r['label']=='policy-native-trace')['metrics']['elapsed_s']
 observer_overhead.append({'repeat':repeat,'off_s':off,'on_s':on,'relative_observed_difference':on/off-1})
deployment_comparisons=[]
for (repeat,deployment,length,concurrency),rows in deployment_raw.items():
 baseline=deployment_raw[(repeat,'single',length,concurrency)]
 differences=[{'request_id':rid,'baseline_text':baseline[rid]['text'],'candidate_text':r['text'],
               'baseline_quality':baseline[rid]['quality'],'candidate_quality':r['quality']} for rid,r in rows.items() if r['text']!=baseline[rid]['text']]
 deployment_comparisons.append({'repeat':repeat,'deployment':deployment,'length':length,'concurrency':concurrency,'differences':differences})
paired=[]
for repeat in sorted({r['repeat'] for r in records}):
 current={r['label']:r for r in records if r['repeat']==repeat}
 for label,row in current.items():
  if row['kind'] in ['inference','policy']:
   reference=current['spec-target' if row['kind']=='inference' else 'policy-native']
   assert row['workload_sha256']==reference['workload_sha256']
   before,after=reference['metrics']['elapsed_s'],row['metrics']['elapsed_s']
   paired.append({'repeat':repeat,'candidate':label,'baseline':reference['label'],'elapsed_reduction':1-after/before,'request_throughput_relative_gain':before/after-1})
atomic_json(args.report,{'state_evidence':state_evidence,'paired_comparisons':paired,'aggregator_file_sha256':file_hash(Path(__file__).resolve()),'rounds':[json.load(open(p))['plan'] for p in args.states],'independent_inner_runs':len(seen),
 'records':records,'run_level_statistics':summary,'policy_comparisons':policy_comparisons,'observer_overhead':observer_overhead,'inference_comparisons':inference_comparisons,'deployment_comparisons':deployment_comparisons,
 'limits':['Run, not each token/request/Event sample, is the independent unit. Three runs still do not establish a production P99.',
 'No final-test access. Dev thresholds are small-sample engineering gates, not statistical noninferiority or safety.',
 'Output lengths may change; show elapsed time, requests/s, quality and token/s together.',
 'These are separate profiles; CUDA standalone speed is not an end-to-end serving gain.',
 'Policy source analyzer supplies detailed group and maintenance data; summary is not a replacement for those raw observations.']})
print(json.dumps({'independent_runs':len(seen),'rounds':len(args.states),'metric_groups':len(summary)},indent=2))
