"""Matched open-loop HTTP deployments with immutable trajectories and all-attempt SLOs."""
import argparse,asyncio,http.client,json,os,random,signal,socket,subprocess,sys,time
from pathlib import Path
sys.path.insert(0,str(Path.cwd()))
from driveserve.evidence import Run,atomic_json,file_hash,process_identity,now
from driveserve.task import messages,digest
from driveserve.openloop import run_arrivals
from driveserve.openloop_stats import summarize

p=argparse.ArgumentParser();p.add_argument('--deployment',choices=['single','replica','tp2'],required=True)
p.add_argument('--protocol',type=Path,required=True);p.add_argument('--repeat',type=int,default=0)
p.add_argument('--python',default='/hy-tmp/driveserve/venv-rebuilt/bin/python');a=p.parse_args()
protocol=json.loads(a.protocol.read_text());assert protocol['stage']=='S5'
root=Path.cwd();data=Path(protocol['data']['path']);assert file_hash(data)==protocol['data']['sha256']
rows=[json.loads(line) for line in data.read_text().splitlines()];assert len(rows)==128 and all(r['split']=='dev' for r in rows)
assert protocol['requests_per_cell']>0 and protocol['requests_per_cell']<=1024
initial=subprocess.check_output(['nvidia-smi','--query-gpu=index,memory.used','--format=csv,noheader,nounits'],text=True)
assert all(int(line.split(',')[1])<100 for line in initial.strip().splitlines()),'requires both GPUs idle'
model=Path(protocol['model']);provenance=json.load(open(model/'driveserve-provenance.json'))
for f in provenance['files']:assert file_hash(model/Path(f['path']).name)==f['sha256']
from transformers import AutoTokenizer
tokenizer=AutoTokenizer.from_pretrained(model,local_files_only=True)
workloads={};padding=tokenizer.encode(' background',add_special_tokens=False);assert len(padding)==1
for kind in protocol['workloads']:
 records=[];order=list(range(len(rows)));random.Random(protocol['seed']).shuffle(order)
 for i in range(protocol['requests_per_cell']):
  row=rows[order[i%len(order)]]
  natural=tokenizer.apply_chat_template(messages(row['scene']),tokenize=True,add_generation_prompt=True)
  target_length=None if kind=='natural' else [512,1536][i%2]
  assert kind in ['natural','mixed-padding']
  tokens=natural if target_length is None else padding*(target_length-len(natural))+natural
  assert target_length is None or len(tokens)==target_length
  records.append(dict(request_id=f'{kind}-{i:04d}',scene=row['scene'],split='dev',tokens=tokens,
     prompt_sha256=digest(tokens),natural_prompt_tokens=len(natural),prompt_tokens=len(tokens),
     padding_tokens=len(tokens)-len(natural),source_index=order[i%len(order)],group='natural' if target_length is None else str(target_length)))
 workloads[kind]=records
trajectories={}
for rate in protocol['rates']:
 randomizer=random.Random(protocol['seed']+int(rate*100));offsets=[0.]
 for _ in range(protocol['requests_per_cell']-1):offsets.append(offsets[-1]+randomizer.expovariate(rate))
 trajectories[str(rate)]=dict(offsets_s=offsets,arrival_window_s=offsets[-1]+1/rate)
services=[('0',1,8081,8)] if a.deployment=='single' else [('0',1,8081,4),('1',1,8082,4)] if a.deployment=='replica' else [('0,1',2,8081,8)]
config=dict(stage='S5',purpose=protocol['purpose'],repeat=a.repeat,requirement_ids=['M1-03','M6-03','M6-04'],
 hypothesis='independent offered arrivals expose queueing/quality tradeoffs under matched two-GPU deployments',
 model=provenance,data=protocol['data'],deployment=a.deployment,protocol=protocol,
 protocol_file=dict(path=str(a.protocol),sha256=file_hash(a.protocol)),initial_gpu_usage=initial,
 service_budget=dict(global_max_num_seqs=8,gpu_memory_utilization_per_gpu=.45,max_model_len=2048,
  prefix_cache=protocol['prefix_cache'],chunked_prefill=False,graph=True,backend='FLASH_ATTN version 2 V0',disable_custom_all_reduce=True),
 routing='request ordinal modulo replica count; no prefix affinity; max_inflight applies globally',
 limitations=['SSE content chunks can group tokens; TPOT is request average, not per-token ITL.',
 'Natural dev128 repeats are not final held-out quality and P99 is exploratory at this sample budget.',
 'Synthetic padding is separate; shared padding prefixes can be reused when APC is enabled.',
 'Single GPU efficiency is separate from the equal two-GPU replica/TP2 budget; automatic KV capacity is not forced equal.',
 'All failures and drain time retained; engineering SLOs are not a real vehicle deadline guarantee.'])
run=Run(root,'deployment-openloop',config,formal=True);print(run.path,flush=True)
atomic_json(run.path/'workloads.json',workloads);atomic_json(run.path/'trajectories.json',trajectories)
processes=[];logs=[]
def gpu():
 return subprocess.check_output(['nvidia-smi','--query-gpu=index,uuid,memory.used,utilization.gpu,temperature.gpu,power.draw,power.limit,clocks.current.sm,clocks.current.memory','--format=csv'],text=True)
def stop_servers():
 for child in processes:
  try:os.killpg(child.pid,signal.SIGTERM)
  except ProcessLookupError:pass
 for child in processes:
  try:child.wait(timeout=20)
  except subprocess.TimeoutExpired:
   try:os.killpg(child.pid,signal.SIGKILL)
   except ProcessLookupError:pass
   child.wait(timeout=10)
  try:os.killpg(child.pid,signal.SIGKILL)
  except ProcessLookupError:pass
 for stream in logs:stream.close()
 processes.clear();logs.clear()
def interrupt(*_):raise KeyboardInterrupt('SIGTERM')
signal.signal(signal.SIGTERM,interrupt)
def request_control(port,path):
 conn=http.client.HTTPConnection('127.0.0.1',port,timeout=10)
 try:
  conn.request('POST',path);response=conn.getresponse();body=response.read();assert response.status==200,(response.status,body)
 finally:conn.close()
try:
 for devices,tp,port,maxseq in services:
  with socket.socket() as probe:probe.bind(('127.0.0.1',port))
  command=[a.python,'-m','vllm.entrypoints.openai.api_server','--model',str(model),'--served-model-name','driveserve-deployment',
   '--host','127.0.0.1','--port',str(port),'--tensor-parallel-size',str(tp),'--dtype','half','--max-model-len','2048',
   '--max-num-seqs',str(maxseq),'--max-num-batched-tokens','2048','--gpu-memory-utilization','.45',
   '--enable-prefix-caching' if protocol['prefix_cache'] else '--no-enable-prefix-caching','--no-enable-chunked-prefill',
   '--disable-custom-all-reduce','--disable-log-requests','--seed','37']
  env={**os.environ,'CUDA_VISIBLE_DEVICES':devices,'VLLM_USE_V1':'0','VLLM_ATTENTION_BACKEND':'FLASH_ATTN','VLLM_FLASH_ATTN_VERSION':'2',
       'HF_HUB_OFFLINE':'1','TRANSFORMERS_OFFLINE':'1','VLLM_WORKER_MULTIPROC_METHOD':'spawn'}
  for key in list(env):
   if key=='PYTHONPATH' or key.startswith('DRIVESERVE_'):env.pop(key,None)
  stream=(run.path/f'server-{port}.log').open('w',buffering=1);logs.append(stream)
  child=subprocess.Popen(command,env=env,stdout=stream,stderr=subprocess.STDOUT,start_new_session=True);processes.append(child)
  run.manifest.setdefault('services',[]).append(dict(argv=command,devices=devices,process=process_identity(child.pid),process_group=child.pid));run.save()
 deadline=time.monotonic()+300
 for child,(_,_,port,_) in zip(processes,services):
  while True:
   if child.poll() is not None:raise RuntimeError('service exited before readiness')
   if time.monotonic()>deadline:raise TimeoutError('service readiness timeout')
   connection=http.client.HTTPConnection('127.0.0.1',port,timeout=2)
   try:
    connection.request('GET','/health');response=connection.getresponse();ready=response.status==200;response.read()
   except (OSError,http.client.HTTPException):ready=False
   finally:connection.close()
   if ready:break
   run.manifest['heartbeat_at']=now();run.save();time.sleep(1)
 for _,_,port,_ in services:
  log=(run.path/f'server-{port}.log').read_text()
  assert f"enable_prefix_caching={protocol['prefix_cache']}" in log and 'chunked_prefill_enabled=False' in log and 'enforce_eager=False' in log
 atomic_json(run.path/'ready-gpu.json',dict(query=gpu()))
 endpoints=[f'http://127.0.0.1:{s[2]}/v1' for s in services]
 summaries=[]
 cells=[(kind,rate) for kind in protocol['workloads'] for rate in protocol['rates']]
 if a.repeat%2==0:cells.reverse()
 for kind,rate in cells:
  warm=[dict(row,request_id='warm-'+str(i)) for i,row in enumerate(workloads[kind][:4])]
  warm_result=asyncio.run(run_arrivals(warm,[0]*len(warm),endpoints,'driveserve-deployment',max_inflight=4,timeout_s=30,max_tokens=protocol['max_tokens']))
  assert all(r['status']=='completed' for r in warm_result['records'])
  if protocol['prefix_cache']:
   reset_evidence=[]
   for _,_,port,_ in services:
    log_path=run.path/f'server-{port}.log';before=len(log_path.read_text())
    request_control(port,'/reset_prefix_cache')
    new_log=log_path.read_text()[before:]
    assert 'Successfully reset prefix cache' in new_log and 'Failed to reset prefix cache' not in new_log,new_log
    reset_evidence.append(dict(port=port,log_excerpt=new_log))
   atomic_json(run.path/f'{kind}-r{rate}-cache-reset.json',reset_evidence)
  label=f'{kind}-r{rate}';atomic_json(run.path/(label+'-warmup.json'),warm_result)
  atomic_json(run.path/(label+'-gpu-before.json'),dict(query=gpu()))
  with (run.path/(label+'-requests.jsonl')).open('w',buffering=1) as stream:
   def persist(row):
    stream.write(json.dumps(row,ensure_ascii=False,allow_nan=False)+'\n');stream.flush()
   trajectory=trajectories[str(rate)]
   result=asyncio.run(run_arrivals(workloads[kind],trajectory['offsets_s'],endpoints,'driveserve-deployment',
      max_inflight=protocol['max_inflight'],timeout_s=protocol['timeout_s'],max_tokens=protocol['max_tokens'],on_result=persist))
   stream.flush();os.fsync(stream.fileno())
  assert len(result['records'])==protocol['requests_per_cell']
  measurement=dict(epoch_ns=result['epoch_ns'],finished_ns=result['finished_ns'],arrival_window_s=trajectory['arrival_window_s'])
  atomic_json(run.path/(label+'-measurement.json'),measurement)
  summary=summarize(result['records'],result['epoch_ns'],trajectory['arrival_window_s'],protocol['slo'][kind])
  summary.update(workload=kind,nominal_rate=rate,repeat=a.repeat,deployment=a.deployment)
  atomic_json(run.path/(label+'-summary.json'),summary);summaries.append(summary)
  atomic_json(run.path/(label+'-gpu-after.json'),dict(query=gpu()))
  run.manifest.update(heartbeat_at=now(),completed_cells=len(summaries));run.save()
  print(json.dumps(dict(cell=label,success=summary['success'],requests=summary['requests'],goodput=summary['slo_goodput_per_s'],quality=summary['quality_correct'],send_lag=summary['send_lag_s'])),flush=True)
 stop_servers();run.finish('completed',dict(cells=len(summaries),requests=sum(s['requests'] for s in summaries),success=sum(s['success'] for s in summaries),
   interpretation='experiment completed; request failures/timeouts/cancellations if any remain in summaries'))
except BaseException as exc:
 stop_servers();run.finish('interrupted' if isinstance(exc,KeyboardInterrupt) else 'failed',dict(error=str(exc)));raise
