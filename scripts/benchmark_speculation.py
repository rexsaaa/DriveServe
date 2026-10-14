"""Real target/fixed-K/adaptive-K inference with EOS, length and context boundaries."""
import argparse,json,os
from pathlib import Path
import sys,time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from driveserve.evidence import Run,atomic_json,file_hash
from driveserve.task import messages,score


def main():
 p=argparse.ArgumentParser()
 p.add_argument('--mode',choices=['target','fixed','adaptive'],required=True)
 p.add_argument('--overlay',type=Path,default=Path('/hy-tmp/driveserve/vllm-spec-v2'))
 p.add_argument('--target',type=Path,default=Path('/hy-tmp/driveserve/models/target'))
 p.add_argument('--draft',type=Path,default=Path('/hy-tmp/driveserve/models/draft-aligned-v1'))
 p.add_argument('--dataset',type=Path,default=Path('data/samples/proxy-v1.jsonl'))
 p.add_argument('--max-k',type=int,choices=[2,3,4],default=4)
 p.add_argument('--trace',action='store_true')
 p.add_argument('--temperature',type=float,default=0)
 p.add_argument('--limit',type=int,default=32)
 p.add_argument('--baseline-run')
 p.add_argument('--upstream',action='store_true',help='untouched wheel fixed-K control, no project observers')
 p.add_argument('--unseeded',action='store_true',help='use global RNG, retaining engine seed')
 p.add_argument('--batch-expansion',action='store_true',help='use upstream alternative scorer')
 p.add_argument('--quality-only',action='store_true',help='additional diagnostic subset, not full boundary acceptance')
 p.add_argument('--logprobs',type=int,choices=[0,5],default=0,help='diagnostic target top-5 per emitted token; excluded from timing comparisons')
 args=p.parse_args()
 if args.upstream and (args.mode!='fixed' or args.trace):p.error('untouched wheel requires fixed mode without trace')
 root=Path(__file__).resolve().parents[1]
 overlay=args.overlay.resolve();lock=json.load(open(overlay/'overlay-manifest.json'))
 assert lock['patch_sha256']==file_hash(root/'patches/vllm-v0.8.5-spec.patch')
 for f in lock['lock']['files']:assert file_hash(overlay/f['path'])==f['patched_sha256']
 provenances={}
 for name,path in [('target',args.target),('draft',args.draft)]:
  provenance=json.load(open(path/'driveserve-provenance.json'))
  for f in provenance['files']:
   assert file_hash(path/Path(f['path']).name)==f['sha256']
  provenances[name]=provenance
  assert json.load(open(path/'config.json'))['vocab_size']==152064
 assert file_hash(args.target/'tokenizer.json')==file_hash(args.draft/'tokenizer.json')
 assert file_hash(args.target/'tokenizer_config.json')==file_hash(args.draft/'tokenizer_config.json')
 config={'stage':'S2','requirement_ids':['M3-01','M3-02','M3-03'],
  'hypothesis':'bounded runtime K changes actual proposals/verification without modifying target acceptance or EOS handling',
  'mode':args.mode,'maximum_k':args.max_k,'upstream':args.upstream,'unseeded':args.unseeded,'batch_expansion':args.batch_expansion,'quality_only':args.quality_only,'logprobs':args.logprobs,'trace':args.trace,'temperature':args.temperature,'seed':37,
  'model':provenances,'overlay':lock,'data':{'path':str(args.dataset),'sha256':file_hash(args.dataset),'split':'dev'},
  'max_num_seqs':4,'max_model_len':1536,'max_num_batched_tokens':1536,'kv_blocks':512,'block_size':16,
  'dtype':'float16','eager':True,'prefix_caching':False,'async_output':False,
  'controller':{'initial':2,'window_batches':8,'minimum_hold_batches':8,'low':0.45,'high':0.8},
  'limitations':['single GPU V0 eager draft_model, n=1, non-chunked; no TP/beam/quantized target validation',
    'development quality fixture and synthetic length probes, not frozen final test',
    'verifier acceptance excludes bonus/recovery but precedes engine EOS/string/length truncation',
    'controller observes CPU copies of verifier tensors; their synchronization cost is included',
    'same KV block count but Draft adds its own weights/KV; not equal total memory to target-only']}
 run=Run(root,'vllm-speculation',config,formal=True,baseline_run_id=args.baseline_run)
 print(run.path,flush=True)
 try:
  os.environ.update(VLLM_USE_V1='0',VLLM_ATTENTION_BACKEND='FLASH_ATTN',CUDA_VISIBLE_DEVICES='0',
    VLLM_USE_FLASHINFER_SAMPLER='0',HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',
    DRIVESERVE_SPEC_MODE=args.mode,DRIVESERVE_SPEC_MAX_K=str(args.max_k),
    PYTHONPATH=os.pathsep.join(([str(overlay)] if not args.upstream else [])+[str(root)]))
  for key in ['DRIVESERVE_CACHE_POLICY','DRIVESERVE_LENGTH_AGING','DRIVESERVE_NVTX']:os.environ.pop(key,None)
  if args.trace:os.environ['DRIVESERVE_TRACE_DIR']=str(run.path/'spec-trace')
  else:os.environ.pop('DRIVESERVE_TRACE_DIR',None)
  if not args.upstream:sys.path.insert(0,str(overlay))
  else:
   import importlib.metadata
   wheel=Path(importlib.metadata.distribution('vllm').locate_file('vllm')).resolve()
   for f in lock['lock']['files']:assert file_hash(wheel.parent/f['path'])==f['upstream_sha256']
  from vllm import EngineArgs,LLMEngine,SamplingParams
  kwargs=dict(model=str(args.target),dtype='half',max_model_len=1536,max_num_seqs=4,
    max_num_batched_tokens=1536,num_gpu_blocks_override=512,block_size=16,gpu_memory_utilization=0.5,
    enable_prefix_caching=False,enforce_eager=True,enable_chunked_prefill=False,seed=37,
    disable_async_output_proc=True,disable_log_stats=True)
  if args.mode!='target':kwargs['speculative_config']={'model':str(args.draft),
    'num_speculative_tokens':args.max_k,'draft_tensor_parallel_size':1,'method':'draft_model','disable_logprobs':not bool(args.logprobs),'disable_mqa_scorer':args.batch_expansion}
  engine=LLMEngine.from_engine_args(EngineArgs(**kwargs));tokenizer=engine.get_tokenizer()
  dataset=[json.loads(line) for line in args.dataset.read_text().splitlines()]
  dev=[r for r in dataset if r['split']=='dev'][:args.limit]
  workload=[]
  for i,row in enumerate(dev):
   workload.append({'request_id':f'dev-{i:03d}','kind':'quality','messages':messages(row['scene']),
    'scene':row['scene'],'max_tokens':128,'ignore_eos':False})
  for i,text in enumerate(['Write a numbered checklist for a road trip with 50 detailed entries.',
    'Explain how a hash table handles collisions. Give many examples.',
    'Continue this sequence with one number per line: 1, 2, 3, 4, 5,',
    'Describe the seasons in a long story with dialogue and varied characters.']):
   workload.append({'request_id':f'long-{i}','kind':'synthetic-long',
    'messages':[{'role':'user','content':text}],'max_tokens':128,'ignore_eos':True})
  for n in [1,2,3,5]:
   workload.append({'request_id':f'budget-{n}','kind':'length-boundary',
    'messages':[{'role':'user','content':'List the integers from 1 through 100.'}],
    'max_tokens':n,'ignore_eos':True})
  long_tokens=tokenizer.encode('road dry lane clear speed moderate. '*500)[:1508]
  assert len(long_tokens)==1508
  workload.append({'request_id':'context-limit','kind':'context-boundary','tokens':long_tokens,
    'max_tokens':28,'ignore_eos':True})
  if args.quality_only:workload=[row for row in workload if row['kind']=='quality']
  for row in workload:
   if 'tokens' not in row:row['tokens']=tokenizer.apply_chat_template(row['messages'],tokenize=True,add_generation_prompt=True)
   row['prompt_tokens']=len(row['tokens']);row['seed']=None if args.unseeded else 37
  atomic_json(run.path/'workload.json',workload)
  # Unrelated target/Draft warmup. Reset learned controller state afterwards.
  engine.add_request('warmup',{'prompt_token_ids':tokenizer.encode('Say hello.')},SamplingParams(temperature=0,max_tokens=16,seed=37))
  while engine.has_unfinished_requests():engine.step()
  if args.mode!='target':
   worker=engine.model_executor.driver_worker.worker
   if hasattr(worker,'_driveserve_controller'):
    del worker._driveserve_controller
  results=[];waves=[]
  for start in range(0,len(workload),4):
   # Keep context boundary alone; current workload is 32+4+4+1.
   wave=workload[start:start+4];submitted={};observations={}
   begin=time.perf_counter_ns()
   for row in wave:
    request_id=row['request_id'];submitted[request_id]=time.perf_counter_ns();observations[request_id]=[]
    engine.add_request(request_id,{'prompt_token_ids':row['tokens']},SamplingParams(
      temperature=args.temperature,top_p=1,top_k=-1,max_tokens=row['max_tokens'],ignore_eos=row['ignore_eos'],seed=None if args.unseeded else 37,logprobs=args.logprobs or None))
   steps=0
   while engine.has_unfinished_requests():
    outputs=engine.step();after=time.perf_counter_ns();steps+=1
    if steps>4096:raise RuntimeError('step limit exceeded')
    for output in outputs:
     request_id=output.request_id;generated=output.outputs[0]
     observations[request_id].append({'elapsed_ns':after-submitted[request_id],'tokens':len(generated.token_ids)})
     if output.finished:
      row=next(x for x in wave if x['request_id']==request_id)
      results.append({'request_id':request_id,'status':'completed','elapsed_ns':after-submitted[request_id],
        'output_token_ids':list(generated.token_ids),'text':generated.text,
        'token_logprobs':[{str(t):{'logprob':v.logprob,'rank':v.rank,'decoded_token':v.decoded_token} for t,v in item.items()} for item in generated.logprobs] if generated.logprobs is not None else None,
        'finish_reason':generated.finish_reason,'stop_reason':generated.stop_reason,
        'observations':observations[request_id],
        'quality':score(row['scene'],generated.text) if row['kind']=='quality' else None})
   waves.append({'wave':start//4,'request_ids':[r['request_id'] for r in wave],
     'elapsed_ns':time.perf_counter_ns()-begin,'engine_steps':steps})
   atomic_json(run.path/'results.json',results);atomic_json(run.path/'waves.json',waves)
   print(json.dumps(waves[-1]),flush=True)
  assert len(results)==len(workload)==len({r['request_id'] for r in results})
  by_id={r['request_id']:r for r in results}
  for row in workload:
   got=by_id[row['request_id']]
   assert 0<len(got['output_token_ids'])<=row['max_tokens']
   if row['ignore_eos']:assert len(got['output_token_ids'])==row['max_tokens']
  if args.mode!='target':
   worker=engine.model_executor.driver_worker.worker
   if hasattr(worker,'_driveserve_controller'):
    atomic_json(run.path/'controller-summary.json',worker._driveserve_controller.summary())
  from driveserve.engine_trace import close_traces
  close_traces()
  run.finish('completed',{'requests':len(results),'failed':0,
    'quality_correct':sum(r['quality']['exact_match'] for r in results if r['quality']),
    'quality_total':len(dev),'output_tokens':sum(len(r['output_token_ids']) for r in results),
    'workload_sha256':file_hash(run.path/'workload.json')})
 except BaseException as exc:
  from driveserve.engine_trace import close_traces
  close_traces();run.finish('failed',{'error':str(exc)});raise

if __name__=='__main__':main()
