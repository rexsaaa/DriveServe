"""Fresh small OSS restores plus presence listings; full weights use historical readbacks."""
import json,subprocess,sys
from pathlib import Path
sys.path.insert(0,str(Path.cwd()))
from driveserve.evidence import Run,atomic_json,file_hash
root=Path.cwd()
reference=json.load(open('reports/s3-restore/summary.json'))
receipts=[x['argv'][x['argv'].index('--receipt')+1] for x in reference['probes']]
receipts+=['reports/s1-environment-receipt.json']
config=dict(stage='S5',requirement_ids=[],hypothesis='all previously backed up object names remain listed and selected metadata can be freshly downloaded and hash-verified',
 receipts=[dict(path=p,sha256=file_hash(p)) for p in receipts],
 limitations=['Fresh probes cover nine small files, not a second complete model/environment restore or a host migration.',
 'Presence listings do not verify current whole-weight checksums; historical full archive/content readback receipts remain the integrity evidence.',
 'No new object upload or cloud deletion; no budget cap introduced.'])
run=Run(root,'s5-asset-readback',config,formal=True);print(run.path,flush=True)
try:
 listings=[];objects=set();total_bytes=0
 for name in receipts:
  r=json.load(open(name))
  if 'plan' in r:expected=[x['object'] for x in r['plan']['items']];prefix=r['plan']['destination'].rstrip('/')+'/'
  else:expected=[r['object']];prefix=r['object'].rsplit('/',1)[0]+'/'
  assert len(set(expected))==len(expected)
  log=run.path/(Path(name).stem+'-listing.log')
  with log.open('w') as f:result=subprocess.run(['oss','ls',prefix],stdout=f,stderr=subprocess.STDOUT,timeout=120)
  result.check_returncode();text=log.read_text()
  assert all(obj in text for obj in expected),'object absent from current prefix listing'
  for obj in expected:assert obj not in objects;objects.add(obj)
  total_bytes+=sum(x['archive_bytes'] for x in r['plan']['items']) if 'plan' in r else r['bytes']
  listings.append(dict(receipt=name,prefix=prefix,listed_expected_objects=len(expected),log=log.name,sha256=file_hash(log)))
 probes=[]
 for ref in reference['probes']:
  label=ref['name'];report=run.path/(label+'-restore.json');destination=run.path/'restored'/label
  argv=list(ref['argv']);argv[0]=sys.executable
  argv[argv.index('--report')+1]=str(report);argv[argv.index('--destination')+1]=str(destination)
  log=run.path/(label+'-restore-command.log')
  with log.open('w') as f:result=subprocess.run(argv,stdout=f,stderr=subprocess.STDOUT,timeout=300)
  result.check_returncode();restored=json.load(open(report));assert restored['status']=='completed'
  assert len(restored['restored'])==ref['files'] and all(x['action']=='downloaded_and_restored' for x in restored['restored'])
  probes.append(dict(label=label,argv=argv,files=ref['files'],report=report.name,sha256=file_hash(report)))
 assert sum(x['files'] for x in probes)==9 and len(objects)==144
 summary=dict(status='passed',objects_listed=len(objects),archive_bytes=total_bytes,estimated_CNY_per_day=total_bytes/1e9*.0004*24,
  small_files_freshly_restored=9,listings=listings,probes=probes,limits=config['limitations'])
 atomic_json(run.path/'summary.json',summary);run.finish('completed',summary)
except BaseException as e:run.finish('failed',dict(error=str(e)));raise
