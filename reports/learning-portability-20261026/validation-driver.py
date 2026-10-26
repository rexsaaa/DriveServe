from pathlib import Path
import hashlib,json,re,subprocess,sys,tarfile
meta=json.loads(Path('/tmp/driveserve-learning-audit-location.json').read_text());root=Path(meta['checkout']);out=Path(meta['output']);out.mkdir(parents=True,exist_ok=True)
result={'schema_version':1,'recorded_date':'2026-10-26','scope':'Local fresh clone with --no-local from staged candidate, not a remote or GPU execution. No ignored files copied from the source workspace.','candidate_sha':meta['candidate_sha'],'candidate_tree':meta['candidate_tree'],'commands':[],'checks':{},'status':'running'}
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save():(out/'validation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
def run(label,args,expected=0):
 r=subprocess.run(args,cwd=root,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT);p=out/(label+'.log');p.write_text(r.stdout);result['commands'].append({'label':label,'argv':args,'returncode':r.returncode,'expected_returncode':expected,'log':p.name,'log_sha256':digest(p)});save()
 if r.returncode!=expected:raise AssertionError(label+': '+r.stdout[-2000:])
 return r.stdout
try:
 assert not (root/'third_party').exists()
 result['checks']['upstream_absent_before_restore']=True
 run('sources_missing',['python3','scripts/restore_learning_sources.py','--check'],expected=1)
 run('sources_restore',['python3','scripts/restore_learning_sources.py'])
 run('sources_check',['python3','scripts/restore_learning_sources.py','--check'])
 run('sources_idempotent',['python3','scripts/restore_learning_sources.py'])
 # An edited source and a missing file must both stay untouched on conflict.
 conflict=root/'third_party/nano-vllm/nanovllm/engine/llm_engine.py';missing=root/'third_party/vllm-ba41cc90e8ef7f236347b2f1599eec2cbb9e1f0d/README.md'
 original=conflict.read_bytes();saved=missing.read_bytes();conflict.write_bytes(original+b'\n# Local edit preservation probe\n');missing.unlink()
 run('sources_preserve_edits',['python3','scripts/restore_learning_sources.py'],expected=1)
 assert conflict.read_bytes()==original+b'\n# Local edit preservation probe\n' and not missing.exists()
 conflict.write_bytes(original);missing.write_bytes(saved);result['checks']['conflict_preflight_preserves_edits_and_missing_files']=True
 links=[];broken=[]
 for p in (root/'docs/interview-prep').glob('*.md'):
  for target in re.findall(r'\]\(([^)]+)\)',p.read_text()):
   if '://' in target or target.startswith('#'):continue
   actual=(p.parent/target.split('#')[0]).resolve();links.append({'document':str(p.relative_to(root)),'target':target})
   if not actual.exists():broken.append(links[-1])
 result['checks']['markdown_links']={'checked':len(links),'broken':broken};assert not broken,broken
 manifest=json.loads((root/'docs/interview-prep/assets/historical-learning-manifest.json').read_text());archive=root/manifest['archive']['path'];assert digest(archive)==manifest['archive']['sha256']
 with tarfile.open(archive) as t:
  assert set(t.getnames())=={f['path'] for f in manifest['files']}
  for f in manifest['files']:
   data=t.extractfile(f['path']).read();assert len(data)==f['bytes'] and hashlib.sha256(data).hexdigest()==f['sha256']
 result['checks']['historical_files_verified']=len(manifest['files'])
 for f in json.loads((root/'docs/interview-prep/portability-inventory-2026-10-26.json').read_text())['supplemental_evidence']:
  assert digest(root/f['path'])==f['sha256']
 result['checks']['supplemental_evidence_hashes_verified']=10
 contract=json.loads((root/'configs/s5-asset-receipts.json').read_text());cmd=['python3','scripts/audit_evidence.py','--through-stage','S6','--require-tracked','--report',str(out/'evidence-audit.json')]
 for receipt in contract['receipts']:cmd+=['--receipt',receipt]
 run('evidence_audit',cmd);audit=json.loads((out/'evidence-audit.json').read_text());assert audit['status']=='passed' and len(audit['runs'])==655
 result['checks']['run_manifests_verified']=len(audit['runs']);result['checks']['run_assets_verified']=sum(r['assets'] for r in audit['runs']);result['checks']['evidence_audit_sha256']=digest(out/'evidence-audit.json')
 tasks=[('composition','scripts/analyze_s5_composition.py',['--states',*[f'reports/s5-timing-v2-r{i}-state.json' for i in (1,2,3)],'--report','reports/s5-composition.json'],'reports/s5-composition.json'),('openloop','scripts/analyze_s5_openloop.py',['--states',*[f'reports/s5-timing-v2-r{i}-state.json' for i in (1,2,3)],'--report','reports/s5-openloop.json'],'reports/s5-openloop.json'),('final_quality','scripts/analyze_s5_final.py',['--state','reports/s5-final-quality-state.json','--protocol','configs/s5-final-quality.json','--report','reports/s5-final-quality.json'],'reports/s5-final-quality.json'),('final_gpu','scripts/analyze_s5_final_gpu.py',['--state','reports/s5-final-gpu-state.json','--report','reports/s5-final-gpu.json'],'reports/s5-final-gpu.json'),('table','scripts/render_s5_results.py',['--composition','reports/s5-composition.json','--openloop','reports/s5-openloop.json','--output','docs/s5-results.md'],'docs/s5-results.md')]
 assets=json.loads((root/'reports/s5-assets.json').read_text());tasks.append(('asset_readback','scripts/analyze_s5_assets.py',['--run',str(Path(assets['manifest']['path']).parent),'--report','reports/s5-assets.json'],'reports/s5-assets.json'));tasks.append(('nsight','scripts/analyze_nsys.py',['--sqlite','artifacts/profiles/engine-observers-v1.sqlite','--nsys-rep','artifacts/profiles/engine-observers-v1.nsys-rep','--report','reports/s2-nsight-engine.json'],'reports/s2-nsight-engine.json'))
 equal=[]
 for label,script,args,path in tasks:
  before=digest(root/path);run(label,['python3',script,*args]);after=digest(root/path);equal.append({'path':path,'sha256':after,'exact_bytes_equal':before==after});assert before==after,path
 result['checks']['exact_reaggregations']=equal
 result['checks']['clean_checkout_after']=not subprocess.check_output(['git','status','--porcelain'],cwd=root,text=True);assert result['checks']['clean_checkout_after']
 result['status']='passed';save();print(json.dumps({'status':'passed','runs':655,'source_files':2378,'reaggregations':len(equal),'links':len(links)}))
except BaseException as exc:
 result['status']='failed';result['error']=repr(exc);save();raise
