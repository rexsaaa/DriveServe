"""Freeze equal-token general/domain calibration without touching final-test data."""
import argparse,hashlib,json,os,sys
from pathlib import Path
sys.path.insert(0,str(Path.cwd()))
from driveserve.evidence import Run,atomic_json,file_hash
from driveserve.task import messages,digest
p=argparse.ArgumentParser();p.add_argument('--destination',type=Path,required=True)
p.add_argument('--layer',type=Path,default=Path('/hy-tmp/driveserve/awq-deps-v2'));args=p.parse_args()
if args.destination.exists():raise ValueError('immutable calibration destination already exists')
sys.path.insert(0,str(args.layer.resolve()))
import requests,pyarrow.parquet as pq
from transformers import AutoTokenizer
revision='b08601e04326c79dfdd32d625aee71d232d685c3'
expected='e83889baabc497075506f91975be5fac0d45c5290b6b20582c8cd1e853d0c9f7'
run=Run(Path.cwd(),'awq-calibration-freeze',{'stage':'S2','requirement_ids':['M4-02'],
 'hypothesis':'general and domain calibration share exact 32x512 token budget and immutable sources',
 'dataset':'Salesforce/wikitext/wikitext-2-raw-v1 train','revision':revision,
 'license':['CC-BY-SA-3.0','GFDL'],'domain_manifest_sha256':file_hash('data/frozen-v1/manifest.json'),
 'token_budget':16384,'blocks':32,'block_length':512,
 'limitations':['small fixed prefixes, not full-distribution coverage','general text downloaded from hf-mirror.com with pinned upstream-revision hash',
 'same domain task schema as dev; final test never opened','upstream AWQ routine will consume pretokenized blocks without reshuffling']},formal=True)
print(run.path,flush=True)
try:
 args.destination.mkdir(parents=True);session=requests.Session();session.trust_env=False
 endpoint='https://hf-mirror.com';dataset='Salesforce/wikitext'
 api=session.get(f'{endpoint}/api/datasets/{dataset}/revision/{revision}?blobs=true',timeout=30);api.raise_for_status();metadata=api.json()
 assert metadata['sha']==revision
 atomic_json(args.destination/'upstream-metadata.json',metadata)
 for name in ['README.md','wikitext-2-raw-v1/train-00000-of-00001.parquet']:
  item=next(v for v in metadata['siblings'] if v['rfilename']==name)
  r=session.get(f'{endpoint}/datasets/{dataset}/resolve/{revision}/{name}',timeout=60);r.raise_for_status()
  dest=args.destination/Path(name).name;dest.write_bytes(r.content)
  if name.endswith('parquet'):assert file_hash(dest)==item['lfs']['sha256']==expected
  else:assert hashlib.sha1(b'blob '+str(len(r.content)).encode()+b'\0'+r.content).hexdigest()==item['blobId']
 tokenizer=AutoTokenizer.from_pretrained('/hy-tmp/driveserve/models/target',local_files_only=True)
 texts=pq.read_table(args.destination/'train-00000-of-00001.parquet',columns=['text']).column('text').to_pylist()
 domain=[json.loads(line) for line in Path('data/frozen-v1/calibration.jsonl').read_text().splitlines()]
 assert all(r['split']=='calibration' for r in domain)
 frozen=json.load(open('data/frozen-v1/manifest.json'));assert file_hash('data/frozen-v1/calibration.jsonl')==frozen['files']['calibration']['sha256']
 streams={'general':[],'domain':[]};used={'general':[],'domain':[]}
 for i,text in enumerate(texts):
  if not text.strip():continue
  streams['general']+=tokenizer.encode(text,add_special_tokens=False)+[tokenizer.eos_token_id];used['general'].append(i)
  if len(streams['general'])>=16384:break
 for row in domain:
  streams['domain']+=tokenizer.apply_chat_template(messages(row['scene']),tokenize=True,add_generation_prompt=True)+[tokenizer.eos_token_id]
  used['domain'].append(row['scene']['scene_id'])
  if len(streams['domain'])>=16384:break
 files={}
 for kind,tokens in streams.items():
  assert len(tokens)>=16384
  blocks=[tokens[i:i+512] for i in range(0,16384,512)]
  dest=args.destination/(kind+'-tokens.json');atomic_json(dest,blocks)
  files[kind]={'path':str(dest),'sha256':file_hash(dest),'blocks':len(blocks),'tokens':sum(map(len,blocks)),
               'source_rows_including_last_partially_used':used[kind],'unused_tail_tokens':len(tokens)-16384}
 manifest={'revision':revision,'source_url':f'https://huggingface.co/datasets/{dataset}/tree/{revision}',
 'license':['CC-BY-SA-3.0','GFDL'],'attribution':'WikiText by Stephen Merity et al., sourced from Wikipedia; retain upstream README and attribution for shared text/token derivatives.',
 'tokenizer_sha256':file_hash('/hy-tmp/driveserve/models/target/tokenizer.json'),'domain_manifest_sha256':file_hash('data/frozen-v1/manifest.json'),
 'files':files,'raw_parquet_sha256':expected,'run_id':run.manifest['run_id'],
 'purpose':'calibration only; tokens do not become teacher training records; final-test untouched'}
 atomic_json(args.destination/'calibration-manifest.json',manifest);atomic_json(run.path/'calibration-manifest.json',manifest)
 run.finish('completed',{'tokens_per_source':16384,'blocks_per_source':32,'destination':str(args.destination)})
except BaseException as exc:run.finish('failed',{'error':str(exc)});raise
