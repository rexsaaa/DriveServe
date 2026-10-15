"""Verified speculation runs, causal acceptance and explicit output differences."""
import argparse,json,statistics,sys
from collections import Counter
from pathlib import Path
sys.path.insert(0,str(Path.cwd()))
from driveserve.evidence import atomic_json,verify_assets,file_hash
p=argparse.ArgumentParser();p.add_argument('--runs',type=Path,nargs='+',required=True);p.add_argument('--report',type=Path,required=True)
p.add_argument('--contributions',action='store_true',help='recompute per-workload causal acceptance and observed TPOT')
p.add_argument('--context',type=Path,help='versioned run-specific limitations, with an exact required_runs list')
args=p.parse_args()
root=Path.cwd();reports=[];raw={};work={}
for path in args.runs:
 m=json.load(open(path/'manifest.json'));assert m['status']=='completed';verify_assets(root,m)
 rows=json.load(open(path/'results.json'));workload=json.load(open(path/'workload.json'));ws={w['request_id']:w for w in workload}
 assert len(rows)==len(ws)==len({r['request_id'] for r in rows})
 events=[json.loads(l) for f in (path/'spec-trace').glob('*.jsonl') for l in f.read_text().splitlines()]
 verifies=[x for x in events if x['event']=='spec.verify' and any(row['request_id'] in ws for row in x['rows'])]
 choices=[x for x in events if x['event']=='spec.choose' and any(rid in ws for rid in x['request_ids'])]
 vrows=[row for x in verifies for row in x['rows'] if row['request_id'] in ws]
 proposed=sum(r['proposed'] for r in vrows);accepted=sum(r['accepted_draft_prefix'] for r in vrows)
 for x in verifies:assert x['proposal_width']==x['actual_k'] and x['verification_width']==x['actual_k']+1
 for r in vrows:assert 0<=r['accepted_draft_prefix']<=r['proposed']
 waves=json.load(open(path/'waves.json'));elapsed=sum(w['elapsed_ns'] for w in waves)/1e9
 groups={}
 for kind in sorted({w['kind'] for w in workload}):
  rs=[r for r in rows if ws[r['request_id']]['kind']==kind]
  groups[kind]={'requests':len(rs),'finish_counts':dict(Counter(r['finish_reason'] for r in rs)),
   'output_tokens':sum(len(r['output_token_ids']) for r in rs),
   'mean_e2e_ms':statistics.mean(r['elapsed_ns']/1e6 for r in rs),
   'mean_ttft_ms':statistics.mean(next(o['elapsed_ns'] for o in r['observations'] if o['tokens'])/1e6 for r in rs)}
 result={'run_id':m['run_id'],'sha':m['code']['sha'],'mode':m['config']['mode'],'trace':m['config']['trace'],
  'temperature':m['config']['temperature'],'maximum_k':m['config']['maximum_k'],'logprobs':m['config'].get('logprobs',0),
  'workload_sha256':file_hash(path/'workload.json'),'requests':len(rows),'groups':groups,
  'elapsed_s':elapsed,'output_tokens_per_s':sum(len(r['output_token_ids']) for r in rows)/elapsed,
  'quality_correct':sum(r['quality']['exact_match'] for r in rows if r['quality']),
  'quality_total':sum(bool(r['quality']) for r in rows),'verifier_batches':len(verifies),
  'actual_k_histogram':dict(Counter(x['actual_k'] for x in verifies)),
  'changes':[{k:x[k] for k in ['step','previous_k','k','reason','window_ratio','observed_batches']} for x in choices if x['changed']],
  'proposed':proposed if verifies else None,'continuous_accepted':accepted if verifies else None,
  'acceptance_rate':accepted/proposed if proposed else None,
  'rejected_rows':sum(r['rejected'] for r in vrows),'bonus_rows':sum(r['bonus'] for r in vrows),
  'natural_stop_token_rows':sum(bool(r['stop_token_positions']) and not r['ignore_eos'] for r in vrows),
  'length_truncated_rows':sum(r['beyond_output_budget']>0 for r in vrows),
  'no_proposal_rows':sum(r['no_proposal'] for r in vrows),
  'controller_summary':json.load(open(path/'controller-summary.json')) if (path/'controller-summary.json').exists() else None}
 if args.contributions:
  contribution={}
  for kind in groups:
   ids={w['request_id'] for w in workload if w['kind']==kind}
   vr=[r for r in vrows if r['request_id'] in ids]
   a=sum(r['accepted_draft_prefix'] for r in vr);n=sum(r['proposed'] for r in vr)
   tpot=[]
   for row in rows:
    if row['request_id'] in ids and len(row['output_token_ids'])>1:
     first=next(o['elapsed_ns'] for o in row['observations'] if o['tokens'])
     tpot.append((row['elapsed_ns']-first)/1e6/(len(row['output_token_ids'])-1))
   contribution[kind]={'accepted':a,'proposed':n,'acceptance_rate':a/n if n else None,
    'mean_observed_tpot_ms':statistics.mean(tpot) if tpot else None}
  result['contribution_groups']=contribution
 reports.append(result);raw[m['run_id']]={r['request_id']:r for r in rows};work[m['run_id']]=ws
comparisons=[]
for row in reports:
 if row['temperature']!=0:continue
 candidates=[r for r in reports if r['mode']=='target' and r['temperature']==0 and r['workload_sha256']==row['workload_sha256']]
 if not candidates:continue
 base=next((r for r in candidates if r['logprobs']==row['logprobs'] and r['trace']==row['trace']),candidates[0])
 diffs=[]
 for rid,a in raw[base['run_id']].items():
  b=raw[row['run_id']][rid];at,bt=a['output_token_ids'],b['output_token_ids']
  if at==bt:continue
  i=next((i for i,(x,y) in enumerate(zip(at,bt)) if x!=y),min(len(at),len(bt)))
  diffs.append({'request_id':rid,'first_difference':i,'kind':work[row['run_id']][rid]['kind'],
    'baseline_token':at[i] if i<len(at) else None,'candidate_token':bt[i] if i<len(bt) else None,
    'baseline_top_logprobs':a['token_logprobs'][i] if a.get('token_logprobs') and i<len(at) else None,
    'candidate_top_logprobs':b['token_logprobs'][i] if b.get('token_logprobs') and i<len(bt) else None})
 comparisons.append({'baseline':base['run_id'],'candidate':row['run_id'],'identical':row['requests']-len(diffs),'total':row['requests'],'differences':diffs})
extra_limits=[]
if args.context:
 context=json.load(open(args.context));assert set(context['required_runs'])=={r['run_id'] for r in reports}
 extra_limits=context['limitations'];assert all(isinstance(s,str) for s in extra_limits)
atomic_json(args.report,{'runs':reports,'greedy_comparisons':comparisons,
 'limitations':['all timing single observations, no stable speedup claim','verifier acceptance is before engine EOS/length truncation',
 'random-model sequences are not required to match; known-law sampler statistics are separate',
 'any unexplained greedy difference must remain explicit; do not mark full correctness proven']+extra_limits})
print(json.dumps({'report':str(args.report),'comparisons':[{k:v for k,v in r.items() if k!='differences'}|{'different_ids':[d['request_id'] for d in r['differences']]} for r in comparisons]},indent=2))
