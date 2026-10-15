"""Compare two complete AWQ exports and map equal content to verified OSS objects."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path.cwd()))
from driveserve.evidence import atomic_json,file_hash,now,verify_assets
p=argparse.ArgumentParser();p.add_argument('--baseline',type=Path,required=True);p.add_argument('--repeat',type=Path,required=True)
p.add_argument('--receipt',type=Path,required=True);p.add_argument('--report',type=Path,required=True);args=p.parse_args()
manifests=[];exports=[];sensitivity=[]
for folder in [args.baseline,args.repeat]:
 m=json.load(open(folder/'manifest.json'));assert m['status']=='completed';verify_assets(Path.cwd(),m);manifests.append(m)
 exp=json.load(open(folder/'export.json'));exports.append({Path(f['path']).name:f for f in exp['files']})
 layers=[json.load(open(f)) for f in sorted(folder.glob('layer-*.json'))];assert len(layers)==28
 sensitivity.append([r for layer in layers for r in layer['sensitivity']])
assert manifests[0]['run_id']!=manifests[1]['run_id']
for key in ['model','data','source','quant_config','seed','calibration','sensitivity','layer_manifest']:
 assert manifests[0]['config'][key]==manifests[1]['config'][key],key+' changed'
assert exports[0].keys()==exports[1].keys()
receipt=json.load(open(args.receipt));assert receipt['status']=='completed'
objects={i['name']:i for i in receipt['plan']['items']}
rows=[]
for name,base in exports[0].items():
 repeat=exports[1][name]
 for f in [base,repeat]:assert Path(f['path']).stat().st_size==f['bytes'] and file_hash(f['path'])==f['sha256']
 equal=base['bytes']==repeat['bytes'] and base['sha256']==repeat['sha256']
 object=objects['assets/domain-g128/'+name]
 assert object['sha256']==base['sha256'] and receipt['verified'][object['object']]['content_sha256']==base['sha256']
 rows.append({'name':name,'bytes':repeat['bytes'],'baseline_sha256':base['sha256'],'repeat_sha256':repeat['sha256'],
              'exact_equal':equal,'existing_verified_object':object['object'] if equal else None})
assert len(sensitivity[0])==len(sensitivity[1])==21
comparison=[]
for a,b in zip(*sensitivity):
 assert (a['layer'],a['name'])==(b['layer'],b['name'])
 comparison.append({'layer':a['layer'],'name':a['name'],'exact_equal':a==b,
                    'relative_mse_absolute_difference':abs(a['relative_mse']-b['relative_mse'])})
result={'verified_at':now(),'baseline_run':manifests[0]['run_id'],'repeat_run':manifests[1]['run_id'],
 'same_recipe_data_seed_model':True,'files':rows,'all_export_files_exact_equal':all(r['exact_equal'] for r in rows),
 'sensitivity':comparison,'all_local_error_records_exact_equal':all(r['exact_equal'] for r in comparison),
 'repeat_provenance':str(args.repeat/'export.json'),'repeat_provenance_sha256':file_hash(args.repeat/'export.json'),
 'storage_policy':'Equal content reuses the referenced verified OSS object; distinct run provenance remains in Git. Different files require new backup before acceptance.',
 'limits':['Two complete calibrations on this recorded environment; not a guarantee across seeds, versions, or hardware.',
           'This compares export and local calibration distortion, not additional held-out model quality.',
           'Existing full OSS readback receipts are verified; no second duplicate upload or new remote readback is claimed.']}
atomic_json(args.report,result)
print(json.dumps({k:result[k] for k in ['baseline_run','repeat_run','all_export_files_exact_equal','all_local_error_records_exact_equal']},indent=2))
