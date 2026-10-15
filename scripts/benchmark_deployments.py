"""Matched HTTP deployment comparison: one GPU, two replicas, and TP2."""
import argparse,http.client,json,os,signal,socket,subprocess,sys,time
from concurrent.futures import ThreadPoolExecutor,as_completed
from pathlib import Path
sys.path.insert(0,str(Path.cwd()))
from driveserve.evidence import Run,atomic_json,file_hash,process_identity,now
from driveserve.task import messages,score,digest
from driveserve.benchmark import aggregate
p=argparse.ArgumentParser();p.add_argument('--deployment',choices=['single','replica','tp2'],required=True)
p.add_argument('--stage',choices=['S2','S3','S5'],default='S2');p.add_argument('--repeat',type=int,default=0)
p.add_argument('--fault-checks',action='store_true',help='real HTTP errors before timed warmup')
p.add_argument('--diagnose-quality',action='store_true',help='non-timed logprob diagnostics for long-padding dev-030')
p.add_argument('--python',default='/hy-tmp/driveserve/venv-rebuilt/bin/python');args=p.parse_args()
idle_gpu=subprocess.check_output(['nvidia-smi','--query-gpu=index,memory.used','--format=csv,noheader,nounits'],text=True)
assert all(int(line.split(',')[1].strip())<100 for line in idle_gpu.strip().splitlines()),'matched deployment timings require both GPUs idle'
model=Path('/hy-tmp/driveserve/models/target');provenance=json.load(open(model/'driveserve-provenance.json'))
for f in provenance['files']:assert file_hash(model/Path(f['path']).name)==f['sha256']
from transformers import AutoTokenizer
tokenizer=AutoTokenizer.from_pretrained(model,local_files_only=True)
data=Path('data/frozen-v1/dev.jsonl');rows=[json.loads(line) for line in data.read_text().splitlines()][:64]
assert len(rows)==64 and all(r['split']=='dev' for r in rows)
workloads={};padding=tokenizer.encode(' background',add_special_tokens=False);assert len(padding)==1
for length in [512,1536]:
 workloads[length]=[]
 for i,row in enumerate(rows):
  prompt=tokenizer.apply_chat_template(messages(row['scene']),tokenize=True,add_generation_prompt=True)
  assert len(prompt)<length
  tokens=padding*(length-len(prompt))+prompt
  workloads[length].append({'request_id':f'dev-{i:03d}','scene':row['scene'],'split':'dev','tokens':tokens,'prompt_sha256':digest(tokens)})
services=[('0',1,8081,8)] if args.deployment=='single' else [('0',1,8081,4),('1',1,8082,4)] if args.deployment=='replica' else [('0,1',2,8081,8)]
config={'stage':args.stage,'repeat':args.repeat,'purpose':'quality-diagnostic' if args.diagnose_quality else 'timing','fault_checks':args.fault_checks,'requirement_ids':['M6-03','M6-04'],'hypothesis':'relative deployment behavior depends on prompt length and offered closed-loop concurrency',
 'model':provenance,'deployment':args.deployment,'data':{'path':str(data),'sha256':file_hash(data),'split':'dev','selected':64},
 'prompt_lengths':[512,1536],'global_concurrency':[1,8],'requests_per_cell':64,'max_output_tokens':64,'temperature':0,'seed':37,
 'routing':'stable index modulo replica count; global thread pool, no prefix affinity','arrival':'closed loop, no fixed offered requests/s',
 'service_budget':{'gpu_memory_utilization_per_gpu':.45,'global_max_num_seqs':8,'max_model_len':2048,'graph':True,'prefix_cache':False,
 'chunked_prefill':False,'disable_custom_all_reduce':True,'backend':'FLASH_ATTN version 2, V0'},
 'warmup':'4 requests per cell, modulo endpoints; excluded from timing and quality denominator',
 'limitations':['single observation per cell; P99 nearest-rank from 64 requests is exploratory','synthetic padding before chat; actual lengths and quality measured',
 'single uses one GPU, replica and TP2 use same two physical GPUs; no shared total-KV-token constraint',
 'no NVLink, custom all-reduce off; physical 24GB environment not tested']}
run=Run(Path.cwd(),'deployment-matrix',config,formal=True);print(run.path,flush=True)
atomic_json(run.path/'workloads.json',workloads)
processes=[];logs=[]
def stop_servers():
 for child in processes:
  try:os.killpg(child.pid,signal.SIGTERM)
  except ProcessLookupError:continue
 for child in processes:
  try:child.wait(timeout=20)
  except subprocess.TimeoutExpired:
   try:os.killpg(child.pid,signal.SIGKILL)
   except ProcessLookupError:pass
   child.wait(timeout=10)
 for child in processes:
  try:os.killpg(child.pid,signal.SIGKILL)
  except ProcessLookupError:pass
 for stream in logs:stream.close()
 processes.clear();logs.clear()
def interrupt(*a):raise KeyboardInterrupt('SIGTERM')
signal.signal(signal.SIGTERM,interrupt)
def send(index,record):
 replica=index%len(services);port=services[replica][2]
 row={'scene_id':record['scene']['scene_id'],'request_id':record['request_id'],'split':'dev','replica':replica,
 'prompt_sha256':record['prompt_sha256'],'status':'failed','error':None,'chunks':[],'text':'','completion_tokens':None,'prompt_tokens':None,
 'ttft_s':None,'tpot_s':None,'finish_reason':None,'sent_at':now()}
 start=time.perf_counter();connection=http.client.HTTPConnection('127.0.0.1',port,timeout=120)
 try:
  body={'model':'driveserve-deployment','prompt':record['tokens'],'temperature':0,'seed':37,'max_tokens':64,'stream':True,'stream_options':{'include_usage':True}}
  connection.request('POST','/v1/completions',body=json.dumps(body),headers={'Content-Type':'application/json'})
  response=connection.getresponse()
  if response.status!=200:raise RuntimeError(f'HTTP {response.status}: '+response.read(1024).decode(errors='replace'))
  done=False
  while True:
   remaining=120-(time.perf_counter()-start)
   if remaining<=0:raise TimeoutError('whole request deadline')
   if connection.sock:connection.sock.settimeout(remaining)
   line=response.readline(1024*1024)
   if not line:break
   if not line.startswith(b'data:'):continue
   payload=line[5:].strip()
   if payload==b'[DONE]':done=True;break
   if not payload:continue
   event=json.loads(payload);elapsed=time.perf_counter()-start
   row['chunks'].append({'offset_s':elapsed,'event':event})
   if 'error' in event:raise RuntimeError(str(event['error']))
   for choice in event.get('choices',[]):
    text=choice.get('text') or ''
    if text:
     row['text']+=text
     if row['ttft_s'] is None:row['ttft_s']=elapsed
     row['last_content_s']=elapsed
    if choice.get('finish_reason') is not None:row['finish_reason']=choice['finish_reason']
   if event.get('usage'):
    row['prompt_tokens']=event['usage']['prompt_tokens'];row['completion_tokens']=event['usage']['completion_tokens']
  assert done and row['finish_reason'] and row['ttft_s'] is not None
  assert row['prompt_tokens']==len(record['tokens']) and 0<row['completion_tokens']<=64
  row['status']='completed'
  if row['completion_tokens']>1:row['tpot_s']=(row['last_content_s']-row['ttft_s'])/(row['completion_tokens']-1)
 except Exception as exc:
  row['status']='timeout' if isinstance(exc,TimeoutError) else 'failed';row['error']=str(exc)
 finally:row['e2e_s']=time.perf_counter()-start;connection.close()
 row['quality']=score(record['scene'],row['text']);return row
try:
 for devices,tp,port,maxseq in services:
  with socket.socket() as probe:probe.bind(('127.0.0.1',port))
  command=[args.python,'-m','vllm.entrypoints.openai.api_server','--model',str(model),'--served-model-name','driveserve-deployment',
   '--host','127.0.0.1','--port',str(port),'--tensor-parallel-size',str(tp),'--dtype','half','--max-model-len','2048',
   '--max-num-seqs',str(maxseq),'--max-num-batched-tokens','2048','--gpu-memory-utilization','.45',
   '--no-enable-prefix-caching','--no-enable-chunked-prefill',
   '--disable-custom-all-reduce','--disable-log-requests','--seed','37']
  env={**os.environ,'CUDA_VISIBLE_DEVICES':devices,'VLLM_USE_V1':'0','VLLM_ATTENTION_BACKEND':'FLASH_ATTN','VLLM_FLASH_ATTN_VERSION':'2',
       'HF_HUB_OFFLINE':'1','TRANSFORMERS_OFFLINE':'1','VLLM_WORKER_MULTIPROC_METHOD':'spawn'}
  for key in ['PYTHONPATH','DRIVESERVE_SPEC_MODE','DRIVESERVE_TRACE_DIR','DRIVESERVE_CACHE_POLICY','DRIVESERVE_LENGTH_AGING']:env.pop(key,None)
  stream=(run.path/f'server-{port}.log').open('w',buffering=1);logs.append(stream)
  child=subprocess.Popen(command,env=env,stdout=stream,stderr=subprocess.STDOUT,start_new_session=True);processes.append(child)
  run.manifest.setdefault('services',[]).append({'argv':command,'devices':devices,'process':process_identity(child.pid),'process_group':child.pid});run.save()
 deadline=time.monotonic()+300
 for child,(_,_,port,_) in zip(processes,services):
  while True:
   if child.poll() is not None:raise RuntimeError('service exited before health check')
   if time.monotonic()>deadline:raise TimeoutError('service readiness timeout')
   connection=http.client.HTTPConnection('127.0.0.1',port,timeout=2)
   try:
    connection.request('GET','/health');response=connection.getresponse();ready=response.status==200;response.read()
   except (OSError,http.client.HTTPException):ready=False
   finally:connection.close()
   if ready:break
   run.manifest['heartbeat_at']=now();run.save();time.sleep(1)
 for _,_,port,_ in services:
  text=(run.path/f'server-{port}.log').read_text()
  assert 'enable_prefix_caching=False' in text and 'chunked_prefill_enabled=False' in text and 'enforce_eager=False' in text
 atomic_json(run.path/'ready-gpu-memory.json',{'query':subprocess.check_output(['nvidia-smi','--query-gpu=index,uuid,memory.used,utilization.gpu','--format=csv'],text=True)})
 if args.fault_checks:
  from driveserve.benchmark import request as chat_request
  faults=[]
  for label,model_name,max_tokens in [('unknown-model','driveserve-missing-boundary',64),('invalid-length','driveserve-deployment',-1),('context-overflow','driveserve-deployment',4096)]:
   row=chat_request('http://127.0.0.1:8081/v1',model_name,rows[0],timeout=10,max_tokens=max_tokens)
   assert row['status']=='failed' and row['error'],(label,row)
   faults.append({'case':label,'request':row})
  atomic_json(run.path/'http-faults.json',faults)
  assert send(0,workloads[512][0])['status']=='completed','service did not recover after invalid requests'
 if args.diagnose_quality:
  assert args.deployment in ['single','tp2']
  def diagnostic(tokens,budget):
   connection=http.client.HTTPConnection('127.0.0.1',8081,timeout=120)
   body={'model':'driveserve-deployment','prompt':tokens,'temperature':0,'seed':37,'max_tokens':budget,'stream':False,'logprobs':5,'return_tokens_as_token_ids':True}
   try:
    connection.request('POST','/v1/completions',body=json.dumps(body),headers={'Content-Type':'application/json'})
    response=connection.getresponse();result=json.loads(response.read());assert response.status==200,result
   finally:connection.close()
   return {'body':body,'response':result}
  diagnostics=[]
  for i in range(4):assert send(i,workloads[1536][i])['status']=='completed'
  for i in [29,30,31]:
   record=workloads[1536][i];result=diagnostic(record['tokens'],64)
   result.update(request_id=record['request_id'],scene=record['scene'],quality=score(record['scene'],result['response']['choices'][0]['text']))
   diagnostics.append(result);atomic_json(run.path/'quality-diagnostics.json',diagnostics)
  # Replay a common prefix from the two *retained* S2 outputs. This is a new
  # prefill shape, so report separately from full-generation decode logprobs.
  refs=[]
  for rid in ['20261015T113913+0800-03587d84d8','20261015T114325+0800-e6bdc12c1f']:
   old=[json.loads(l) for l in (Path('experiments/runs')/rid/'p1536-c1-requests.jsonl').read_text().splitlines()]
   refs.append(tokenizer.encode(next(r['text'] for r in old if r['request_id']=='dev-030'),add_special_tokens=False))
  different=next(i for i,(a,b) in enumerate(zip(*refs)) if a!=b);prefix=refs[0][:different];assert prefix==refs[1][:different]
  result=diagnostic(workloads[1536][30]['tokens']+prefix,1);result.update(prefix_ids=prefix,s2_next_ids=[a[different] for a in refs],limitation='common-prefix one-step prefill; not the same kernel shape as iterative decode')
  atomic_json(run.path/'common-prefix-diagnostic.json',result)
 summaries=[]
 for length in ([] if args.diagnose_quality else [512,1536]):
  for concurrency in [1,8]:
   for i in range(4):assert send(i,workloads[length][i])['status']=='completed'
   label=f'p{length}-c{concurrency}';records=[];begin=time.perf_counter_ns()
   with (run.path/(label+'-requests.jsonl')).open('w',buffering=1) as log:
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
     futures=[pool.submit(send,i,row) for i,row in enumerate(workloads[length])]
     for future in as_completed(futures):
      row=future.result();records.append(row);log.write(json.dumps(row,ensure_ascii=False)+'\n');log.flush();os.fsync(log.fileno())
   end=time.perf_counter_ns();summary=aggregate(records,(end-begin)/1e9)
   summary.update(prompt_length=length,concurrency=concurrency,started_ns=begin,finished_ns=end,
                  per_replica={str(i):sum(r['replica']==i for r in records) for i in range(len(services))})
   atomic_json(run.path/(label+'-summary.json'),summary);summaries.append(summary)
   run.manifest['heartbeat_at']=now();run.manifest['completed_cells']=len(summaries);run.save()
   assert summary['success']==64
 stop_servers();run.finish('completed',{'diagnostic_requests':4,'timing_eligible':False} if args.diagnose_quality else {'cells':4,'requests':256,'success':sum(s['success'] for s in summaries)})
except BaseException as exc:
 stop_servers();run.finish('interrupted' if isinstance(exc,KeyboardInterrupt) else 'failed',{'error':str(exc)});raise
