"""Pin an additive AWQ layer, preserving the baseline GPU and training layers."""
import argparse,hashlib,json,os,subprocess,sys
from pathlib import Path
sys.path.insert(0,str(Path.cwd()))
from driveserve.evidence import atomic_json,file_hash,now
p=argparse.ArgumentParser();p.add_argument('--destination',type=Path,required=True);p.add_argument('--wheels',type=Path,required=True)
p.add_argument('--training-layer',type=Path,default=Path('/hy-tmp/driveserve/training-deps-v1'));args=p.parse_args()
if args.destination.exists():raise ValueError('immutable dependency layer already exists')
args.wheels.mkdir(parents=True,exist_ok=True)
packages=['autoawq==0.2.9','datasets==3.5.0','pyarrow==19.0.1','pandas==2.2.3','dill==0.3.8','multiprocess==0.70.16',
          'fsspec==2024.12.0','zstandard==0.23.0','xxhash==3.5.0','python-dateutil==2.9.0.post0','pytz==2025.2','tzdata==2025.2']
base=subprocess.check_output([sys.executable,'-m','pip','freeze'],text=True)
subprocess.run([sys.executable,'-m','pip','wheel','--no-deps','--no-build-isolation','--index-url','https://pypi.org/simple','--wheel-dir',str(args.wheels),*packages],check=True)
wheels=[{'name':p.name,'bytes':p.stat().st_size,'sha256':file_hash(p)} for p in sorted(args.wheels.glob('*.whl'))]
subprocess.run([sys.executable,'-m','pip','install','--no-deps','--no-index','--find-links',str(args.wheels),'--target',str(args.destination),*packages],check=True)
assert subprocess.check_output([sys.executable,'-m','pip','freeze'],text=True)==base
addon_env={**os.environ,'PYTHONPATH':os.pathsep.join(map(str,[args.destination,args.training_layer]))}
subprocess.run([sys.executable,'-m','pip','check'],env=addon_env,check=True)
subprocess.run([sys.executable,'-c','import awq, datasets, pyarrow, torch; print(awq.__version__,datasets.__version__,pyarrow.__version__,torch.__version__)'],env=addon_env,check=True)
manifest={'created_at':now(),'python':sys.executable,'layer':str(args.destination),'requirements':packages,'wheels':wheels,
 'base_freeze_sha256':hashlib.sha256(base.encode()).hexdigest(),'base_requirements_sha256':file_hash('requirements/gpu.lock.txt'),
 'training_layer_manifest_sha256':file_hash(args.training_layer/'driveserve-training-layer.json'),'base_environment_unchanged':True,
 'rebuild':'rebuild locked GPU and training layer; install these wheels --no-deps --target, prepend AWQ then training layer to PYTHONPATH',
 'limitation':'AutoAWQ is third-party calibration tooling, not a project-authored quantization algorithm; native vLLM deploy uses base environment'}
atomic_json(args.destination/'driveserve-awq-layer.json',manifest);print(json.dumps(manifest,indent=2))
