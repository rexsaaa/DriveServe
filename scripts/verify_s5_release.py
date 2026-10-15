"""Recheck S5 from a separately fetched, clean GitHub checkout; no new GPU run."""
import argparse,hashlib,json,re,shutil,subprocess,sys
from datetime import datetime,timezone
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--checkout',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--python',default='/hy-tmp/driveserve/venv-rebuilt/bin/python');a=p.parse_args()
clone=a.checkout.resolve();out=a.output.resolve();out.mkdir(parents=True,exist_ok=True)
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def git(*args):return subprocess.check_output(['git',*args],cwd=clone,text=True).strip()
assert not git('status','--porcelain'), 'checkout is not clean'
head=git('rev-parse','HEAD');origin=git('remote','get-url','origin');assert origin in ['git@github.com:rexsaaa/DriveServe.git','https://github.com/rexsaaa/DriveServe.git']
result={'head':head,'remote':origin,'clean_checkout_before':True,'status':'running','commands':[],
 'reaggregations':[],'limits':['Independent remote checkout: CPU checks and raw evidence reaggregation, not a new GPU experiment.',
 'OSS assets are covered by historical complete readbacks and separately recorded current restore probes; this checker makes no new model download.']}
def save():
 (out/'readback.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
def run(label,argv):
 log=out/(label+'.log')
 with log.open('w') as f:r=subprocess.run(argv,cwd=clone,stdout=f,stderr=subprocess.STDOUT)
 result['commands'].append({'label':label,'argv':argv,'code_sha':head,'returncode':r.returncode,'log':log.name,'log_sha256':sha(log)})
 save();r.check_returncode();return log
try:
 run('cpu',[a.python,'-m','unittest','discover','-s','tests','-v'])
 assert 'Ran 39 tests' in (out/'cpu.log').read_text() and 'skipped=' not in (out/'cpu.log').read_text()
 checks=[('composition',[a.python,'scripts/analyze_s5_composition.py','--states',*[f'reports/s5-timing-v2-r{i}-state.json' for i in [1,2,3]],'--report','reports/s5-composition.json'],['reports/s5-composition.json']),
 ('openloop',[a.python,'scripts/analyze_s5_openloop.py','--states',*[f'reports/s5-timing-v2-r{i}-state.json' for i in [1,2,3]],'--report','reports/s5-openloop.json'],['reports/s5-openloop.json']),
 ('final_quality',[a.python,'scripts/analyze_s5_final.py','--state','reports/s5-final-quality-state.json','--protocol','configs/s5-final-quality.json','--report','reports/s5-final-quality.json'],['reports/s5-final-quality.json']),
 ('final_gpu',[a.python,'scripts/analyze_s5_final_gpu.py','--state','reports/s5-final-gpu-state.json','--report','reports/s5-final-gpu.json'],['reports/s5-final-gpu.json']),
 ('table',[a.python,'scripts/render_s5_results.py','--composition','reports/s5-composition.json','--openloop','reports/s5-openloop.json','--output','docs/s5-results.md'],['docs/s5-results.md'])]
 assets=json.loads((clone/'reports/s5-assets.json').read_text());asset_run=str(Path(assets['manifest']['path']).parent)
 checks.append(('asset_readback',[a.python,'scripts/analyze_s5_assets.py','--run',asset_run,'--report','reports/s5-assets.json'],['reports/s5-assets.json']))
 for label,argv,paths in checks:
  before={s:sha(clone/s) for s in paths};run(label,argv)
  for s in paths:
   current=sha(clone/s);result['reaggregations'].append({'path':s,'expected_sha256':before[s],'actual_sha256':current,'exact_bytes_equal':current==before[s]});assert current==before[s],s
 composition=json.loads((clone/'reports/s5-composition.json').read_text())
 assert len(composition['records'])==30 and len(composition['run_level_statistics'])==10
 assert all(v['independent_processes']==3 for v in composition['run_level_statistics'].values())
 assert all(r['prefix_cache'] for r in composition['records'])
 assert len({r['execution_source_fingerprint'] for r in composition['records']})==1
 deployment=json.loads((clone/'reports/s5-openloop.json').read_text())
 assert deployment['independent_processes']==9 and len(deployment['records'])==36
 assert all(v['independent_runs']==3 for v in deployment['run_level_statistics'].values())
 assert sum(r['metrics']['requests'] for r in deployment['records'])==9216
 final=json.loads((clone/'reports/s5-final-quality.json').read_text())
 assert len(final['profiles'])==10 and final['baseline_engineering_floor_passed']
 assert all(r['completed']==256 for r in final['profiles'].values())
 gpu=json.loads((clone/'reports/s5-final-gpu.json').read_text());assert gpu['status']=='passed' and len(gpu['tasks'])==10
 contract=json.loads((clone/'configs/s5-asset-receipts.json').read_text())
 assert assets['status']=='passed' and assets['objects_listed']==contract['expected_objects']
 assert assets['archive_bytes']==contract['expected_archive_bytes'] and len(assets['small_files_freshly_restored'])==contract['expected_fresh_small_files']
 result['validated_scope']={'composition_processes':30,'deployment_processes':9,'http_attempts':9216,'final_profiles':10,'final_attempts':2560}
 wheel_receipt=json.loads((clone/contract['base_wheel_receipt']).read_text())
 wheels={Path(x['name']).name:x for x in wheel_receipt['plan']['items'] if x['name'].endswith('.whl')}
 locked=re.findall(r'file:///hy-tmp/driveserve/wheelhouse/([^#\s]+)#sha256=([0-9a-f]{64})',(clone/'requirements/gpu.lock.txt').read_text())
 assert len(wheels)==len(locked)==36 and {x[0] for x in locked}==set(wheels)
 assert all(wheels[name]['sha256']==checksum for name,checksum in locked)
 result['base_wheel_references_verified']=36
 receipts=contract['receipts']
 docs=['README.md','docs/coverage.md',*[f'docs/stages/S5/{x}.md' for x in ['README','replay','resume','coverage','acceptance']]]
 argv=[a.python,'scripts/audit_evidence.py','--through-stage','S5','--require-tracked','--report','artifacts/s5-release-readback/evidence-audit.json']
 for s in receipts:argv+=['--receipt',s]
 for s in docs:argv+=['--document',s]
 run('audit',argv);src=clone/'artifacts/s5-release-readback/evidence-audit.json';shutil.copyfile(src,out/'evidence-audit.json')
 audit=json.loads(src.read_text());assert audit['status']=='passed';result['audit']={'path':'evidence-audit.json','sha256':sha(out/'evidence-audit.json'),'runs':len(audit['runs']),'storage':audit['storage']}
 assert not git('status','--porcelain'),'reaggregation changed tracked files'
 result.update(status='passed',clean_checkout_after=True,cpu_tests=39,verified_at=datetime.now(timezone.utc).isoformat());save()
except BaseException as e:
 result.update(status='failed',error=repr(e),verified_at=datetime.now(timezone.utc).isoformat());save();raise
print(json.dumps({'status':result['status'],'head':head,'reaggregations':len(result['reaggregations']),'runs':result['audit']['runs']}))
