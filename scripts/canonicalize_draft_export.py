"""Derive a corrected export with byte-identical base tokenizer files, no weight rewrite."""
import argparse,json,os,shutil,sys
from pathlib import Path
sys.path.insert(0,str(Path.cwd()))
from driveserve.evidence import Run,atomic_json,file_hash
p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--destination',type=Path,required=True)
p.add_argument('--base',type=Path,default=Path('/hy-tmp/driveserve/models/draft-aligned-v1'));args=p.parse_args()
assert not args.destination.exists()
previous=json.load(open(args.source/'driveserve-provenance.json'))
for row in previous['files']:assert file_hash(args.source/Path(row['path']).name)==row['sha256']
run=Run(Path.cwd(),'draft-tokenizer-canonicalization',{'stage':'S2','requirement_ids':['M3-01','M3-04'],
 'hypothesis':'save_pretrained rewrites tokenizer serialization; copy byte-exact proven-compatible base artifacts, keeping merged weights identical',
 'model':previous,'source':str(args.source),'destination':str(args.destination),
 'limitation':'hardlinks reuse immutable local weights only; restore from independent OSS objects after migration'},formal=True)
print(run.path,flush=True)
try:
 args.destination.mkdir()
 tokenizer_names=['tokenizer.json','tokenizer_config.json','merges.txt','vocab.json']
 for f in args.source.iterdir():
  if not f.is_file() or f.name in ['driveserve-provenance.json','special_tokens_map.json','added_tokens.json',*tokenizer_names]:continue
  if f.suffix=='.safetensors':os.link(f,args.destination/f.name)
  else:shutil.copyfile(f,args.destination/f.name)
 for name in tokenizer_names:shutil.copyfile(args.base/name,args.destination/name)
 files=[{'path':str(f),'bytes':f.stat().st_size,'sha256':file_hash(f)} for f in sorted(args.destination.iterdir()) if f.is_file()]
 current={**previous,'files':files,'derivation':{**previous['derivation'],'canonical_tokenizer_source':str(args.base),'canonicalization_run':run.manifest['run_id']}}
 atomic_json(args.destination/'driveserve-provenance.json',current);atomic_json(run.path/'export.json',current)
 for f in files:
  if f['path'].endswith('.safetensors'):assert f['sha256']==file_hash(args.source/Path(f['path']).name)
 run.finish('completed',{'unchanged_weights':True,'canonical_tokenizer_files':len(tokenizer_names)})
except BaseException as exc:run.finish('failed',{'error':str(exc)});raise
