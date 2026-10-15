"""Verify a clean GitHub checkout with a fresh CPU env and saved GPU evidence."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

p=argparse.ArgumentParser()
p.add_argument('--checkout',type=Path,required=True)
p.add_argument('--output',type=Path,required=True)
p.add_argument('--env',type=Path,required=True)
p.add_argument('--index',default='https://mirrors.cloud.tencent.com/pypi/simple')
a=p.parse_args()
clone=a.checkout.resolve();out=a.output.resolve();env=a.env.resolve()
if out.exists() or env.exists():raise ValueError('select fresh verification output and environment paths')
out.mkdir(parents=True)
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def git(*args):return subprocess.check_output(['git',*args],cwd=clone,text=True).strip()
assert not git('status','--porcelain'),'checkout must be clean'
origin=git('remote','get-url','origin');assert origin in ['git@github.com:rexsaaa/DriveServe.git','https://github.com/rexsaaa/DriveServe.git']
head=git('rev-parse','HEAD')
result=dict(status='running',head=head,remote=origin,clean_before=True,commands=[],
 limits=['Fresh CPU environment and asset access in an independent GitHub checkout; no new GPU inference, training or host migration.',
         '36 local-wheel relocation and negative guards use separately recorded local verification; this checker freshly restores aiohttp from OSS.',
         'S5 frozen GPU paths and all formal conclusions remain unchanged; user mastery is not tested.'])
def save():(out/'readback.json').write_text(json.dumps(result,indent=2)+'\n')
def run(label,argv):
    log=out/(label+'.log')
    with log.open('w') as f:r=subprocess.run(argv,cwd=clone,stdout=f,stderr=subprocess.STDOUT)
    result['commands'].append(dict(label=label,argv=list(map(str,argv)),returncode=r.returncode,log=log.name,sha256=sha(log)))
    save();r.check_returncode();return log
try:
    # Freeze all S5 execution, data, tests, GPU locks and experiment configs.
    protected=git('ls-tree','-r','--name-only','stage-5-release-candidate','driveserve','csrc','patches','tests','data','configs','requirements').splitlines()
    execution_prefixes=('benchmark_','train_','quantize_','export_','check_rope','check_policy','build_vllm','diagnose_','drill_')
    protected += [name for name in git('ls-tree','-r','--name-only','stage-5-release-candidate','scripts').splitlines() if Path(name).name.startswith(execution_prefixes)]
    for name in protected:
        assert subprocess.check_output(['git','show','stage-5-release-candidate:'+name],cwd=clone)==(clone/name).read_bytes(),name
    result['s5_protected_files_unchanged']=len(protected)
    versions=json.loads((clone/'reports/stage-versions.json').read_text())
    for version in versions['accepted_versions']:
        assert git('rev-parse',version['tag']+'^{}')==version['commit']
    result['verified_stage_tags']=versions['accepted_versions']
    wheel=next(line for line in (clone/'requirements/cpu-http.txt').read_text().splitlines() if line.startswith('aiohttp @ ')).split('/wheelhouse/',1)[1].split('#',1)[0]
    restore=out/'wheel-restore.json'
    run('oss_wheel_restore',[sys.executable,'scripts/restore_models_oss.py','--receipt','reports/s5-base-wheels-oss.json','--destination',str(out/'wheels'),'--include','assets/w/'+wheel,'--report',str(restore)])
    proof=json.loads(restore.read_text());assert proof['status']=='completed' and len(proof['restored'])==1 and proof['restored'][0]['action']=='downloaded_and_restored'
    result['fresh_oss_wheel']=dict(report=restore.name,sha256=sha(restore),member=proof['restored'][0])
    log=run('fresh_cpu_bootstrap',[sys.executable,'scripts/bootstrap_cpu.py','--env',str(env),'--http-tests','--wheelhouse',str(out/'wheels'),'--index',a.index])
    assert 'Ran 39 tests' in log.read_text() and 'skipped=' not in log.read_text() and '\nOK' in log.read_text()
    python=str(env/'bin/python')
    run('installed_identity',[python,'-c',"import importlib.metadata as m,importlib.util as u,driveserve,pathlib; assert m.version('driveserve')=='1.0.0'; assert m.version('aiohttp')=='3.14.5'; assert u.find_spec('torch') is None and u.find_spec('vllm') is None; assert pathlib.Path(driveserve.__file__).resolve().parent.parent==pathlib.Path.cwd(); print('1.0.0; aiohttp3.14.5; package resolves to independent checkout; no torch/vllm')"])
    run('demo',[python,'-m','driveserve','demo','--dataset','data/frozen-v1/dev.jsonl'])
    run('doctor',[python,'-m','driveserve','doctor'])
    run('gpu_bootstrap_help',[python,'scripts/bootstrap_gpu.py','--help'])
    run('s5_reaggregation',[python,'scripts/verify_s5_release.py','--checkout',str(clone),'--output',str(out/'s5-evidence'),'--python',python])
    replay=json.loads((out/'s5-evidence/readback.json').read_text());assert replay['status']=='passed' and replay['head']==head and replay['cpu_tests']==39
    result['s5_reaggregation']=dict(report='s5-evidence/readback.json',sha256=sha(out/'s5-evidence/readback.json'),exact_files=len(replay['reaggregations']),runs=replay['audit']['runs'])
    path=clone/'reports/release-assets.json';expected=sha(path)
    run('asset_index',[python,'scripts/index_release_assets.py','--output','reports/release-assets.json'])
    assert sha(path)==expected;result['asset_index_exact']=dict(path='reports/release-assets.json',sha256=expected)
    argv=[python,'scripts/audit_evidence.py','--through-stage','S6','--require-tracked','--report','artifacts/s6-release-readback/audit.json']
    for receipt in json.loads((clone/'configs/s5-asset-receipts.json').read_text())['receipts']:argv+=['--receipt',receipt]
    docs=['README.md','docs/progress.md','docs/coverage.md','docs/quickstart.md','docs/reproduce.md','docs/assets.md','docs/results-index.md','docs/final-report.md','docs/learning-guide.md',*[f'docs/stages/S6/{n}.md' for n in ['README','replay','resume','coverage','acceptance']]]
    for doc in docs:argv+=['--document',doc]
    run('s6_audit',argv)
    shutil.copyfile(clone/'artifacts/s6-release-readback/audit.json',out/'evidence-audit.json')
    audit=json.loads((out/'evidence-audit.json').read_text());assert audit['status']=='passed'
    result['s6_audit']=dict(report='evidence-audit.json',sha256=sha(out/'evidence-audit.json'),runs=len(audit['runs']),storage=audit['storage'])
    assert not git('status','--porcelain'),'verification changed tracked content'
    result.update(status='passed',clean_after=True,cpu_tests=39,verified_at=datetime.now(timezone.utc).isoformat());save()
except BaseException as e:
    result.update(status='failed',error=repr(e),verified_at=datetime.now(timezone.utc).isoformat());save();raise
print(json.dumps(dict(status=result['status'],head=head,cpu_tests=39,s5_exact_files=result['s5_reaggregation']['exact_files'],runs=result['s6_audit']['runs'])))
