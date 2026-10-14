"""Freeze arbitrary named project asset trees for the existing verified OSS pipeline."""
import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path.cwd()))
from driveserve.evidence import atomic_json,file_hash,now,git_state
p=argparse.ArgumentParser();p.add_argument('--entry',action='append',required=True,help='unique-label=source-file-or-directory')
p.add_argument('--output',type=Path,required=True);args=p.parse_args()
if args.output.exists():raise ValueError('immutable inventory already exists')
files=[]
for entry in args.entry:
 name,raw=entry.split('=',1);source=Path(raw).resolve()
 if not name or any(v in name for v in ['/', '..']):raise ValueError('unsafe label')
 candidates=sorted(source.rglob('*')) if source.is_dir() else [source]
 for f in candidates:
  if f.is_symlink():raise ValueError('asset inventory requires regular files, no implicit linked sources')
  if not f.is_file() or f.name=='.lock':continue
  relative=Path(name)/f.relative_to(source) if source.is_dir() else Path(name)/f.name
  files.append({'name':str(relative),'source':str(f),'bytes':f.stat().st_size,'sha256':file_hash(f)})
assert files and len({f['name'] for f in files})==len(files)
provenance=args.output.with_suffix('.provenance.json')
atomic_json(provenance,{'created_at':now(),'type':'project-artifact-bundle','code':git_state(Path.cwd()),'files':files,
 'restore':'Each OSS tar has one safe relative member; verify receipt and member hash, extract to a fresh directory. Paths here document original sources, not persistence.'})
atomic_json(args.output,{'created_at':now(),'models':[{'role':'assets','model':'non-model project artifacts',
 'provenance_path':str(provenance.resolve()),'provenance_sha256':file_hash(provenance),'files':files}],
 'payload_bytes':sum(f['bytes'] for f in files)})
print(json.dumps({'inventory':str(args.output),'files':len(files),'bytes':sum(f['bytes'] for f in files)}))
