"""Reaggregate observed heap maintenance events without inferring old timings."""
import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path.cwd()))
from driveserve.evidence import atomic_json,file_hash,verify_assets
p=argparse.ArgumentParser();p.add_argument('--run',type=Path,required=True);p.add_argument('--wrapper',type=Path,required=True);p.add_argument('--report',type=Path,required=True);a=p.parse_args();root=Path.cwd()
m=json.load(open(a.run/'manifest.json'));w=json.load(open(a.wrapper/'manifest.json'))
for item in [m,w]:verify_assets(root,item);assert item['status']=='completed' and item['stage']=='S4' and not item['code']['dirty']
assert m['code']['sha']==w['code']['sha']
assert all(m['process'][k]==w['child_process'][k] for k in ['pid','boot_id','start_ticks'])
assert m['result']['bundles']==1024 and m['result']['same_victims_and_metadata']
cells=json.load(open(a.run/'operations.json'));summary=[]
def brief(row):
 return {k:row[k] for k in ['step','clock','elapsed_ns','evict_ns','stale_pops_delta','rebuilds_delta','methods','gc_events']}
for cell in cells:
 rows=cell['rows'];n=cell['capacity'];assert len(rows)==512 and all(x['same_victim_and_metadata'] for x in rows)
 assert rows[0]['stale_pops_delta']==n//2 and rows[0]['rebuilds_delta']==0
 first=next(x for x in rows[0]['methods'] if x['method']=='take_cold');assert first['stale_pops_delta']==n//2
 expiry=next(x for x in rows[256]['methods'] if x['method']=='expire')
 rebuild=[(r['step'],v) for r in rows for v in r['methods'] if v['method']=='compact' and v['rebuilds_delta']]
 assert sum(v['rebuilds_delta'] for _,v in rebuild)==cell['heap_rebuilds']
 summary.append({'capacity':n,'first':brief(rows[0]),'forced_expiry':brief(rows[256]),
  'live_expiry_reindexed_from_heap_count_delta':expiry['heap_entries_after'][0]-expiry['heap_entries_before'][0],
  'max_bundle':brief(max(rows,key=lambda x:x['elapsed_ns'])),'actual_compactions':[{'step':s,**v} for s,v in rebuild],
  'gc_events':sum(len(r['gc_events']) for r in rows),'total_stale_pops':cell['stale_pops']})
assert {x['capacity'] for x in summary}=={128,16384}
atomic_json(a.report,{'status':'passed','aggregator_sha256':file_hash(Path(__file__)),'run_id':m['run_id'],'source_sha':m['code']['sha'],'wrapper_run_id':w['run_id'],'assets':[{'path':str(p),'sha256':file_hash(p)} for p in [a.run/'manifest.json',a.run/'operations.json',a.wrapper/'manifest.json']],
 'cells':summary,'limits':m['result']['limits']+['GC may be triggered by the diagnostic instrumentation itself. A long measured compact method with rebuild delta zero is not an actual heap rebuild.','Bounded lazy storage does not bound per-operation work; no worst-case O(log N) or end-to-end latency guarantee.']})
print(json.dumps({'status':'passed','run_id':m['run_id'],'initial_stale_pops':{str(x['capacity']):x['first']['stale_pops_delta'] for x in summary}}))
