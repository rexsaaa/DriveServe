"""Audit S5 final CPU, allocator, CUDA and engine supported-path regressions."""
import argparse,json,subprocess,sys
from pathlib import Path
sys.path.insert(0,str(Path.cwd()))
from driveserve.evidence import atomic_json,file_hash,verify_assets
from scripts.analyze_policies import analyze
p=argparse.ArgumentParser();p.add_argument('--state',type=Path,required=True);p.add_argument('--report',type=Path,required=True);a=p.parse_args()
root=Path.cwd();state=json.load(open(a.state));assert state['status']=='completed' and state['stage']=='S5'
plan=json.load(open(state['plan']));assert file_hash(state['plan'])==state['plan_sha256'];entries=[];lifecycles=[]
for task in plan['tasks']:
 rows=[x for x in state['attempts'] if x['label']==task['label'] and x['status']=='completed'];assert len(rows)==1
 x=rows[0];wp=Path(x['wrapper_manifest']);wm=json.load(open(wp));verify_assets(root,wm)
 assert wm['status']=='completed' and wm['result']['returncode']==0 and not wm['code']['dirty'] and wm['code']['sha']==state['code_sha']
 log=(wp.parent/'command.log').read_text();entry={'label':task['label'],'wrapper':{'run_id':wm['run_id'],'sha256':file_hash(wp)},'inner':[]}
 if task['label'].endswith('-cpu'):assert 'Ran 39 tests' in log and '\nOK' in log and 'skipped=' not in log
 if '-allocator-' in task['label']:assert 'Ran 4 tests' in log and '\nOK' in log
 if task['label'].endswith('memcheck'):assert 'ERROR SUMMARY: 0 errors' in log
 for ip in map(Path,x['inner_manifests']):
  m=json.load(open(ip));verify_assets(root,m);folder=ip.parent;v=m['result']
  assert m['status']=='completed' and m['stage']=='S5' and not m['code']['dirty'] and m['code']['sha']==state['code_sha']
  item={'run_id':m['run_id'],'code_sha':m['code']['sha'],'kind':m['kind'],'manifest_sha256':file_hash(ip),'result':v}
  if m['kind']=='rope-cache-depth-validation':
   cases=json.load(open(folder/'correctness.json'));assert len(cases)==v['correctness_cases']==(99 if m['config']['sanitizer'] else 275)
   assert len(v['invalid_inputs_rejected'])==4 and v['benchmark_shapes']==0
   assert all(c.get('exact_upstream_agreement',True) and c.get('matches_upstream',True) and c.get('auto_matches_upstream',True) for c in cases)
   assert {c['unaligned_input'] for c in cases if 'unaligned_input' in c}=={'projection','table','cache'}
  elif m['kind']=='rope-input-contract':
   assert v['invalid_cases']==24 and v['read_only_index_alias_matches_disjoint_reference'] and v['all_negative_slots_leave_cache_unchanged']
  elif m['kind']=='vllm-policy-lifecycle':
   value,_=analyze(folder.resolve(),root);raw=json.load(open(folder/'results.json'));assert value['invariant_snapshots']==792 and value['shared_cancel_blocks']==32 and value['preemptions']>0
   assert value['groups']['all']['cancelled']==2 and value['groups']['all']['failed']==0
   order=value['first_prefill_order'];assert all(order['aged-long']<order[f'new-short-{i}'] for i in range(4))
   item['policy']=value;item['implementation']=m['config']['cache_implementation'];lifecycles.append((item['implementation'],raw))
  else:raise ValueError(m['kind'])
  entry['inner'].append(item)
 entries.append(entry)
assert len(lifecycles)==2 and {x[0] for x in lifecycles}=={'scan','heap'}
# Compare raw stable fields, excluding timestamps and diagnostic cost.
left={x['request_id']:x for x in lifecycles[0][1]};right={x['request_id']:x for x in lifecycles[1][1]};assert left.keys()==right.keys()
for rid in left:
 assert left[rid]['status']==right[rid]['status'] and left[rid].get('output_token_ids')==right[rid].get('output_token_ids'),rid
assert len(entries)==10
for source in ['csrc/rope_cache.cu','csrc/rope_cache.cpp','csrc/rope_cache_tiled.cu','csrc/rope_cache_v2.cpp','driveserve/rope_cache.py']:
 assert subprocess.check_output(['git','show','stage-4-depth:'+source])==Path(source).read_bytes()
atomic_json(a.report,{'status':'passed','aggregator_sha256':file_hash(Path(__file__)),'state':{'path':str(a.state),'sha256':file_hash(a.state)},'tasks':entries,'same_frozen_s4_cuda_source':True,'lifecycle_token_and_status_equal':len(left),
 'limits':['Diagnostic CPU/index times do not enter the formal replicated timing report.','275 full and 99 sanitizer entries include variants and boundary cases, not independent processes.','Standalone CUDA has no serving integration; heap preserves the defined policy but this does not promise overall throughput gains.','Final-test quality has its own frozen protocol/report; this regression is not a new performance or migration claim.']})
print(json.dumps({'status':'passed','tasks':len(entries),'lifecycle_equal':len(left)}))
