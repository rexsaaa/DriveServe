"""Reaggregate policy experiments from verified request logs, never preset numbers."""
import argparse
from collections import Counter
import json
from pathlib import Path
import statistics
import sys
sys.path.insert(0,str(Path.cwd()))
from driveserve.evidence import atomic_json, file_hash, verify_assets


def describe(values):
    return {'count':len(values), 'mean':statistics.mean(values) if values else None,
            'median':statistics.median(values) if values else None, 'max':max(values) if values else None}


def analyze(path,root):
    m=json.loads((path/'manifest.json').read_text())
    if m['status']!='completed':
        raise ValueError('incomplete run: '+str(path))
    verify_assets(root,m)
    workload=json.loads((path/'workload.json').read_text())
    data=json.loads((path/'results.json').read_text())
    expected={w['request_id']:w for w in workload}
    if len(expected)!=len(data) or len({r['request_id'] for r in data})!=len(data):
        raise ValueError('duplicate/missing result')
    events=[json.loads(line) for p in (path/'engine-trace').glob('*.jsonl') for line in p.read_text().splitlines()]
    # Exclude warmup and explicit reset evictions; use actual request event windows.
    intervals=[]
    for scenario in {w['scenario'] for w in workload}:
        ids={w['request_id'] for w in workload if w['scenario']==scenario}
        starts=[e['monotonic_ns'] for e in events if e['event']=='Scheduler.add_seq_group' and e.get('request_id') in ids]
        ends=[e['monotonic_ns'] for e in events if e['event']=='LLMEngine.step' and any(o['request_id'] in ids and o['finished'] for o in e.get('outputs',[]))]
        if starts and ends:
            intervals.append((min(starts),max(ends)))
    events=[e for e in events if any(start<=e['monotonic_ns']<=end for start,end in intervals)]
    evictions=[e for e in events if e['event']=='policy.cache_evict']
    orders=[e for e in events if e['event']=='policy.admission_order']
    phases=json.loads((path/'phases.json').read_text()) if (path/'phases.json').exists() else []
    if m['config']['suite']=='lifecycle':
        phases=[]  # warmup-only phases file is not lifecycle timing
    def group(rows,phase_list):
        complete=[r for r in rows if r['status']=='completed']
        for r in complete:
            assert len(r['output_token_ids'])==expected[r['request_id']]['output_tokens']
        elapsed=sum(p['elapsed_ns'] for p in phase_list)/1e9
        return {'requests':len(rows),'completed':len(complete),
            'cancelled':sum(r['status']=='cancelled' for r in rows),
            'failed':len(rows)-len(complete)-sum(r['status']=='cancelled' for r in rows),
            'elapsed_s':elapsed,
            'output_tokens_per_s':sum(len(r['output_token_ids']) for r in complete)/elapsed if elapsed else None,
            'cached_tokens_sum':sum(r['num_cached_tokens'] for r in complete),
            'wait_ms':describe([r['metrics']['time_in_queue']*1000 for r in complete]),
            'ttft_ms':describe([next(o['elapsed_ns'] for o in r['observations'] if o['tokens']>0)/1e6 for r in complete]),
            'e2e_ms':describe([r['elapsed_ns']/1e6 for r in complete]),
            'mean_token_interval_ms':describe([(r['observations'][-1]['elapsed_ns']-r['observations'][0]['elapsed_ns'])/1e6/(len(r['output_token_ids'])-1) for r in complete if len(r['output_token_ids'])>1])}
    groups={'all':group(data,phases)}
    for scenario in sorted({w['scenario'] for w in workload}):
        rows=[r for r in data if expected[r['request_id']]['scenario']==scenario]
        groups[scenario]=group(rows,[p for p in phases if p['scenario']==scenario])
    for name,predicate in [('short',lambda n:n<512),('long',lambda n:n>=512)]:
        groups[name]=group([r for r in data if predicate(expected[r['request_id']]['length'])],[])
    groups['hot_probe']=group([r for r in data if r['request_id'].startswith('hot-probe')],
                               [p for p in phases if p['phase']=='hot-probe'])
    snapshots=json.loads((path/'snapshots.json').read_text())
    first_prefill={}
    for e in events:
        if e['event']=='Scheduler.schedule':
            for scheduled in e.get('scheduled',[]):
                if scheduled['is_prompt'] and scheduled['request_id'] not in first_prefill:
                    first_prefill[scheduled['request_id']]=len(first_prefill)
    allocations={e.get('request_id'):e.get('tables') for e in events if e['event']=='SelfAttnBlockSpaceManager.allocate'}
    shared_cancel_blocks=None
    if 'cancel-0' in allocations and 'cancel-1' in allocations:
        shared_cancel_blocks=len(set(next(iter(allocations['cancel-0'].values()))) & set(next(iter(allocations['cancel-1'].values()))))
    result={'run_id':m['run_id'],'code_sha':m['code']['sha'],'variant':m['config']['variant'],
            'trace':m['config']['trace'],'suite':m['config']['suite'],
            'max_num_seqs':m['config']['max_num_seqs'],'eager':m['config']['eager'],
            'upstream':m['config'].get('upstream',False), 'shared_cancel_blocks':shared_cancel_blocks,
            'workload_sha256':file_hash(path/'workload.json'),'groups':groups,
            'preemptions':sum(e.get('preempted',0) for e in events if e['event']=='Scheduler.schedule') if m['config']['trace'] else None,
            'effective_full_reused_blocks':sum(e['full_reused_blocks'] for e in events if e['event']=='policy.prefix_reuse') if m['config']['trace'] else None,
            'effective_skipped_tokens':sum(e['skipped_tokens'] for e in events if e['event']=='policy.prefix_reuse') if m['config']['trace'] else None,
            'eviction_events':len(evictions) if m['config']['trace'] and m['config']['variant'] in ('cache','both') else None,
            'hot_evictions':sum(e['hot'] for e in evictions) if m['config']['trace'] and m['config']['variant'] in ('cache','both') else None,
            'selection_ns':describe([e['selection_ns'] for e in evictions]),
            'admission_reorders':sum(e['before']!=e['after'] for e in orders) if m['config']['trace'] else None,
            'aged_priority_events':sum(bool(e['aged']) for e in orders) if m['config']['trace'] else None,
            'order_ns':describe([e['host_order_ns'] for e in orders]),
            'first_prefill_order':first_prefill,'invariant_snapshots':len(snapshots),
            'final_pool':snapshots[-1],
            'assets':[{'path':str(p.relative_to(root)),'sha256':file_hash(p)} for p in [path/'manifest.json',path/'workload.json',path/'results.json']]}
    return result,{r['request_id']:r.get('output_token_ids') for r in data}


def main():
    p=argparse.ArgumentParser();p.add_argument('--runs',nargs='+',type=Path,required=True);p.add_argument('--report',type=Path,required=True);args=p.parse_args()
    root=Path.cwd().resolve()
    reports,outputs=[],{}
    for path in args.runs:
        report,out=analyze(path.resolve(),root);reports.append(report);outputs[report['run_id']]=out
    comparisons=[]
    for suite in sorted({r['suite'] for r in reports}):
        rows=[r for r in reports if r['suite']==suite]
        base=next(r for r in rows if r['variant']=='native')
        for r in rows:
            b,o=outputs[base['run_id']],outputs[r['run_id']]
            equal=[key for key in set(b)&set(o) if b[key]==o[key]]
            different=[key for key in set(b)&set(o) if b[key]!=o[key]]
            comparisons.append({'baseline':base['run_id'],'candidate':r['run_id'],
                'same_workload':base['workload_sha256']==r['workload_sha256'],
                'same_tokens_or_cancel_status':len(equal),'different_requests':sorted(different),
                'missing_ids':sorted(set(b)^set(o))})
    atomic_json(args.report,{'schema_version':1,'aggregator_sha256':file_hash(Path(__file__)),
        'runs':reports,'output_comparisons':comparisons,
        'limits':['native is native LRU/FCFS plus shared waiting-prefix correctness fix',
                  'barrier workload; no HTTP, final P99 or quality conclusions',
                  'traced runs and lifecycle checks are diagnostics, not uninstrumented timing',
                  'single independent observation unless repeat recorded; no significance claim']})
    print(json.dumps({'report':str(args.report),'comparisons':comparisons},indent=2))
if __name__=='__main__':main()
