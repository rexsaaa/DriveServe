"""Recheck S4 from a separately fetched, clean GitHub checkout; no new GPU run."""
import argparse,hashlib,json,shutil,subprocess,sys
from datetime import datetime,timezone
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--checkout',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
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
 run('cpu',[sys.executable,'-m','unittest','discover','-s','tests','-v'])
 assert 'Ran 28 tests' in (out/'cpu.log').read_text()
 checks=[('stability',[sys.executable,'scripts/analyze_s4_replication.py','--states',*[f'reports/s4-timing-r{i}-state.json' for i in [1,2,3]],'--report','reports/s4-depth.json'],['reports/s4-depth.json']),
 ('boundaries',[sys.executable,'scripts/analyze_s4_boundaries.py','--state','reports/s4-boundaries-state.json','--report','reports/s4-boundaries.json'],['reports/s4-boundaries.json']),
 ('table',[sys.executable,'scripts/render_s4_depth.py','--report','reports/s4-depth.json','--output','docs/s4-depth-results.md'],['docs/s4-depth-results.md'])]
 for label,argv,paths in checks:
  before={s:sha(clone/s) for s in paths};run(label,argv)
  for s in paths:
   current=sha(clone/s);result['reaggregations'].append({'path':s,'expected_sha256':before[s],'actual_sha256':current,'exact_bytes_equal':current==before[s]});assert current==before[s],s
 receipts=['s1-oss-models-receipt','s1-environment-receipt','s2-teacher-oss-receipt','s2-training-recovery-oss','s2-trained-assets-oss','s2-awq-g128-oss','s2-awq-g64-oss']
 docs=['README.md','docs/coverage.md',*[f'docs/stages/S4/{x}.md' for x in ['README','replay','resume','coverage','acceptance']]]
 argv=[sys.executable,'scripts/audit_evidence.py','--through-stage','S4','--require-tracked','--report','artifacts/s4-release-readback/evidence-audit.json']
 for s in receipts:argv+=['--receipt','reports/'+s+'.json']
 for s in docs:argv+=['--document',s]
 run('audit',argv);src=clone/'artifacts/s4-release-readback/evidence-audit.json';shutil.copyfile(src,out/'evidence-audit.json')
 audit=json.loads(src.read_text());assert audit['status']=='passed';result['audit']={'path':'evidence-audit.json','sha256':sha(out/'evidence-audit.json'),'runs':len(audit['runs']),'storage':audit['storage']}
 assert not git('status','--porcelain'),'reaggregation changed tracked files'
 result.update(status='passed',clean_checkout_after=True,cpu_tests=28,verified_at=datetime.now(timezone.utc).isoformat());save()
except BaseException as e:
 result.update(status='failed',error=repr(e),verified_at=datetime.now(timezone.utc).isoformat());save();raise
print(json.dumps({'status':result['status'],'head':head,'reaggregations':len(result['reaggregations']),'runs':result['audit']['runs']}))
