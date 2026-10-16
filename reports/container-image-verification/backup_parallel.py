"""Resume the verified image transfer with 16 multipart workers; full readback required."""
import json,pathlib,subprocess,sys
sys.path.insert(0,str(pathlib.Path.cwd()))
from scripts.container_image import digest,verify_archive,write_json,now
base=pathlib.Path('/dev/shm/driveserve-image-final-20261016')
archive=base/'driveserve.docker.tar.gz'
lock=json.loads((base/'image-lock.json').read_text())
prior=json.loads((base/'archive.json').read_text())
assert archive.stat().st_size==prior['bytes'] and digest(archive)==prior['sha256']
receipt=pathlib.Path('reports/container-image-oss.json')
assert not receipt.exists()
uri='oss://DriveServe/container-images/20261016-eb7cdf5ccb06/driveserve-'+prior['sha256'][:16]+'.docker.tar.gz'
old=receipt.with_suffix('.upload.log')
if old.exists(): old.rename(pathlib.Path('artifacts/container-image-20261016/upload-p2-interrupted.log'))
readback=archive.with_name(archive.name+'.readback')
assert not readback.exists()
def copy(source,target,log):
 with log.open('w') as out:
  subprocess.run(['oss','cp',str(source),str(target),'-p=16'],input=b'n\n',stdout=out,stderr=subprocess.STDOUT,check=True)
copy(archive,uri,receipt.with_suffix('.upload.log'))
print('upload completed',flush=True)
copy(uri,readback,receipt.with_suffix('.readback.log'))
print('fresh full download completed; verifying',flush=True)
assert readback.stat().st_size==prior['bytes'] and digest(readback)==prior['sha256']
verify_archive(readback,lock)
result=dict(schema_version=1,status='completed',verified_at=now(),object=uri,bytes=prior['bytes'],sha256=prior['sha256'],image=lock,verification='fresh full archive and every uncompressed layer/config SHA256',transfer_parallelism=16,estimated_incremental_CNY_per_day=prior['bytes']/1e9*.0004*24)
write_json(receipt,result)
readback.unlink()
print(json.dumps({k:v for k,v in result.items() if k!='image'}),flush=True)
