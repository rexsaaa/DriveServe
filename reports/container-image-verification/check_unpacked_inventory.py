import gzip,hashlib,json,os,pathlib
root=pathlib.Path('/dev/shm/driveserve-image-unpacked/rootfs')
with gzip.open('/dev/shm/driveserve-image-final-20261016/file-inventory.json.gz') as f: inventory=json.load(f)
counts={}; errors=[]
for layer in inventory:
 counts[layer['layer']]={'files':0,'symlinks':0,'directories':0,'bytes':0}
 c=counts[layer['layer']]
 for item in layer['entries']:
  p=root/item['path']
  try:
   if item['type']=='file':
    if p.is_symlink() or p.stat().st_size!=item['bytes']: raise ValueError('type/size mismatch')
    h=hashlib.sha256()
    with p.open('rb') as s:
     for b in iter(lambda:s.read(8*1024**2),b''): h.update(b)
    if h.hexdigest()!=item['sha256']: raise ValueError('SHA256 mismatch')
    c['files']+=1; c['bytes']+=item['bytes']
   elif item['type']=='symlink':
    if os.readlink(p)!=item['target']: raise ValueError('symlink mismatch')
    c['symlinks']+=1
   else:
    if not p.is_dir() or p.is_symlink(): raise ValueError('directory mismatch')
    c['directories']+=1
  except Exception as e: errors.append({'path':item['path'],'error':str(e)})
result={'status':'passed' if not errors else 'failed','layers':counts,'errors':errors,'scope':'Independent umoci unpack plus final project layer; all regular files hashed, symlink text and directory types checked'}
pathlib.Path('artifacts/container-image-20261016/unpacked-inventory-check.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result))
raise SystemExit(bool(errors))
