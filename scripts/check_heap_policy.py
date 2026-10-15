"""S4 differential trace and whole-operation maintenance benchmark."""
import argparse,json,math,random,statistics,sys,time,tracemalloc
from pathlib import Path
sys.path.insert(0,str(Path.cwd()))
from driveserve.evidence import Run,atomic_json
from driveserve.engine_policies import ColdHotEvictor
from driveserve.heap_policy import HeapColdHotEvictor
p=argparse.ArgumentParser();p.add_argument('--repeat',type=int,required=True);a=p.parse_args()
run=Run(Path.cwd(),'heap-policy-comparison',{'stage':'S4','repeat':a.repeat,'requirement_ids':['M2-01','M2-02'],
 'hypothesis':'exact victim order can be maintained with bounded lazy heaps, reducing large-pool scan cost',
 'seed':4401,'correctness_steps':20000,'capacities':[128,1024,8192,16384],
 'operations_per_capacity':256,'scope':'actual policy classes on CPU, not GPU throughput or serving latency'},formal=True)
print(run.path,flush=True)
try:
 boundary=[]
 for last,ttl in [(0.1,.3),(1e7+.1,.3),(2**40+.1,.3),(17.,30.)]:
  deadline=last+ttl
  for now in [math.nextafter(deadline,-math.inf),deadline,math.nextafter(deadline,math.inf)]:
   clock=[last];models=[cls(hot_threshold=2,hot_ttl_s=ttl,clock=lambda:clock[0]) for cls in [ColdHotEvictor,HeapColdHotEvictor]]
   for model in models:
    model.add(0,10,16,0.0);model.add(1,11,16,1.0);model.record_reuse(10);model.record_reuse(10)
   clock[0]=now;expected=models[0].evict();actual=models[1].evict();assert expected==actual
   boundary.append({'last':last,'ttl':ttl,'now':now,'same_victim':expected})
 atomic_json(run.path/'float-ttl-boundary.json',boundary)
 # Force a small resident pool through many index updates, then drain it.
 # Random traces alone need not hit the empty-table or compaction boundary.
 clock=[0.0];models=[cls(clock=lambda:clock[0]) for cls in [ColdHotEvictor,HeapColdHotEvictor]]
 for model in models:
  for bid in range(16):model.add(bid,bid,16,0.0)
 plateau=[]
 for step in range(5000):
  clock[0]+=.01
  for model in models:model.update(step%16,clock[0]);model.record_reuse(step%16)
  state=models[1].assert_index_invariants()
  if step%100==0:plateau.append({'step':step,**state})
 assert models[1].heap_rebuilds>0
 drained=[]
 while models[0].free_table:
  before=models[0].evict();after=models[1].evict();assert before==after;drained.append(before)
 for model in models:
  assert not model.free_table and not model.reuse
  try:model.evict()
  except ValueError:pass
  else:raise AssertionError('empty pool did not reject eviction')
 models[1].assert_index_invariants()
 atomic_json(run.path/'bounded-index.json',{'updates':5000,'snapshots':plateau,'same_drained_victims':drained,
  'empty_eviction_rejected':True,'final':models[1].assert_index_invariants()})
 rng=random.Random(4401);clock=[0.0]
 scan=ColdHotEvictor(clock=lambda:clock[0]);heap=HeapColdHotEvictor(clock=lambda:clock[0])
 models=[scan,heap];active={};next_hash=128;victims=[];max_entries=0;operations={}
 for i in range(128):
  for model in models:model.add(i,i,16*(i%8+1),0.0)
 for step in range(20000):
  clock[0]+=rng.choice([0.0,.001,.1,30.0,30.00001])
  choice=rng.randrange(5)
  if choice==0 and scan.free_table:
   bid=rng.choice(list(scan.free_table));meta=scan.free_table[bid];active[bid]=meta
   for model in models:model.remove(bid)
   kind='reactivate'
  elif choice==1 and active:
   bid=rng.choice(list(active));meta=active.pop(bid)
   for model in models:model.add(bid,meta.content_hash,meta.num_hashed_tokens,clock[0])
   kind='release'
  elif choice==2 and scan.free_table:
   bid=rng.choice(list(scan.free_table))
   for model in models:model.update(bid,clock[0])
   kind='touch'
  elif choice==3:
   candidates=[m.content_hash for m in scan.free_table.values()]+[m.content_hash for m in active.values()]
   content=rng.choice(candidates)
   for model in models:model.record_reuse(content)
   kind='effective-reuse'
  elif scan.free_table:
   reference=scan.evict();candidate=heap.evict();assert reference==candidate,(step,reference,candidate)
   bid,_=reference;next_hash+=1;depth=16*rng.randrange(1,100)
   for model in models:model.add(bid,next_hash,depth,clock[0])
   victims.append({'step':step,'block_id':bid,'content_hash':reference[1]});kind='evict-reuse'
  else:continue
  operations[kind]=operations.get(kind,0)+1
  assert scan.free_table==heap.free_table and scan.reuse==heap.reuse
  assert set(heap._versions)==set(heap.free_table)
  assert set(heap._by_hash)=={m.content_hash for m in heap.free_table.values()}
  entries=len(heap._cold)+len(heap._hot)+len(heap._expiry)
  assert entries<=max(64,4*len(heap.free_table));max_entries=max(max_entries,entries)
 atomic_json(run.path/'differential.json',{'steps':20000,'operations':operations,'victims':victims,
  'heap_rebuilds':heap.heap_rebuilds,'stale_pops':heap.stale_pops,'max_entries':max_entries,'same_metadata_and_victims':True})
 results=[]
 for capacity in [128,1024,8192,16384]:
  order=[('scan',ColdHotEvictor),('heap',HeapColdHotEvictor)]
  if a.repeat%2==0:order.reverse()
  outputs={}
  for name,cls in order:
   clock=[0.0];policy=cls(clock=lambda:clock[0]);tracemalloc.start();init_begin=time.perf_counter_ns()
   for i in range(capacity):policy.add(i,i,16*(i%8+1),float(i))
   for i in range(capacity//4):policy.record_reuse(i);policy.record_reuse(i)
   init_ns=time.perf_counter_ns()-init_begin
   resident_memory,peak=tracemalloc.get_traced_memory();tracemalloc.stop()
   raw=[];selected=[]
   for step in range(256):
    clock[0]+=.001
    start=time.perf_counter_ns();victim=policy.evict();evict_ns=time.perf_counter_ns()-start
    bid,h=capacity+step,capacity+step
    begin=time.perf_counter_ns()
    policy.add(bid,h,32,float(capacity+step))
    policy.record_reuse(h);policy.record_reuse(h)
    policy.update(bid,float(capacity+step)+.5)
    policy.remove(bid);policy.add(bid,h,32,float(capacity+step)+.5)
    maintenance_ns=time.perf_counter_ns()-begin
    raw.append({'step':step,'evict_ns':evict_ns,'other_operations_ns':maintenance_ns,'all_ns':evict_ns+maintenance_ns})
    selected.append(victim)
   outputs[name]=selected
   results.append({'capacity':capacity,'variant':name,'raw':raw,'resident_traced_bytes':resident_memory,
     'initialization_ns_with_tracemalloc':init_ns,'initialization_peak_traced_bytes':peak,'heap_rebuilds':getattr(policy,'heap_rebuilds',None),
     'median_all_ns':statistics.median(x['all_ns'] for x in raw),'sum_all_ns':sum(x['all_ns'] for x in raw),
     'p99_all_ns':sorted(x['all_ns'] for x in raw)[math.ceil(.99*len(raw))-1], 'max_all_ns':max(x['all_ns'] for x in raw)})
  assert outputs['scan']==outputs['heap']
  atomic_json(run.path/'maintenance.json',results)
 run.finish('completed',{'differential_steps':20000,'capacity_cases':4,'limits':[
  'Whole-operation CPU times include index updates and compaction; not model timings.',
  'Tracemalloc records Python tracked allocation at initialization, not complete process RSS.',
  'Three process repeats needed before reporting stability; within-run operations are correlated.',
  'Exact equivalence on these controlled traces does not prove correctness for arbitrary unsupported allocator contracts.']})
except BaseException as exc:run.finish('failed',{'error':str(exc)});raise
