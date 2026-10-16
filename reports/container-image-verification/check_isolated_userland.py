"""Execute selected image userland in a fresh root; no host libraries or bind mounts."""
import json, os, pathlib, shutil, subprocess, hashlib
src=pathlib.Path('/dev/shm/driveserve-image-unpacked/rootfs')
dst=pathlib.Path('/tmp/driveserve-image-userland-check')
if dst.exists(): raise RuntimeError('fresh destination required')
dst.mkdir()
copied=[]
def copy(rel):
 s=src/rel; d=dst/rel
 if not s.exists() and not s.is_symlink(): return
 d.parent.mkdir(parents=True,exist_ok=True)
 if s.is_symlink():
  d.symlink_to(os.readlink(s))
 elif s.is_dir():
  d.mkdir(exist_ok=True)
  for p in s.iterdir(): copy(str(p.relative_to(src)))
 else:
  shutil.copy2(s,d); copied.append(rel)
for rel in ['bin','sbin','lib','lib64','etc','usr/bin','usr/sbin','usr/lib/gcc','usr/lib/python3.11','usr/lib/git-core','usr/share/git-core','usr/include','usr/local/bin/python','usr/local/bin/python3','usr/local/cuda','usr/local/cuda-12','usr/local/cuda-12.1/bin','usr/local/cuda-12.1/nvvm','usr/local/cuda-12.1/include','usr/local/cuda-12.1/targets/x86_64-linux/include','opt/driveserve']:
 copy(rel)
for p in (src/'usr/lib/x86_64-linux-gnu').iterdir():
 if p.name.startswith(('libcudnn','libnccl','libLLVM')) or p.name in ['dri']: continue
 copy(str(p.relative_to(src)))
for p in (src/'usr/lib64').iterdir(): copy(str(p.relative_to(src)))
for rel in ['tmp','dev','proc','sys','root','hy-netdisk/jq/project/DriveServe']:
 (dst/rel).mkdir(parents=True,exist_ok=True)
(dst/'dev/null').touch()
(dst/'tmp/test.cu').write_text('__global__ void add(float *p) { p[threadIdx.x] += 1.0f; }\n')
env={'PATH':'/usr/bin:/bin','HOME':'/root','LANG':'C.UTF-8','PYTHONDONTWRITEBYTECODE':'1'}
commands=[
 ['/usr/bin/python3.11','-c','import sys,ssl,sqlite3,ctypes,platform,json; print(json.dumps(dict(python=sys.version,libc=platform.libc_ver(),ssl=ssl.OPENSSL_VERSION,sqlite=sqlite3.sqlite_version)))'],
 ['/usr/local/cuda-12.1/bin/nvcc','--version'],
 ['/usr/local/cuda-12.1/bin/nvcc','-ptx','-arch=sm_89','/tmp/test.cu','-o','/tmp/test.ptx'],
 ['/opt/driveserve/entrypoint.sh','/usr/bin/git','rev-parse','HEAD']]
# The original project layer is replaced with the final layer before this script runs.
lock=json.loads(pathlib.Path('/dev/shm/driveserve-image-final-20261016/image-lock.json').read_text())
env['DRIVESERVE_SOURCE_COMMIT']=lock['source_commit']
checks=[]
for cmd in commands:
 r=subprocess.run(['/usr/sbin/chroot',str(dst),*cmd],env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
 checks.append(dict(command=cmd,returncode=r.returncode,output=r.stdout))
 print(json.dumps(checks[-1]),flush=True)
 if r.returncode: break
out=pathlib.Path('/hy-netdisk/jq/project/DriveServe/artifacts/container-image-20261016/isolated-userland.json')
ptx=dst/'tmp/test.ptx'
result=dict(status='passed' if len(checks)==len(commands) and all(x['returncode']==0 for x in checks) else 'failed',source='files copied only from independently unpacked image',image_manifest=lock['manifest']['digest'],copied_regular_files=len(copied),commands=checks,ptx_sha256=hashlib.sha256(ptx.read_bytes()).hexdigest() if ptx.exists() else None,scope='Selected system userland Python/CUDA compiler and bundled source entrypoint; no Docker daemon, complete venv execution, or GPU device test')
out.write_text(json.dumps(result,indent=2)+'\n')
if result['status']!='passed': raise SystemExit(1)
