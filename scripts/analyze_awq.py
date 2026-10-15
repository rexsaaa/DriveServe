"""Reaggregate calibration distortion, inference, and distinct memory budgets."""
import argparse,json,math,statistics,sys
from collections import Counter
from pathlib import Path
sys.path.insert(0,str(Path.cwd()))
from driveserve.evidence import atomic_json,verify_assets,file_hash
from driveserve.task import score
p=argparse.ArgumentParser();p.add_argument('--calibration-runs',nargs='+',type=Path,required=True);p.add_argument('--inference-runs',nargs='+',type=Path,required=True)
p.add_argument('--report',type=Path,required=True);p.add_argument('--timing-eligible',nargs='*',default=[]);args=p.parse_args()
calibrations=[];inferences=[];root=Path.cwd()
for path in args.calibration_runs:
 m=json.load(open(path/'manifest.json'));assert m['status']=='completed';verify_assets(root,m)
 layers=[json.load(open(p)) for p in sorted(path.glob('layer-*.json'))];assert len(layers)==28
 sensitivities=[r for layer in layers for r in layer['sensitivity']];assert len(sensitivities)==21
 assert {r['layer'] for r in sensitivities}=={0,13,27}
 for r in sensitivities:assert math.isclose(r['relative_mse'],r['squared_error_sum']/max(r['reference_squared_sum'],1e-20))
 exported=json.load(open(path/'export.json'));inventory=json.load(open(path/'tensor-inventory.json'))
 dtype_bytes={'F16':2,'BF16':2,'F32':4,'I32':4,'I64':8,'U8':1}
 totals=Counter();families=Counter()
 for t in inventory:
  size=math.prod(t['shape'])*dtype_bytes[t['dtype']];totals[t['dtype']]+=size;families[t['name'].split('.')[-1]]+=size
 group=m['config']['quant_config']['q_group_size'];source=m['config']['source']
 calibrations.append({'run_id':m['run_id'],'code_sha':m['code']['sha'],'source':source,'group_size':group,'export_provenance_sha256':file_hash(path/'export.json'),
  'model_files':exported['files'],'tensor_bytes_by_dtype':dict(totals),'tensor_bytes_by_role':dict(families),
  'safetensors_file_bytes':sum(f['bytes'] for f in exported['files'] if f['path'].endswith('.safetensors')),
  'packed_qweight_tensors':sum(t['name'].endswith('.qweight') for t in inventory),
  'high_precision_nonquantized_weights':[t['name'] for t in inventory if t['name'].endswith('.weight')],
  'tokens':m['config']['calibration']['tokens'],'sensitivity':sensitivities,'mean_relative_mse':statistics.mean(r['relative_mse'] for r in sensitivities),
  'per_layer_mean_relative_mse':{str(i):statistics.mean(r['relative_mse'] for r in sensitivities if r['layer']==i) for i in [0,13,27]},
  'wall_elapsed_layers_s':sum(v['elapsed_s'] for v in layers)})
for path in args.inference_runs:
 m=json.load(open(path/'manifest.json'));assert m['status']=='completed';verify_assets(root,m)
 rows=json.load(open(path/'results.json'));work={r['request_id']:r for r in json.load(open(path/'workload.json'))};waves=json.load(open(path/'waves.json'))
 assert len(rows)==len(work)==137 and m['config']['mode']=='target'
 for row in rows:
  w=work[row['request_id']]
  if w['kind']=='quality':assert row['quality']==score(w['scene'],row['text'])
 final=json.load(open(path/'memory-final.json'));initial=json.load(open(path/'memory-initial.json'))
 config=m['config'].get('target_config') or {'num_hidden_layers':28,'num_key_value_heads':4,'hidden_size':3584,'num_attention_heads':28}
 # The recorded provenance supplies local paths; computation is checked against fixed Qwen config.
 assert config['num_hidden_layers']==28 and config['num_key_value_heads']==4
 bytes_per_token=2*config['num_hidden_layers']*config['num_key_value_heads']*(config['hidden_size']//config['num_attention_heads'])*2
 assert bytes_per_token==57344
 elapsed=sum(w['elapsed_ns'] for w in waves)/1e9;quality=[r for r in rows if work[r['request_id']]['kind']=='quality']
 grouped={}
 for kind in sorted({w['kind'] for w in work.values()}):
  rs=[r for r in rows if work[r['request_id']]['kind']==kind];ttft=[];tpot=[]
  for r in rs:
   first=next(v for v in r['observations'] if v['tokens'])['elapsed_ns']/1e6;ttft.append(first)
   if len(r['output_token_ids'])>1:tpot.append((r['elapsed_ns']/1e6-first)/(len(r['output_token_ids'])-1))
  grouped[kind]={'requests':len(rs),'output_tokens':sum(len(r['output_token_ids']) for r in rs),'mean_ttft_ms':statistics.mean(ttft),'mean_observed_tpot_ms':statistics.mean(tpot) if tpot else None}
 derivation=m['config']['model']['target'].get('derivation',{})
 tensors=json.load(open(path/'live-model-tensors.json')) if (path/'live-model-tensors.json').exists() else None
 record={'live_model_weight_logical_bytes':sum(t['logical_bytes'] for t in tensors if t['weight_related']) if tensors else None,
  'run_id':m['run_id'],'sha':m['code']['sha'],'source':derivation.get('source','fp16'),'group_size':derivation.get('config',{}).get('q_group_size'),
  'quantization':m['config'].get('quantization'),'automatic_kv':m['config'].get('automatic_kv',False),'workload_sha256':file_hash(path/'workload.json'),
  'requests':len(rows),'completed':sum(r['status']=='completed' for r in rows),'quality_correct':sum(r['quality']['exact_match'] for r in quality),'quality_total':len(quality),
  'json_valid':sum(r['quality']['json_valid'] for r in quality),'elapsed_s':elapsed,'output_token_per_s':sum(len(r['output_token_ids']) for r in rows)/elapsed,
  'groups':grouped,'initial_memory':initial,'final_memory':final,'kv_bytes_per_token':bytes_per_token,
  'kv_allocated_bytes':final['actual_gpu_blocks']*final['block_size']*bytes_per_token,
  'kv_token_capacity':final['actual_gpu_blocks']*final['block_size'],'timing_eligible':m['run_id'] in args.timing_eligible}
 if record['timing_eligible']:assert m['config'].get('purpose')=='timing' and (path/'exclusive-gpu-check.json').exists()
 inferences.append(record)
assert len({r['workload_sha256'] for r in inferences})==1
selection={'status':'pending','rule':'docs/awq-protocol.md'}
# Selection uses fixed KV and exclusive timing only, never the concurrent correctness runs.
qualified=[r for r in inferences if not r['automatic_kv'] and r['timing_eligible']]
indexed={(r['source'],r['group_size']):r for r in qualified}
if all(k in indexed for k in [('fp16',None),('general',128),('domain',128),('domain',64)]):
 fp,g,d,d64=[indexed[k] for k in [('fp16',None),('general',128),('domain',128),('domain',64)]]
 selected=('domain',128);reasons=[]
 if d['quality_correct']<g['quality_correct']:selected=('general',128);reasons.append('general has higher dev rule accuracy')
 cm={(r['source'],r['group_size']):r for r in calibrations}
 ratio=cm[('domain',64)]['mean_relative_mse']/cm[('domain',128)]['mean_relative_mse']
 recovery=d['quality_correct']<fp['quality_correct'] and d64['quality_correct']>=fp['quality_correct']
 error_benefit=ratio<=.75 and d64['output_token_per_s']>=.95*d['output_token_per_s']
 if (recovery or error_benefit) and d64['quality_correct']>=indexed[selected]['quality_correct']:
  selected=('domain',64);reasons.append('restores FP16 accuracy' if recovery else 'at least25% lower local MSE with at most5% timing regression')
 selection={'status':'initial_candidate','rule':'docs/awq-protocol.md','source':selected[0],'group_size':selected[1],
  'reasons':reasons or ['default domain128 retained'],'domain64_to128_mean_relative_mse_ratio':ratio,
  'fp16_correct':fp['quality_correct'],'candidate_correct':indexed[selected]['quality_correct'],
  'release_default':'FP16 until stage3 quality threshold/repeats and stage5 integration','single_observation_only':True}
atomic_json(args.report,{'calibration':calibrations,'inference':inferences,'selection':selection,
 'limitations':['local MSE is on calibration inputs; general/domain probe distributions differ so their local errors are not a held-out causal comparison',
 'group64/group128 domain probes share layer-depth/input sampling recipe; full-model activation changes can affect later-layer features',
 'native awq selected explicitly; no AWQ-Marlin performance claim unless separate run provided',
 'fixedKV and total fraction capacity are separate experiments; torch allocated/reserved and nvidia-smi totals not interchangeable',
 'host GPU process PID can differ from container PID; GPU process listing is raw evidence, not automatically attributed to this process',
 '137 synthetic requests; no final-test access, no stable P99 or general speedup claim']})
print(json.dumps({'report':str(args.report),'inference':[{k:r[k] for k in ['run_id','source','group_size','automatic_kv','quality_correct','output_token_per_s','kv_token_capacity','timing_eligible']} for r in inferences],'selection':selection},indent=2))
