"""Audit targeted TP quality diagnostics; no timing or universal equivalence claim."""
import argparse,json
from pathlib import Path
import sys
sys.path.insert(0,str(Path.cwd()))
from driveserve.evidence import atomic_json,file_hash,verify_assets
from driveserve.task import score
p=argparse.ArgumentParser();p.add_argument('--single',type=Path,required=True);p.add_argument('--tp2',type=Path,required=True);p.add_argument('--report',type=Path,required=True);args=p.parse_args()
data=[];manifests=[];common=[]
for folder in [args.single,args.tp2]:
 m=json.load(open(folder/'manifest.json'));assert m['status']=='completed' and m['config']['purpose']=='quality-diagnostic';verify_assets(Path.cwd(),m);manifests.append(m)
 rows=json.load(open(folder/'quality-diagnostics.json'))
 for row in rows:assert row['quality']==score(row['scene'],row['response']['choices'][0]['text'])
 data.append({r['request_id']:r for r in rows});common.append(json.load(open(folder/'common-prefix-diagnostic.json')))
assert [m['config']['deployment'] for m in manifests]==['single','tp2']
for key in ['model','data','service_budget']:assert manifests[0]['config'][key]==manifests[1]['config'][key]
differences=[]
for rid,a in data[0].items():
 b=data[1][rid];assert a['body']==b['body']
 ac,bc=[r['response']['choices'][0] for r in [a,b]]
 at,bt=[c['logprobs']['tokens'] for c in [ac,bc]]
 if at==bt:continue
 first=next(i for i,(x,y) in enumerate(zip(at,bt)) if x!=y);assert at[:first]==bt[:first]
 scores=[]
 for c in [ac,bc]:
  lp=c['logprobs'];chosen=lp['tokens'][first];top=lp['top_logprobs'][first]
  assert top[chosen]==max(top.values())
  scores.append({'selected':chosen,'top_logprobs':top,'single_choice_minus_tp_choice':top[at[first]]-top[bt[first]],
                 'selected_is_maximum':True})
 differences.append({'request_id':rid,'first_difference':first,'common_output_prefix':at[:first],
  'input_sha256':file_hash(args.single/'workloads.json'),'single_quality':a['quality'],'tp2_quality':b['quality'],
  'single_text':ac['text'],'tp2_text':bc['text'],'same_prefix_decode_scores':scores})
assert common[0]['body']==common[1]['body'] and common[0]['prefix_ids']==common[1]['prefix_ids']
faults=json.load(open(args.single/'http-faults.json'))
assert len(faults)==3 and all(f['request']['status']=='failed' for f in faults)
atomic_json(args.report,{'single_run':manifests[0]['run_id'],'tp2_run':manifests[1]['run_id'],'code_shas':[m['code']['sha'] for m in manifests],
 'differences':differences,'common_prefix_prefill':[{'prefix_ids':c['prefix_ids'],'response':c['response']['choices'][0]} for c in common],
 'http_errors':[{'case':f['case'],'status':f['request']['status'],'error':f['request']['error']} for f in faults],
 'interpretation':'Same-prefix decode directly shows a small single-GPU margin becoming a TP2 tie; consistent with FP16 arithmetic under changed parallel computation shapes. The observed task error remains a regression.',
 'limits':['Targeted three dev neighbors and one common-prefix probe, not general sequence/distribution equivalence.',
 'Common-prefix one-step prefill is a different kernel shape from full iterative decode and is reported separately.',
 'No evidence isolates NCCL/all-reduce alone as the cause; GEMM partitioning and other FP16 execution differences also change.',
 'Logprobs and HTTP fault checks are diagnostics, excluded from formal timing. No final-test access.']})
print(json.dumps({'different_ids':[r['request_id'] for r in differences],'first_differences':[r['first_difference'] for r in differences],'http_errors':len(faults)},indent=2))
