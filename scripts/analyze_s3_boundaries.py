"""Verify real post-fix S3 diagnostics and retain their explicit scope."""
import argparse,json,re,subprocess,sys
from pathlib import Path
sys.path.insert(0,str(Path.cwd()))
from driveserve.evidence import atomic_json,file_hash,verify_assets
from scripts.analyze_policies import analyze
p=argparse.ArgumentParser();p.add_argument('--state',type=Path,required=True);p.add_argument('--report',type=Path,required=True);a=p.parse_args()
root=Path.cwd();state=json.load(open(a.state));assert state['status']=='completed'
plan=json.load(open(state['plan']));assert file_hash(state['plan'])==state['plan_sha256']
reports=[];lifecycles=[];fixed=[];randoms=[]
for task in plan['tasks']:
 attempts=[x for x in state['attempts'] if x['label']==task['label'] and x['status']=='completed'];assert len(attempts)==1
 x=attempts[0];wrapper_path=Path(x['wrapper_manifest']);wm=json.load(open(wrapper_path));assert wm['status']=='completed' and wm['result']['returncode']==0
 assert not wm['code']['dirty'] and wm['code']['sha']==state['code_sha'] and wm['stage']=='S3'
 verify_assets(root,wm)
 entry={'label':task['label'],'wrapper_run_id':wm['run_id'],'wrapper_sha256':file_hash(wrapper_path),'inner':[]}
 log=(wrapper_path.parent/'command.log').read_text()
 if task['label'].endswith('cpu-protocol'):assert 'Ran 28 tests' in log and '\nOK' in log
 if task['label'].endswith('allocator'):assert 'Ran 4 tests' in log and '\nOK' in log
 if task['label'].endswith('memcheck'):
  assert 'ERROR SUMMARY: 0 errors' in log and 'Correctness passed: 16 CUDA cases' in log
 inner_paths=list(x['inner_manifests'])
 if task['label'].endswith('memcheck') and not inner_paths:
  # compute-sanitizer inserts a process between wrapper and Python. The live
  # runner's direct-child discovery missed it; retain state verbatim and bind
  # its real manifest from the hashed wrapper log instead.
  ids=re.findall(r'(?m)^/[^\n]*experiments/runs/(\d{8}T\d{6}\+\d{4}-[0-9a-f]{10})$',log)
  assert len(ids)==1
  inner_paths=[f'experiments/runs/{ids[0]}/manifest.json']
  entry['inner_discovery']='sanitizer child path in verified wrapper log'
 for path in map(Path,inner_paths):
  m=json.load(open(path));verify_assets(root,m);assert m['status']=='completed' and m['stage']=='S3' and not m['code']['dirty']
  assert m['code']['sha']==state['code_sha']
  folder=path.parent.resolve();kind=m['kind'];result=m['result']
  detail={'run_id':m['run_id'],'kind':kind,'code_sha':m['code']['sha'],'manifest_sha256':file_hash(path),'result':result}
  if kind.startswith('vllm-policy-'):
   value,_=analyze(folder,root);detail['policy']=value
   if kind=='vllm-policy-lifecycle':
    assert value['shared_cancel_blocks']>0 and value['preemptions']>0 and value['invariant_snapshots']>0
    assert value['groups']['all']['cancelled']==2 and value['groups']['all']['failed']==0
    order=value['first_prefill_order'];assert all(order['aged-long']<order[f'new-short-{i}'] for i in range(4))
    lifecycles.append(m['run_id'])
   else:assert value['variant']=='both' and value['eviction_events']>0 and value['admission_reorders']>0
  elif kind=='rope-index-alias-probe':assert result['cases']==4 and result['rejected']==4 and result['dispatch_reached']==0
  elif kind=='rope-input-contract':
   assert result['invalid_cases']==24 and result['all_negative_slots_leave_cache_unchanged'] and result['read_only_index_alias_matches_disjoint_reference']
  elif kind=='rope-cache-cuda-validation':
   assert result['correctness_cases']==(16 if m['config']['sanitizer'] else 48)
  elif kind=='data-isolation-audit':
   assert result['teacher']['eligible_train']==472 and not result['final_test']['opened_by_this_audit']
  elif kind=='vllm-speculation':
   assert m['config']['trace'] and not m['config']['eager']
   (fixed if m['config']['mode']=='fixed' else randoms).append(str(folder))
  else:raise ValueError(kind)
  entry['inner'].append(detail)
 reports.append(entry)
assert len(lifecycles)==2 and len(fixed)==4 and len(randoms)==2
before=Path('experiments/runs/20261015T130427+0800-e78bf72ca5/manifest.json');bm=json.load(open(before));verify_assets(root,bm)
assert bm['result']['dispatch_reached']==4 and bm['result']['rejected']==0
# The checked-entry fix must not replace the measured GPU kernel or binding.
for source in ['csrc/rope_cache.cu','csrc/rope_cache.cpp']:
 old=subprocess.check_output(['git','show',bm['code']['sha']+':'+source]);assert old==Path(source).read_bytes()
trace_report=a.report.with_name(a.report.stem+'-fixed.json');random_report=a.report.with_name(a.report.stem+'-random.json')
original='experiments/runs/20261015T120019+0800-1735067ddc';trained='experiments/runs/20261015T120135+0800-8f2c7fba2a'
subprocess.run([sys.executable,'scripts/analyze_speculation.py','--runs','experiments/runs/20261015T115909+0800-2d8ec6c644',original,trained,*fixed,'--contributions','--report',str(trace_report)],check=True)
subprocess.run([sys.executable,'scripts/analyze_speculation.py','--runs',*randoms,'--contributions','--report',str(random_report)],check=True)
fr=json.load(open(trace_report));acceptance={}
for row in fr['runs']:
 if row['mode']=='target':continue
 assert row['quality_correct']>=120 and row['requests']==137
 m=json.load(open(Path('experiments/runs')/row['run_id']/'manifest.json'))
 name='trained' if 'distilled' in m['config']['model']['draft']['files'][0]['path'] else 'original'
 acceptance.setdefault(name,[]).append({'run_id':row['run_id'],'accepted':row['continuous_accepted'],'proposed':row['proposed'],'rate':row['acceptance_rate'],'quality_correct':row['quality_correct'],'requests':row['requests']})
assert all(x['identical']==137 for x in fr['greedy_comparisons'])
assert {k:len(v) for k,v in acceptance.items()}=={'original':3,'trained':3}
rr=json.load(open(random_report));assert len(rr['runs'])==2
assert len({x['workload_sha256'] for x in rr['runs']})==1
assert all(x['requests']==41 and x['quality_total']==32 for x in rr['runs'])
adaptive=next(x for x in rr['runs'] if x['mode']=='adaptive')
assert len(adaptive['actual_k_histogram'])>1 and adaptive['changes']
assert all(adaptive[k]>0 for k in ['rejected_rows','bonus_rows','natural_stop_token_rows','length_truncated_rows','no_proposal_rows'])
result={'status':'passed','aggregator_file_sha256':file_hash(Path(__file__)),
 'state':{'path':str(a.state),'sha256':file_hash(a.state)},'tasks':reports,
 'alias_before':{'run_id':bm['run_id'],'manifest_sha256':file_hash(before),'result':bm['result']},
 'same_cuda_sources_before_after':True,'fixed_acceptance':acceptance,
 'fixed_trace_report':{'path':str(trace_report),'sha256':file_hash(trace_report)},
 'random_trace_report':{'path':str(random_report),'sha256':file_hash(random_report)},
 'limits':['Diagnostic runtimes are not eligible for timing comparisons.',
 'Index alias before-fix probe intercepted extension dispatch; it did not execute an unsafe kernel.',
 'Random model tokens need not match across target and speculative paths; controlled CUDA categorical tests remain separate S2 evidence.',
 'Initial fixed trace was concurrent with GPU1 calibration; only its count/quality observations are reused.',
 'Real host migration, physical 24GB devices, production P99/SLO, TP/beam/swap/chunked custom-policy combinations remain unvalidated.']}
atomic_json(a.report,result);print(json.dumps({'status':'passed','tasks':len(reports),'fixed_acceptance':acceptance},indent=2))
