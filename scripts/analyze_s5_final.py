"""Frozen final quality decisions, recomputed from saved outputs and rule labels."""
import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path.cwd()))
from driveserve.evidence import atomic_json,file_hash,verify_assets
from driveserve.task import score
p=argparse.ArgumentParser();p.add_argument('--state',type=Path,required=True);p.add_argument('--protocol',type=Path,required=True);p.add_argument('--report',type=Path,required=True);a=p.parse_args()
protocol=json.load(open(a.protocol));state=json.load(open(a.state));assert state['status']=='completed' and state['stage']=='S5'
plan=json.load(open(state['plan']));assert file_hash(state['plan'])==state['plan_sha256']
assert file_hash(protocol['test_data']['path'])==protocol['test_data']['sha256'];dataset=[json.loads(line) for line in Path(protocol['test_data']['path']).read_text().splitlines()]
scenes={r['scene']['scene_id']:r['scene'] for r in dataset};assert len(scenes)==len(dataset)==protocol['test_data']['records']==256
assert all(r['split']=='test' for r in dataset)
profiles={};raw={};seen=set()
for task in plan['tasks']:
 completed=[x for x in state['attempts'] if x['label']==task['label'] and x['status']=='completed'];assert len(completed)==1
 attempt=completed[0];wm=json.load(open(attempt['wrapper_manifest']));verify_assets(Path.cwd(),wm)
 assert wm['status']=='completed' and wm['code']['sha']==state['code_sha'] and not wm['code']['dirty']
 assert len(attempt['inner_manifests'])==1;p=Path(attempt['inner_manifests'][0]);folder=p.parent;m=json.load(open(p));verify_assets(Path.cwd(),m)
 cfg=m['config'];name=cfg['final_profile'];assert name in protocol['profiles'] and name not in profiles
 assert m['status']=='completed' and m['code']['sha']==state['code_sha'] and not m['code']['dirty']
 assert cfg['final_protocol']['sha256']==file_hash(a.protocol) and cfg['data']['split']=='test' and cfg['data']['selected']==256
 work=json.load(open(folder/'workload.json'));results=json.load(open(folder/'results.json'));assert len(work)==len(results)==256
 assert len({r['request_id'] for r in work})==len({r['request_id'] for r in results})==256
 assert {r['scene']['scene_id'] for r in work}==set(scenes)
 by_id={r['request_id']:r for r in work};quality=[]
 for r in results:
  w=by_id[r['request_id']];assert w['scene']==scenes[w['scene']['scene_id']] and w['kind']=='quality' and w['split']=='test'
  actual=score(w['scene'],r['text']);assert actual==r['quality'];quality.append(actual)
 assert all(r['status']=='completed' for r in results)
 raw[name]={r['request_id']:r for r in results}
 profiles[name]=dict(run_id=m['run_id'],code_sha=m['code']['sha'],manifest_sha256=file_hash(p),
  workload_sha256=file_hash(folder/'workload.json'),completed=len(results),json_valid=sum(q['json_valid'] for q in quality),
  exact_correct=sum(q['exact_match'] for q in quality),field_correct={k:sum(q['fields'][k] for q in quality) for k in ['action','speed_band','must_yield']},
  incorrect_ids=[r['request_id'] for r in results if not r['quality']['exact_match']],
  sampling_reference=protocol['profiles'][name]['sampling_reference'],quality_reference=protocol['profiles'][name]['quality_reference'])
assert set(profiles)==set(protocol['profiles'])
gates=protocol['quality_gate']
for name,r in profiles.items():
 ref=profiles[r['quality_reference']];r['correct_count_difference']=r['exact_correct']-ref['exact_correct']
 r['quality_gate_passed']=(r['completed']==gates['required_completed'] and r['json_valid']==gates['required_json_valid']
   and r['correct_count_difference']>=-gates['maximum_correct_count_drop'])
 baseline=raw[r['sampling_reference']]
 differences=[rid for rid,row in raw[name].items() if row['output_token_ids']!=baseline[rid]['output_token_ids'] or row['finish_reason']!=baseline[rid]['finish_reason']]
 r.update(same_reference_tokens_and_finish=256-len(differences),token_different_ids=differences,
    exact_greedy_gate_required=protocol['profiles'][name]['exact_greedy_reference_required'])
 r['eligible_for_recommendation']=r['quality_gate_passed'] and (not r['exact_greedy_gate_required'] or not differences)
 def parsed(row):
  return dict(valid=True,value=json.loads(row['text'])) if row['quality']['json_valid'] else dict(valid=False,text=row['text'])
 r['sampling_reference_parsed_different_ids']=sorted(rid for rid,row in raw[name].items() if parsed(row)!=parsed(baseline[rid]))
 qref=raw[r['quality_reference']]
 r['quality_reference_field_different_ids']=sorted(rid for rid,row in raw[name].items() if row['quality']!=qref[rid]['quality'])
 r['quality_reference_incorrect_ids_equal']=(set(r['incorrect_ids'])==set(profiles[r['quality_reference']]['incorrect_ids']))
 r['sampling_reference_token_differences']=[dict(request_id=rid,baseline_text=baseline[rid]['text'],candidate_text=raw[name][rid]['text'],
  parsed_equal=parsed(baseline[rid])==parsed(raw[name][rid]),finish_equal=baseline[rid]['finish_reason']==raw[name][rid]['finish_reason']) for rid in differences]

base=profiles['fp16-target'];base_ok=base['quality_gate_passed'] and base['exact_correct']>=gates['baseline_minimum_exact_correct']
atomic_json(a.report,dict(aggregator_sha256=file_hash(__file__),state=dict(path=str(a.state),sha256=file_hash(a.state)),
 protocol=dict(path=str(a.protocol),sha256=file_hash(a.protocol)),source_sha=state['code_sha'],profiles=profiles,
 baseline_engineering_floor_passed=base_ok,default='fp16-target' if base_ok else None,
 decision_scope='Passing quality is necessary, not sufficient for a speed/memory/SLO recommendation; negative-speed combinations remain disabled.',
 limits=protocol['limitations']+['At most2/256 tolerated loss is an engineering rule, not a statistical or safety guarantee.',
 'Token equality is finite greedy evidence only; quantized speculation references its quantized Target.']))
print(json.dumps(dict(profiles=len(profiles),baseline_floor=base_ok,counts={k:r['exact_correct'] for k,r in profiles.items()})))
