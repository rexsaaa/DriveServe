"""Merge a verified LoRA checkpoint into a separate Draft; preserve all input assets."""
import argparse,json,os,shutil,sys
from pathlib import Path
sys.path.insert(0,str(Path.cwd()))
from driveserve.evidence import Run,atomic_json,file_hash
p=argparse.ArgumentParser();p.add_argument('--training',type=Path,required=True);p.add_argument('--destination',type=Path,required=True)
p.add_argument('--base',type=Path,default=Path('/hy-tmp/driveserve/models/draft-aligned-v1'))
p.add_argument('--layer',type=Path,default=Path('/hy-tmp/driveserve/training-deps-v1'));args=p.parse_args()
sys.path.insert(0,str(args.layer.resolve()))
import torch
from transformers import AutoModelForCausalLM,AutoTokenizer
from peft import PeftModel
if args.destination.exists():raise ValueError('immutable exported model already exists')
latest=json.load(open(args.training/'latest.json'));checkpoint=args.training/latest['directory']
assert file_hash(checkpoint/'checkpoint.json')==latest['manifest_sha256']
manifest=json.load(open(checkpoint/'checkpoint.json'))
for entry in manifest['files']:assert file_hash(checkpoint/entry['name'])==entry['sha256']
base_provenance=json.load(open(args.base/'driveserve-provenance.json'))
for entry in base_provenance['files']:assert file_hash(args.base/Path(entry['path']).name)==entry['sha256']
run=Run(Path.cwd(),'draft-merge-export',{'stage':'S2','requirement_ids':['M3-04','M3-05'],
 'hypothesis':'verified LoRA adapter is merged into an independent FP16 vLLM-loadable Draft',
 'model':base_provenance,'checkpoint':{'manifest':manifest,'sha256':latest['manifest_sha256']},
 'config':{'load_dtype':'bfloat16','merge_dtype':'bfloat16','export_dtype':'float16'},
 'limitations':['BF16 merge into BF16 base then cast FP16 adds rounding; actual deployment evaluation required']},formal=True)
print(run.path,flush=True)
try:
 model=AutoModelForCausalLM.from_pretrained(args.base,torch_dtype=torch.bfloat16,local_files_only=True)
 model=PeftModel.from_pretrained(model,checkpoint/'adapter').merge_and_unload(safe_merge=True)
 model=model.to(torch.float16);model.config.use_cache=True
 model.save_pretrained(args.destination,safe_serialization=True)
 for name in ['tokenizer.json','tokenizer_config.json','merges.txt','vocab.json']:
  shutil.copyfile(args.base/name,args.destination/name)
 files=[{'path':str(f),'bytes':f.stat().st_size,'sha256':file_hash(f)} for f in sorted(args.destination.iterdir()) if f.is_file()]
 provenance={'model':base_provenance.get('model'),'revision':'local-sequence-distillation-'+manifest['identity'][:16],
 'derivation':{'type':'teacher-sequence-LoRA','base_provenance_sha256':file_hash(args.base/'driveserve-provenance.json'),
 'training_checkpoint_sha256':latest['manifest_sha256'],'step':manifest['step'],'training_identity':manifest['identity'],
 'export_run':run.manifest['run_id'],'merge_dtype':'bfloat16','export_dtype':'float16'},'files':files}
 atomic_json(args.destination/'driveserve-provenance.json',provenance)
 atomic_json(run.path/'export.json',provenance);run.finish('completed',{'files':len(files),'bytes':sum(f['bytes'] for f in files),'destination':str(args.destination)})
except BaseException as exc:run.finish('failed',{'error':str(exc)});raise
