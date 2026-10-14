from pathlib import Path
import argparse,hashlib,json,subprocess,sys
sys.path.insert(0,str(Path.cwd()))
from driveserve.evidence import atomic_json,file_hash,verify_assets
parser=argparse.ArgumentParser()
parser.add_argument('--reference',type=Path,required=True)
parser.add_argument('--candidates',type=Path,nargs='+',required=True)
parser.add_argument('--report',type=Path,required=True)
parser.add_argument('--protocol-commit',default='5bcc38de6f0712bab48fdf5055bd2b426d8989d2')
args=parser.parse_args()
root=Path.cwd()
reference=args.reference
expected={r['request_id']:r['output_token_ids'] for r in json.load(open(reference/'results.json'))}
refhash=file_hash(reference/'workload.json')
paths=[reference]+args.candidates
assert len(paths)==5, 'frozen budget: eager reference, untouched B0, three Graph candidates'
rows=[]
for path in paths:
 m=json.load(open(path/'manifest.json'));assert m['status']=='completed';verify_assets(root,m)
 data=json.load(open(path/'results.json'));out={r['request_id']:r['output_token_ids'] for r in data}
 missing=sorted(set(out)^set(expected));different=sorted(k for k in set(out)&set(expected) if out[k]!=expected[k])
 same_workload=file_hash(path/'workload.json')==refhash
 elapsed=sum(x['elapsed_ns'] for x in json.load(open(path/'phases.json')))/1e9
 rows.append({'run_id':m['run_id'],'sha':m['code']['sha'],'upstream':m['config'].get('upstream',False),
  'eager':m['config']['eager'],'max_num_seqs':m['config']['max_num_seqs'],'requests':len(data),
  'same_workload':same_workload,'missing_ids':missing,'different_ids':different,'elapsed_s':elapsed,
  'output_tokens_per_s':sum(len(r['output_token_ids']) for r in data)/elapsed,
  'eligible':not (missing or different) and same_workload})
selected=min([r for r in rows if not r['upstream'] and r['eligible']],key=lambda r:r['elapsed_s'])
atomic_json(args.report,{'protocol':'docs/baseline-protocol.md',
 'protocol_git_sha':args.protocol_commit,
 'protocol_sha256':hashlib.sha256(subprocess.check_output(['git','show',args.protocol_commit+':docs/baseline-protocol.md'])).hexdigest(),
 'reference':reference.name,'candidates':rows,
 'selected':selected,'scope':'synthetic engine benchmark B1; initial single-run tuning; native strategies with common correctness fix',
 'rule':'identical greedy outputs then minimum sum of measured phase time; no candidate budget expansion'})
print(json.dumps({'candidates':rows,'selected':selected},indent=2))
