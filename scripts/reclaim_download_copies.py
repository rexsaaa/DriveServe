"""Reclaim only redundant project download weights after local and OSS receipt checks."""
import json,shutil,sys
from pathlib import Path
sys.path.insert(0,str(Path.cwd()))
from driveserve.evidence import Run,atomic_json,file_hash
receipt_path=Path('reports/s1-oss-models-receipt.json');receipt=json.load(open(receipt_path));assert receipt['status']=='completed'
run=Run(Path.cwd(),'reclaim-verified-download-copies',{'stage':'S2','requirement_ids':[],
 'hypothesis':'redundant original download caches can be removed while identical runtime weights and fully-read-back OSS copies remain',
 'receipt_sha256':file_hash(receipt_path),'scope':'only artifacts/models/{target,draft}-weights/*.safetensors',
 'limitations':['runtime model and remote artifacts are retained; future fresh inventory may need re-download of removed cache copies']},formal=True)
print(run.path,flush=True)
try:
 checked=[];before=shutil.disk_usage(Path.cwd()).free
 for role in ['target','draft']:
  for path in sorted((Path('artifacts/models')/(role+'-weights')).glob('*.safetensors')):
   item=next(i for i in receipt['plan']['items'] if i['name']==role+'/'+path.name)
   remote=receipt['verified'][item['object']];remaining=Path('/hy-tmp/driveserve/models')/role/path.name
   assert remote['content_sha256']==item['sha256']
   assert path.stat().st_size==remaining.stat().st_size==item['bytes']
   assert file_hash(path)==file_hash(remaining)==item['sha256']
   checked.append({'removed_cache':str(path),'retained_runtime':str(remaining),'oss_object':item['object'],
                   'bytes':item['bytes'],'sha256':item['sha256'],'remote_readback_receipt_sha256':file_hash(receipt_path)})
 assert len(checked)==5
 atomic_json(run.path/'verified-plan.json',checked)
 for row in checked:
  Path(row['removed_cache']).unlink()
  atomic_json(run.path/'removed.json',[r for r in checked if not Path(r['removed_cache']).exists()])
 result={'removed_files':len(checked),'payload_bytes':sum(r['bytes'] for r in checked),
         'filesystem_free_before':before,'filesystem_free_after':shutil.disk_usage(Path.cwd()).free}
 run.finish('completed',result);print(json.dumps(result))
except BaseException as exc:run.finish('failed',{'error':str(exc)});raise
