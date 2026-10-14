"""Run upstream AWQ with recorded calibration and representative linear sensitivity."""
import argparse,json,os,signal,sys,time
from pathlib import Path
sys.path.insert(0,str(Path.cwd()))
from driveserve.evidence import Run,atomic_json,file_hash,now
p=argparse.ArgumentParser();p.add_argument('--data',type=Path,required=True);p.add_argument('--source',choices=['general','domain'],required=True)
p.add_argument('--group',type=int,choices=[64,128],required=True);p.add_argument('--destination',type=Path,required=True)
p.add_argument('--layer',type=Path,default=Path('/hy-tmp/driveserve/awq-deps-v2'));p.add_argument('--gpu',default='0');args=p.parse_args()
if args.destination.exists():raise ValueError('immutable quantized destination already exists')
os.environ.update(CUDA_VISIBLE_DEVICES=args.gpu,HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',TOKENIZERS_PARALLELISM='false')
sys.path[:0]=[str(args.layer.resolve()),'/hy-tmp/driveserve/training-deps-v1']
import torch
from awq import AutoAWQForCausalLM
from awq.quantize.quantizer import AwqQuantizer
from transformers import AutoTokenizer
torch.set_num_threads(4);torch.manual_seed(3702);torch.cuda.manual_seed_all(3702)
target=Path('/hy-tmp/driveserve/models/target');base=json.load(open(target/'driveserve-provenance.json'))
for item in base['files']:assert file_hash(target/Path(item['path']).name)==item['sha256']
manifest=json.load(open(args.data/'calibration-manifest.json'));entry=manifest['files'][args.source]
calib_path=args.data/Path(entry['path']).name;assert file_hash(calib_path)==entry['sha256']
blocks=json.load(open(calib_path));assert len(blocks)==32 and all(len(b)==512 for b in blocks)
quant_config={'zero_point':True,'q_group_size':args.group,'w_bit':4,'version':'GEMM'}
config={'stage':'S2','requirement_ids':['M4-01','M4-02','M4-03','M4-04','M4-05'],
 'hypothesis':'calibration source and group size change actual W4A16 output error, deployment quality and memory',
 'model':base,'data':manifest,'source':args.source,'quant_config':quant_config,'seed':3702,'gpu':args.gpu,
 'layer_manifest':json.load(open(args.layer/'driveserve-awq-layer.json')),
 'calibration':{'tokens':16384,'blocks':32,'length':512,'parallel_samples':4,'duo_scaling':True,'apply_clip':True},
 'sensitivity':{'layers':[0,13,27],'linear_modules':'all attention/MLP linears in each selected block','tokens_per_linear':256,
 'reference':'post-AWQ scale, before clipping and quantization; FP32 matmul on fixed strided calibration inputs',
 'metric':'sum((XW-XQW)^2)/sum((XW)^2), zero-reference guarded; includes weight clipping error',
 'limitation':'local linear output distortion on calibration inputs; not end-to-end task effect or held-out error'},
 'limitations':['AutoAWQ supplies scale search/clip/packing; project supplies data, controlled sweeps and sensitivity recording',
 'unit of restart is one complete model calibration; per-layer progress is not a resumable AWQ model checkpoint',
 'embedding, lm_head, norm and bias remain high precision; no whole-model 4bit claim']}
run=Run(Path.cwd(),'awq-calibration-export',config,formal=True);print(run.path,flush=True)
stop=[False];signal.signal(signal.SIGTERM,lambda *a:stop.__setitem__(0,True))
class ObservedQuantizer(AwqQuantizer):
 def _get_input_feat(self,layer,named_linears):
  self.observed_layer=next(i for i,m in enumerate(self.modules) if m is layer)
  self.before_layer=time.perf_counter();self.features=super()._get_input_feat(layer,named_linears)
  return self.features
 def _search_best_clip(self,layer,named_linears,input_feat):
  self.unclipped={name:linear.weight.detach().cpu().clone() for name,linear in named_linears.items()} if self.observed_layer in [0,13,27] else {}
  return super()._search_best_clip(layer,named_linears,input_feat)
 def _apply_quant(self,layer,named_linears):
  rows=[]
  if self.observed_layer in [0,13,27]:
   for name,linear in named_linears.items():
    x=self.features[name].reshape(-1,linear.in_features)
    stride=max(1,len(x)//256);x=x[::stride][:256].to('cuda',dtype=torch.float32)
    original=self.unclipped[name].to('cuda',dtype=torch.float32)
    quantized=self.pseudo_quantize_tensor(linear.weight.detach().clone())[0].to('cuda',dtype=torch.float32)
    reference=torch.nn.functional.linear(x,original);candidate=torch.nn.functional.linear(x,quantized)
    error=float((reference-candidate).square().sum());denominator=float(reference.square().sum())
    rows.append({'layer':self.observed_layer,'name':name,'tokens':len(x),'output_elements':reference.numel(),
      'squared_error_sum':error,'reference_squared_sum':denominator,'relative_mse':error/max(denominator,1e-20),
      'weight_rmse':float((original-quantized).square().mean().sqrt())})
    del x,original,quantized,reference,candidate
  self.unclipped={}
  super()._apply_quant(layer,named_linears)
  atomic_json(run.path/f'layer-{self.observed_layer:02d}.json',{'layer':self.observed_layer,'sensitivity':rows,
    'packed_modules':list(named_linears),'elapsed_s':time.perf_counter()-self.before_layer})
  run.manifest['last_packed_layer']=self.observed_layer;run.manifest['heartbeat_at']=now();run.save()
  self.features={}
  if stop[0]:raise InterruptedError('SIGTERM observed after layer; restart full calibration in new destination/run')
try:
 model=AutoAWQForCausalLM.from_pretrained(str(target),torch_dtype=torch.float16,device_map='cpu',
     trust_remote_code=False,attn_implementation='sdpa',local_files_only=True)
 tokenizer=AutoTokenizer.from_pretrained(target,local_files_only=True)
 model.quantize(tokenizer,quant_config=quant_config,calib_data=blocks,n_parallel_calib_samples=4,
   max_calib_samples=32,max_calib_seq_len=512,max_chunk_memory=256*1024**2,quantizer_cls=ObservedQuantizer)
 model.save_quantized(str(args.destination),shard_size='4GB');tokenizer.save_pretrained(args.destination)
 tensors=[]
 from safetensors import safe_open
 for path in sorted(args.destination.glob('*.safetensors')):
  with safe_open(path,framework='pt',device='cpu') as f:
   for key in f.keys():
    t=f.get_slice(key);tensors.append({'name':key,'dtype':t.get_dtype(),'shape':t.get_shape()})
 files=[{'path':str(f),'bytes':f.stat().st_size,'sha256':file_hash(f)} for f in sorted(args.destination.iterdir()) if f.is_file()]
 provenance={'model':base['model'],'revision':'local-awq-'+run.manifest['run_id'],
 'derivation':{'type':'AWQ-W4A16','config':quant_config,'source':args.source,'calibration_sha256':entry['sha256'],
 'base_provenance_sha256':file_hash(target/'driveserve-provenance.json'),'run_id':run.manifest['run_id']},'files':files}
 atomic_json(args.destination/'driveserve-provenance.json',provenance);atomic_json(run.path/'export.json',provenance)
 atomic_json(run.path/'tensor-inventory.json',tensors)
 run.finish('completed',{'destination':str(args.destination),'files':len(files),'bytes':sum(f['bytes'] for f in files),
 'layers':len(model.model.model.layers),'peak_allocated_bytes':torch.cuda.max_memory_allocated(),'peak_reserved_bytes':torch.cuda.max_memory_reserved()})
except BaseException as exc:run.finish('interrupted' if isinstance(exc,InterruptedError) else 'failed',{'error':str(exc)});raise
