"""Attribute diagnostic heap work to stale popping, expiry, compaction and GC.

This instrumented run is separate from formal timing; nested method times
must not be added together or used as uninstrumented service performance.
"""
import gc,json,time,sys
from pathlib import Path
sys.path.insert(0,str(Path.cwd()))
from driveserve.evidence import Run,atomic_json
from driveserve.engine_policies import ColdHotEvictor
from driveserve.heap_policy import HeapColdHotEvictor

class ObservedHeap(HeapColdHotEvictor):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs);self.method_events=[];self.observe=False
    def measured(self,name,method,*args):
        if not self.observe:return method(*args)
        started=time.perf_counter_ns();stale=self.stale_pops;rebuild=self.heap_rebuilds
        before=[len(self._cold),len(self._hot),len(self._expiry)]
        result=method(*args)
        self.method_events.append({'method':name,'elapsed_ns':time.perf_counter_ns()-started,'stale_pops_delta':self.stale_pops-stale,'rebuilds_delta':self.heap_rebuilds-rebuild,'heap_entries_before':before,'heap_entries_after':[len(self._cold),len(self._hot),len(self._expiry)]})
        return result
    def _take(self,heap):return self.measured('take_cold' if heap is self._cold else 'take_hot',super()._take,heap)
    def _expire(self,now):return self.measured('expire',super()._expire,now)
    def _compact(self,now):return self.measured('compact',super()._compact,now)

run=Run(Path.cwd(),'heap-maintenance-diagnostic',{'stage':'S4','requirement_ids':['M2-01','M2-02'],
 'hypothesis':'initial stale hot candidates and periodic compaction are separately observable operation costs',
 'capacities':[128,16384],'operations_per_capacity':512,'forced_ttl_expiry_step':256,
 'scope':'instrumented CPU structure diagnostic, not formal speed measurement or GPU performance'},formal=True)
print(run.path,flush=True)
current_gc=[];gc_starts={}
def callback(phase,info):
 stamp=time.perf_counter_ns();generation=info['generation']
 if phase=='start':gc_starts[generation]=stamp
 else:current_gc.append({'generation':generation,'start_ns':gc_starts.pop(generation,None),'stop_ns':stamp,'collected':info['collected'],'uncollectable':info['uncollectable']})
gc.callbacks.append(callback)
try:
 results=[]
 for capacity in [128,16384]:
  clock=[0.0];heap=ObservedHeap(clock=lambda:clock[0]);scan=ColdHotEvictor(clock=lambda:clock[0])
  for model in [heap,scan]:
   for i in range(capacity):model.add(i,i,16*(i%8+1),float(i))
   for i in range(capacity//4):model.record_reuse(i);model.record_reuse(i)
  heap.observe=True;rows=[]
  for step in range(512):
   clock[0]+=31.0 if step==256 else .001
   heap.method_events.clear();current_gc.clear()
   before={'stale_pops':heap.stale_pops,'rebuilds':heap.heap_rebuilds}
   start=time.perf_counter_ns();victim=heap.evict();evict_end=time.perf_counter_ns()
   bid=content=capacity+step
   heap.add(bid,content,32,float(capacity+step));heap.record_reuse(content);heap.record_reuse(content)
   heap.update(bid,float(capacity+step)+.5);heap.remove(bid);heap.add(bid,content,32,float(capacity+step)+.5)
   end=time.perf_counter_ns();events=list(heap.method_events);gc_events=list(current_gc)
   expected=scan.evict();assert victim==expected
   scan.add(bid,content,32,float(capacity+step));scan.record_reuse(content);scan.record_reuse(content)
   scan.update(bid,float(capacity+step)+.5);scan.remove(bid);scan.add(bid,content,32,float(capacity+step)+.5)
   assert heap.free_table==scan.free_table and heap.reuse==scan.reuse
   heap.assert_index_invariants()
   rows.append({'step':step,'clock':clock[0],'victim':victim,'same_victim_and_metadata':True,'elapsed_ns':end-start,'evict_ns':evict_end-start,
      'stale_pops_delta':heap.stale_pops-before['stale_pops'],'rebuilds_delta':heap.heap_rebuilds-before['rebuilds'],'methods':events,'gc_events':gc_events})
  assert rows[0]['stale_pops_delta']==capacity//2
  assert any(x['methods'][0]['method']=='expire' for x in rows)
  results.append({'capacity':capacity,'rows':rows,'stale_pops':heap.stale_pops,'heap_rebuilds':heap.heap_rebuilds})
  atomic_json(run.path/'operations.json',results)
 run.finish('completed',{'capacity_cases':2,'bundles':1024,'same_victims_and_metadata':True,
  'initial_stale_pops':{str(x['capacity']):x['rows'][0]['stale_pops_delta'] for x in results},
  'limits':['Nested _expire/_compact/_take times overlap; never sum them as disjoint costs.',
  'GC callbacks and method tracing perturb timing; use to identify actual operations, not benchmark gains.',
  'Controlled TTL jump exercises expiry; no claim that real requests advance time this way.',
  'This diagnoses structures in a new run; it does not prove exact GC or scheduling events in earlier timing runs.']})
except BaseException as exc:run.finish('failed',{'error':str(exc)});raise
finally:gc.callbacks.remove(callback)
