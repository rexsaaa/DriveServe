"""Re-audit the saved fresh restore/listing run; no new network access."""
import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path.cwd()))
from driveserve.evidence import file_hash,verify_assets,atomic_json
p=argparse.ArgumentParser();p.add_argument('--run',type=Path,required=True);p.add_argument('--report',type=Path,required=True);a=p.parse_args()
m=json.load(open(a.run/'manifest.json'));assert m['stage']=='S5' and m['kind']=='s5-asset-readback' and m['status']=='completed' and not m['code']['dirty'];verify_assets(Path.cwd(),m)
r=json.load(open(a.run/'summary.json'));assert r==m['result'] and r['status']=='passed'
contract_info=m['config']['asset_contract'];assert file_hash(contract_info['path'])==contract_info['sha256']
contract=json.load(open(contract_info['path']));receipt_hashes={x['path']:x['sha256'] for x in m['config']['receipts']}
assert set(receipt_hashes)==set(contract['receipts'])
objects=set();total=0;files=[]
for listing in r['listings']:
 assert file_hash(listing['receipt'])==receipt_hashes[listing['receipt']]
 receipt=json.load(open(listing['receipt']));text=(a.run/listing['log']).read_text();assert file_hash(a.run/listing['log'])==listing['sha256']
 if 'plan' in receipt:
  entries=receipt['plan']['items'];expected={x['object'] for x in entries};size=sum(x['archive_bytes'] for x in entries)
 else:expected={receipt['object']};size=receipt['bytes']
 assert len(expected)==listing['listed_expected_objects'] and all(x in text for x in expected) and not objects.intersection(expected)
 objects.update(expected);total+=size
for probe in r['probes']:
 report=a.run/probe['report'];assert file_hash(report)==probe['sha256'];restored=json.load(open(report))
 assert restored['status']=='completed' and len(restored['restored'])==probe['files']
 for x in restored['restored']:
  # Recorded destination is the producing checkout's absolute path. Use the
  # repository-relative restored member for independent cloned verification.
  path=a.run/'restored'/probe['label']/x['name']
  assert x['action']=='downloaded_and_restored' and path.stat().st_size==x['bytes'] and file_hash(path)==x['sha256']
  files.append(dict(probe=probe['label'],name=x['name'],bytes=x['bytes'],sha256=x['sha256']))
assert {x['receipt'] for x in r['listings']}==set(contract['receipts'])
assert len(objects)==r['objects_listed']==contract['expected_objects']
assert total==r['archive_bytes']==contract['expected_archive_bytes'] and len(files)==contract['expected_fresh_small_files']
atomic_json(a.report,dict(status='passed',aggregator_sha256=file_hash(__file__),run_id=m['run_id'],source_sha=m['code']['sha'],
 manifest=dict(path=str(a.run/'manifest.json'),sha256=file_hash(a.run/'manifest.json')),
 objects_listed=len(objects),archive_bytes=total,small_files_freshly_restored=files,
 estimated_CNY_per_day=total/1e9*.0004*24,limits=r['limits']))
print(json.dumps(dict(status='passed',objects=len(objects),fresh_small_files=len(files))))
