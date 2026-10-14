"""Freeze teacher outputs with rule-based eligibility and resumable per-batch state."""
import argparse,fcntl,json,os,signal,sys
from pathlib import Path
sys.path.insert(0,str(Path.cwd()))
from driveserve.evidence import Run,atomic_json,file_hash
from driveserve.task import messages,score,digest
p=argparse.ArgumentParser()
p.add_argument('--data',type=Path,required=True)
p.add_argument('--state',type=Path,required=True)
p.add_argument('--model',type=Path,default=Path('/hy-tmp/driveserve/models/target'))
args=p.parse_args();root=Path.cwd();args.state.mkdir(parents=True,exist_ok=True)
lock=(args.state/'.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
manifest=json.load(open(args.data/'manifest.json'))
source=[]
for split in ['train','dev']:
 path=args.data/(split+'.jsonl');assert file_hash(path)==manifest['files'][split]['sha256']
 rows=[json.loads(line) for line in path.read_text().splitlines()];assert all(r['split']==split for r in rows)
 source.extend(rows)
provenance=json.load(open(args.model/'driveserve-provenance.json'))
for f in provenance['files']:assert file_hash(args.model/Path(f['path']).name)==f['sha256']
config={'stage':'S2','requirement_ids':['M3-04'],'hypothesis':'frozen target provides sequence-level teacher labels, separately checked by independent oracle',
 'model':provenance,'data':manifest,'temperature':0,'seed':37,'max_tokens':128,'batch_size':16,
 'dtype':'float16','prefix_caching':False,'eager':True,
 'training_filter':'train only: valid JSON AND all oracle fields correct AND natural stop; preserve excluded records',
 'limitations':['teacher generation is not distillation training','synthetic proxy task only; final test not loaded']}
identity=digest(config)
state_path=args.state/'state.json'
if state_path.exists():
 state=json.load(open(state_path));assert state['identity']==identity
 assert state['records_sha256']==digest(state['records'])
else:state={'identity':identity,'next_index':0,'records':[],'records_sha256':digest([])}
assert state['next_index']==len(state['records'])
for i,row in enumerate(state['records']):assert row['scene_id']==source[i]['scene']['scene_id']
run=Run(root,'teacher-generation',config,formal=True,previous_run_id=state.get('last_run'))
print(run.path,flush=True)
stop=[False]
signal.signal(signal.SIGTERM,lambda *a:stop.__setitem__(0,True))
try:
 os.environ.update(VLLM_USE_V1='0',VLLM_ATTENTION_BACKEND='FLASH_ATTN',CUDA_VISIBLE_DEVICES='0',HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1')
 for key in ['DRIVESERVE_TRACE_DIR','DRIVESERVE_SPEC_MODE','DRIVESERVE_CACHE_POLICY','DRIVESERVE_LENGTH_AGING']:os.environ.pop(key,None)
 from vllm import LLM,SamplingParams
 model=LLM(model=str(args.model),dtype='half',max_model_len=1024,max_num_seqs=16,
   max_num_batched_tokens=8192,gpu_memory_utilization=.5,num_gpu_blocks_override=1024,
   enable_prefix_caching=False,enforce_eager=True,seed=37,disable_log_stats=True)
 tokenizer=model.get_tokenizer()
 params=SamplingParams(temperature=0,max_tokens=128,seed=37)
 for start in range(state['next_index'],len(source),16):
  chunk=source[start:start+16]
  inputs=[tokenizer.apply_chat_template(messages(r['scene']),tokenize=True,add_generation_prompt=True) for r in chunk]
  outputs=model.generate([{'prompt_token_ids':tokens} for tokens in inputs],params,use_tqdm=False)
  assert len(outputs)==len(chunk)
  for record,tokens,out in zip(chunk,inputs,outputs):
   completion=out.outputs[0];quality=score(record['scene'],completion.text)
   reasons=[]
   if not quality['json_valid']:reasons.append('invalid_json')
   if not quality['exact_match']:reasons.append('oracle_mismatch')
   if completion.finish_reason!='stop':reasons.append('not_natural_stop')
   state['records'].append({'scene_id':record['scene']['scene_id'],'split':record['split'],
    'prompt_tokens':tokens,'completion_tokens':list(completion.token_ids),'completion_text':completion.text,
    'finish_reason':completion.finish_reason,'quality':quality,'filter_reasons':reasons,
    'train_eligible':record['split']=='train' and not reasons})
  state.update(next_index=len(state['records']),records_sha256=digest(state['records']),last_run=run.manifest['run_id'])
  atomic_json(state_path,state)
  run.manifest['checkpoint']={'path':str(state_path),'sha256':file_hash(state_path),'next_index':state['next_index']};run.save()
  print(json.dumps({'completed':state['next_index'],'total':len(source),'eligible_train':sum(r['train_eligible'] for r in state['records'])}),flush=True)
  if stop[0]:break
 atomic_json(run.path/'teacher-summary.json',{'state_path':str(state_path),'state_sha256':file_hash(state_path),
  'completed':state['next_index'],'total':len(source),'train_eligible':sum(r['train_eligible'] for r in state['records']),
  'filtered_train':sum(r['split']=='train' and not r['train_eligible'] for r in state['records'])})
 run.finish('completed' if state['next_index']==len(source) else 'interrupted',{'records':state['next_index'],'state_sha256':file_hash(state_path)})
 if state['next_index']!=len(source):sys.exit(75)
except BaseException as exc:
 if run.manifest['status']=='running':run.finish('failed',{'error':str(exc)})
 raise
