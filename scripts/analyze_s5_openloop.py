"""Recompute all HTTP metrics from immutable request rows and trajectory timestamps."""
import argparse,hashlib,json,statistics,subprocess,sys
from collections import defaultdict
from pathlib import Path
sys.path.insert(0,str(Path.cwd()))
from driveserve.evidence import atomic_json,file_hash,verify_assets
from driveserve.openloop_stats import summarize
from driveserve.benchmark import percentile
p=argparse.ArgumentParser();p.add_argument('--states',nargs='+',type=Path,required=True);p.add_argument('--report',type=Path,required=True);a=p.parse_args()
root=Path.cwd();records=[];states=[];seen=set();source_fingerprints={};raw_cells={}
def source_fingerprint(sha):
 if sha not in source_fingerprints:
  h=hashlib.sha256()
  for path in ['scripts/benchmark_openloop.py','driveserve/openloop.py','driveserve/openloop_stats.py','driveserve/benchmark.py','driveserve/task.py']:
   h.update(path.encode());h.update(subprocess.check_output(['git','show',sha+':'+path]))
  source_fingerprints[sha]=h.hexdigest()
 return source_fingerprints[sha]
for sp in a.states:
 state=json.load(open(sp));assert state['stage']=='S5' and state['status']=='completed'
 plan=json.load(open(state['plan']));assert file_hash(state['plan'])==state['plan_sha256'];states.append(dict(path=str(sp),sha256=file_hash(sp),code_sha=state['code_sha']))
 for task in plan['tasks']:
  if task.get('inner_kind')!='deployment-openloop':continue
  attempts=[x for x in state['attempts'] if x['label']==task['label'] and x['status']=='completed'];assert len(attempts)==1
  x=attempts[0];wm=json.load(open(x['wrapper_manifest']));verify_assets(root,wm);assert wm['status']=='completed' and not wm['code']['dirty']
  assert len(x['inner_manifests'])==1
  folder=Path(x['inner_manifests'][0]).parent;m=json.load(open(folder/'manifest.json'));verify_assets(root,m)
  assert m['status']=='completed' and not m['code']['dirty'] and m['code']['sha']==wm['code']['sha']==state['code_sha']
  assert m['run_id'] not in seen;seen.add(m['run_id']);cfg=m['config'];protocol=cfg['protocol'];dep=cfg['deployment']
  work=json.load(open(folder/'workloads.json'));traj=json.load(open(folder/'trajectories.json'));env=json.load(open(folder/'environment.json'))
  for kind in protocol['workloads']:
   prompts={r['request_id']:r for r in work[kind]};assert len(prompts)==protocol['requests_per_cell']
   for rate in protocol['rates']:
    label=f'{kind}-r{rate}';rows=[json.loads(line) for line in (folder/(label+'-requests.jsonl')).read_text().splitlines()]
    measure=json.load(open(folder/(label+'-measurement.json')));before=json.load(open(folder/(label+'-summary.json')))
    assert len(rows)==len(prompts)==len({r['request_id'] for r in rows});assert {r['request_id'] for r in rows}==set(prompts)
    trajectory=traj[str(rate)];assert measure['arrival_window_s']==trajectory['arrival_window_s']
    for row in rows:
     i=row['ordinal'];assert row['planned_ns']==measure['epoch_ns']+round(trajectory['offsets_s'][i]*1e9)
     assert row['prompt_sha256']==prompts[row['request_id']]['prompt_sha256']
     assert row['endpoint']==f"http://127.0.0.1:{8081+(i%2 if dep=='replica' else 0)}/v1"
     if row['status']=='completed':
      assert row['prompt_tokens']==len(prompts[row['request_id']]['tokens'])
      assert row['planned_ns']<=row['sent_ns']<=row['first_content_ns']<=row['last_content_ns']<=row['finished_ns']
    key=(cfg['repeat'],dep,label);assert key not in raw_cells;raw_cells[key]={r['request_id']:r for r in rows}
    actual=summarize(rows,measure['epoch_ns'],trajectory['arrival_window_s'],protocol['slo'][kind]);actual.update(workload=kind,nominal_rate=rate,repeat=cfg['repeat'],deployment=dep)
    assert actual==before,'saved summary differs from actual raw reaggregation'
    if protocol['prefix_cache']:
     resets=json.load(open(folder/(label+'-cache-reset.json')));assert len(resets)==(2 if dep=='replica' else 1)
     assert all('Successfully reset prefix cache' in r['log_excerpt'] and 'Failed to reset prefix cache' not in r['log_excerpt'] for r in resets)
    groups={g:[r for r in rows if prompts[r['request_id']]['group']==g] for g in sorted({v['group'] for v in prompts.values()})}
    group_metrics={g:summarize(rs,measure['epoch_ns'],trajectory['arrival_window_s'],protocol['slo'][kind],measurement_end_ns=actual['last_attempt_finished_ns']) for g,rs in groups.items()}
    sent=[r for r in rows if r['sent_ns'] is not None]
    stamps=[r['sent_ns'] for r in sent]
    worker_lags=[(r['worker_start_ns']-r['planned_ns'])/1e9 for r in rows if r['worker_start_ns'] is not None]
    post_delays=[(r['sent_ns']-r['dispatch_ns'])/1e9 for r in sent]
    delivery=dict(planned_span_s=trajectory['offsets_s'][-1]-trajectory['offsets_s'][0],
      actual_headers_span_s=(max(stamps)-min(stamps))/1e9 if stamps else None,
      actual_header_rate_over_span_plus_one_interval=len(sent)/((max(stamps)-min(stamps))/1e9+1/rate) if stamps else None,
      scheduled_rate_over_horizon=len(rows)/trajectory['arrival_window_s'],
      last_header_lag_from_last_planned_s=(max(stamps)-max(r['planned_ns'] for r in rows))/1e9 if stamps else None,
      global_permits_at_least_all_attempts=protocol['max_inflight']>=len(rows),
      worker_start_lag_s=dict(p50=percentile(worker_lags,.5),p99=percentile(worker_lags,.99),max=max(worker_lags) if worker_lags else None),
      post_to_headers_s=dict(p50=percentile(post_delays,.5),p99=percentile(post_delays,.99),max=max(post_delays) if post_delays else None),
      scope='Client event-loop and connection jitter remain explicit. With permits>=all attempts, semaphore cannot limit arrivals; this does not prove zero generator perturbation.')
    records.append(dict(run_id=m['run_id'],code_sha=m['code']['sha'],execution_source_fingerprint=source_fingerprint(m['code']['sha']),
      deployment=dep,repeat=cfg['repeat'],purpose=cfg['purpose'],label=label,
      protocol_sha256=cfg['protocol_file']['sha256'],workload_sha256=file_hash(folder/'workloads.json'),trajectory_sha256=file_hash(folder/'trajectories.json'),
      environment={k:env[k] for k in ['gpu','packages']},metrics=actual,groups=group_metrics,delivery_diagnostic=delivery,
      raw_rows_sha256=file_hash(folder/(label+'-requests.jsonl'))))
summary={};grouped=defaultdict(list)
for row in records:grouped[(row['deployment'],row['label'])].append(row)
for (dep,label),rows in grouped.items():
 assert len({r['repeat'] for r in rows})==len(rows)
 assert len({r['execution_source_fingerprint'] for r in rows})==1
 assert len({r['protocol_sha256'] for r in rows})==1
 assert all(r['environment']==rows[0]['environment'] for r in rows)
 metrics={}
 for k in ['success','failed','timeout','cancelled','request_per_s','output_token_per_s','slo_goodput_per_s','quality_goodput_per_s','quality_correct','completion_rate']:
  vals=[r['metrics'][k] for r in rows];metrics[k]=dict(values=vals,mean=statistics.mean(vals),sample_stdev=statistics.stdev(vals) if len(vals)>1 else None)
 for k in ['e2e_s','user_e2e_s','ttft_s','tpot_s','send_lag_s']:
  for rank in ['p50','p99']:
   vals=[r['metrics'][k][rank] for r in rows];metrics[k+'_'+rank]=dict(values=vals,mean=statistics.mean(vals) if None not in vals else None,sample_stdev=statistics.stdev(vals) if len(vals)>1 and None not in vals else None)
 summary[dep+'/'+label]=dict(independent_runs=len(rows),run_ids=[r['run_id'] for r in rows],metrics=metrics)
for label in {r['label'] for r in records}:
 rows=[r for r in records if r['label']==label]
 assert len({r['workload_sha256'] for r in rows})==1 and len({r['trajectory_sha256'] for r in rows})==1
comparisons=[]
for (repeat,dep,label),rows in sorted(raw_cells.items()):
 if dep=='single' or (repeat,'single',label) not in raw_cells:continue
 baseline=raw_cells[(repeat,'single',label)];assert rows.keys()==baseline.keys()
 comparisons.append(dict(repeat=repeat,baseline='single',candidate=dep,label=label,total=len(rows),
  status_different_ids=[rid for rid,r in rows.items() if r['status']!=baseline[rid]['status']],
  output_text_different_ids=[rid for rid,r in rows.items() if r['text']!=baseline[rid]['text']],
  field_quality_different_ids=[rid for rid,r in rows.items() if r['quality']['fields']!=baseline[rid]['quality']['fields']],
  parsed_json_different_ids=[rid for rid,r in rows.items() if r['quality']['json_valid'] and baseline[rid]['quality']['json_valid'] and json.dumps(json.loads(r['text']),sort_keys=True)!=json.dumps(json.loads(baseline[rid]['text']),sort_keys=True)],
  exact_quality_different_ids=[rid for rid,r in rows.items() if r['quality']['exact_match']!=baseline[rid]['quality']['exact_match']],
  baseline_incorrect_ids=[rid for rid,r in baseline.items() if r['status']!='completed' or not r['quality']['exact_match']],
  candidate_incorrect_ids=[rid for rid,r in rows.items() if r['status']!='completed' or not r['quality']['exact_match']],
  scope='same prompt/arrival identifiers; HTTP text and rule quality comparison, not output-token-ID or random-distribution proof'))
atomic_json(a.report,dict(aggregator_sha256=file_hash(__file__),state_evidence=states,independent_processes=len(seen),records=records,run_level_statistics=summary,request_comparisons=comparisons,
 limits=['P99 is an exploratory nearest-rank statistic for this finite per-cell request budget; process repeats are the independent units.',
 'Synthetic padding may benefit from APC shared prefixes; subgroup goodputs use the full-cell denominator, not separate offered windows.',
 'SLO uses planned-arrival user latency/first content; all attempts/failures and drain enter denominators.',
 'Natural dev scenes repeat; this is not held-out final-test quality.',
 'Historical S3 TP2 variation has no diagnosed cause; new measurements do not retrospectively explain it.']))
print(json.dumps(dict(processes=len(seen),cells=len(records),groups=len(summary))))
