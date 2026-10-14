"""Compare full training states at equal steps; exclude wall-clock metadata."""
import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path.cwd()))
from driveserve.evidence import atomic_json,file_hash
import torch
p=argparse.ArgumentParser();p.add_argument('--reference',type=Path,required=True);p.add_argument('--resumed',type=Path,required=True);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
def read(root):
 pointer=json.load(open(root/'latest.json'));folder=root/pointer['directory']
 assert file_hash(folder/'checkpoint.json')==pointer['manifest_sha256']
 for item in json.load(open(folder/'checkpoint.json'))['files']:assert file_hash(folder/item['name'])==item['sha256']
 return torch.load(folder/'state.pt',weights_only=False,map_location='cpu'),str(folder),file_hash(folder/'state.pt')
a,ap,ah=read(args.reference);b,bp,bh=read(args.resumed)
def equal(x,y):
 if isinstance(x,torch.Tensor):return isinstance(y,torch.Tensor) and torch.equal(x,y)
 if isinstance(x,dict):return x.keys()==y.keys() and all(equal(x[k],y[k]) for k in x)
 if isinstance(x,(list,tuple)):return len(x)==len(y) and all(equal(i,j) for i,j in zip(x,y))
 return x==y
checks={k:equal(a[k],b[k]) for k in ['identity','order_hash','step','cursor','adapter','optimizer','scheduler','python_rng','cpu_rng','cuda_rng']}
checks['loss_lr_samples'] = equal([{k:v for k,v in r.items() if k!='elapsed_s'} for r in a['history']], [{k:v for k,v in r.items() if k!='elapsed_s'} for r in b['history']])
report={'reference':{'path':ap,'sha256':ah},'resumed':{'path':bp,'sha256':bh},'step':a['step'],'checks':checks,'all_equal':all(checks.values()),'scope':'same hardware, same full scheduler horizon; tensor bitwise equality, timing metadata excluded'}
atomic_json(args.output,report);print(json.dumps(report,indent=2));assert report['all_equal']
