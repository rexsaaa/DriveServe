"""Preserve a standalone Git bundle and verified recovery metadata alongside the image."""
import hashlib,json,pathlib,subprocess,tarfile,shutil,sys
sys.path.insert(0,str(pathlib.Path.cwd()))
from scripts.container_image import digest,oss_copy,write_json,now
root=pathlib.Path.cwd(); build=pathlib.Path('/dev/shm/driveserve-image-final-20261016')
receipt=json.loads((root/'reports/container-image-oss.json').read_text())
assert receipt['status']=='completed'
prefix=receipt['object'].rsplit('/',1)[0]
kit=build/'recovery-kit.tar.gz'
if kit.exists(): raise RuntimeError('Kit already exists')
files=['docs/container-recovery.md','reports/container-image-oss.json','reports/container-image-validation.json']
files += [str(p.relative_to(root)) for p in (root/'reports/container-image-verification').iterdir() if p.is_file()]
with tarfile.open(kit,'w:gz') as tar:
 tar.add(build/'source.bundle',arcname='source.bundle')
 for rel in sorted(files): tar.add(root/rel,arcname='recovery-files/'+rel)
# The bundle supplies all historical model receipts and all implementation scripts.
checksum=build/'SHA256SUMS'
checksum.write_text(digest(kit)+'  recovery-kit.tar.gz\n'+receipt['sha256']+'  '+receipt['object'].rsplit('/',1)[1]+'\n')
index=build/'recovery-index.tar.gz'
with tarfile.open(index,'w:gz') as tar:
 tar.add(checksum,arcname='SHA256SUMS')
 tar.add(root/'docs/container-recovery.md',arcname='RECOVER.md')
items=[]
for path in [kit,index]:
 uri=prefix+'/'+path.name
 oss_copy(path,uri,root/'artifacts/container-image-20261016'/('kit-upload-'+path.name+'.log'))
 back=path.with_name(path.name+'.oss-readback')
 oss_copy(uri,back,root/'artifacts/container-image-20261016'/('kit-readback-'+path.name+'.log'))
 assert back.stat().st_size==path.stat().st_size and digest(back)==digest(path)
 items.append(dict(object=uri,bytes=path.stat().st_size,sha256=digest(path),verification='fresh full OSS readback SHA256'))
 back.unlink()
result=dict(status='completed',created_at=now(),objects=items,image_receipt='reports/container-image-oss.json',source_commit=receipt['image']['source_commit'],scope='Git bundle plus post-build recovery docs and receipts; credentials excluded')
write_json(root/'reports/container-recovery-kit-oss.json',result)
# Exercise the exact offline bootstrap using only the readback-verified kit.
unpacked=pathlib.Path('/tmp/driveserve-recovery-kit-check')
unpacked.mkdir()
subprocess.run(['tar','-xzf',str(kit),'-C',str(unpacked)],check=True)
checkout=unpacked/'DriveServe'
subprocess.run(['git','clone',str(unpacked/'source.bundle'),str(checkout)],check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
shutil.copytree(unpacked/'recovery-files',checkout,dirs_exist_ok=True)
sha=subprocess.check_output(['git','rev-parse','HEAD'],cwd=checkout,text=True).strip()
assert sha==receipt['image']['source_commit']
for script in ['container_image.py','restore_container_models.py']:
 subprocess.run([sys.executable,str(checkout/'scripts'/script),'--help'],check=True,stdout=subprocess.PIPE)
assert json.loads((checkout/'reports/container-image-oss.json').read_text())==receipt
write_json(root/'reports/container-image-verification/recovery-kit-bootstrap.json',dict(status='passed',source_commit=sha,scope='OSS-verified standalone kit extraction, Git clone, restored receipt and both recovery CLI help commands; no GitHub or original project needed by the recovered scripts'))
print(json.dumps(result),flush=True)
