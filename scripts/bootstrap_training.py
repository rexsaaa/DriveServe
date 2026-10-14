"""Install a pinned additive training layer without modifying the GPU baseline venv."""
import argparse,hashlib,json,os,subprocess,sys
from pathlib import Path
sys.path.insert(0,str(Path.cwd()))
from driveserve.evidence import atomic_json,file_hash,now
p=argparse.ArgumentParser();p.add_argument('--destination',type=Path,required=True);p.add_argument('--wheels',type=Path,required=True);args=p.parse_args()
if args.destination.exists():raise ValueError('immutable dependency layer already exists')
args.wheels.mkdir(parents=True,exist_ok=True)
packages=['accelerate==1.6.0','peft==0.15.2']
base=subprocess.check_output([sys.executable,'-m','pip','freeze'],text=True)
subprocess.run([sys.executable,'-m','pip','download','--no-deps','--only-binary=:all:', '--index-url','https://pypi.org/simple','--dest',str(args.wheels),*packages],check=True)
wheels=[]
for name in ['accelerate-1.6.0-py3-none-any.whl','peft-0.15.2-py3-none-any.whl']:
 path=args.wheels/name;assert path.is_file();wheels.append({'name':name,'bytes':path.stat().st_size,'sha256':file_hash(path)})
subprocess.run([sys.executable,'-m','pip','install','--no-deps','--no-index','--find-links',str(args.wheels),'--target',str(args.destination),*packages],check=True)
assert subprocess.check_output([sys.executable,'-m','pip','freeze'],text=True)==base
addon_env={**os.environ,'PYTHONPATH':str(args.destination)}
subprocess.run([sys.executable,'-m','pip','check'],env=addon_env,check=True)
subprocess.run([sys.executable,'-c','import torch, transformers, peft, accelerate; print(torch.__version__, transformers.__version__, peft.__version__, accelerate.__version__)'],env=addon_env,check=True)
manifest={'created_at':now(),'python':sys.executable,'layer':str(args.destination),
 'requirements':packages,'wheels':wheels,'base_freeze_sha256':hashlib.sha256(base.encode()).hexdigest(),
 'base_requirements_sha256':file_hash('requirements/gpu.lock.txt'),'base_environment_unchanged':True,
 'rebuild':'rebuild locked GPU venv; install these exact wheels with --no-deps --target; prepend layer to PYTHONPATH',
 'limitation':'additive Python dependency layer depends on locked base environment; not a standalone venv'}
atomic_json(args.destination/'driveserve-training-layer.json',manifest)
print(json.dumps(manifest,indent=2))
