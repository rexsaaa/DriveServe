"""Exercise the public CUDA wrapper's declared invalid-input boundaries."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path.cwd()))
from driveserve.evidence import Run, atomic_json

p=argparse.ArgumentParser()
p.add_argument('--stage',choices=['S3','S4','S5'],default='S3')
p.add_argument('--variant',choices=['baseline','auto','scalar','half2'],default='baseline')
options=p.parse_args()
run = Run(Path.cwd(), 'rope-input-contract', {'stage': options.stage, 'variant': options.variant,
    'requirement_ids': ['M5-03'], 'hypothesis': 'unsupported layouts and indices fail without mutating valid storage',
    'scope': 'FP16 Q28/KV4/D128 public fused wrapper; diagnostic, not performance'}, formal=True)
print(run.path, flush=True)
try:
    import torch
    from driveserve.rope_cache import fused, extension
    if options.variant!='baseline':
        from functools import partial
        from driveserve.rope_cache import fused_v2
        fused=partial(fused_v2,variant=options.variant)
    torch.manual_seed(91)
    extension()

    def fresh():
        return [torch.randn(2,36,128,device='cuda',dtype=torch.float16),
                torch.tensor([0,31],device='cuda',dtype=torch.int64),
                torch.randn(32,128,device='cuda',dtype=torch.float16),
                torch.full((2,2,16,4,128),-19.5,device='cuda',dtype=torch.float16),
                torch.tensor([0,31],device='cuda',dtype=torch.int64)]

    def replace(index, operation):
        def change(args):
            args[index] = operation(args[index])
        return change

    def alias(args):
        storage = torch.randn(32768, device='cuda', dtype=torch.float16)
        args[0] = storage[:9216].view(2,36,128)
        args[3] = storage.view(2,2,16,4,128)

    def index_alias(index, target):
        def mutate(args):
            args[index]=args[target].view(-1).view(torch.int64)[:2]
            args[index].copy_(torch.tensor([0,31],device='cuda'))
        return mutate

    mutations = [
        ('fp32_projection', replace(0, lambda t:t.float())),
        ('bf16_table', replace(2, lambda t:t.bfloat16())),
        ('fp32_cache', replace(3, lambda t:t.float())),
        ('int32_positions', replace(1, lambda t:t.int())),
        ('int32_slots', replace(4, lambda t:t.int())),
        ('wrong_head_count', replace(0, lambda t:t[:,:35])),
        ('nonunit_dim_stride', replace(0, lambda t:torch.randn(2,36,256,device='cuda',dtype=t.dtype)[...,::2])),
        ('nonpacked_heads', replace(0, lambda t:torch.randn(2,72,128,device='cuda',dtype=t.dtype)[:,::2,:])),
        ('overlapping_token_rows', replace(0, lambda t:t[:1].expand(2,-1,-1))),
        ('position_length', replace(1, lambda t:t[:1])),
        ('noncontiguous_positions', replace(1, lambda t:torch.tensor([0,99,31,99],device='cuda')[::2])),
        ('noncontiguous_table', replace(2, lambda t:t.T)),
        ('noncontiguous_cache', replace(3, lambda t:t.transpose(0,1))),
        ('unsupported_block_size', replace(3, lambda t:torch.zeros(2,2,8,4,128,device='cuda',dtype=t.dtype))),
        ('cpu_positions', replace(1, lambda t:t.cpu())),
        ('negative_position', replace(1, lambda t:torch.tensor([-1,0],device='cuda'))),
        ('past_position', replace(1, lambda t:torch.tensor([0,32],device='cuda'))),
        ('past_slot', replace(4, lambda t:torch.tensor([0,32],device='cuda'))),
        ('duplicate_slot', replace(4, lambda t:torch.tensor([1,1],device='cuda'))),
        ('projection_cache_alias', alias),
        ('positions_projection_alias',index_alias(1,0)),
        ('positions_cache_alias',index_alias(1,3)),
        ('slots_projection_alias',index_alias(4,0)),
        ('slots_cache_alias',index_alias(4,3)),
    ]
    records = []
    for name, mutate in mutations:
        args = fresh()
        mutate(args)
        before = [t.clone() for t in args]
        try:
            fused(*args)
            torch.cuda.synchronize()
        except (ValueError, RuntimeError) as exc:
            torch.cuda.synchronize()
            for actual, expected in zip(args, before):
                torch.testing.assert_close(actual, expected, atol=0, rtol=0)
            records.append({'case':name,'rejected':True,'error':str(exc),'no_input_mutation':True})
        else:
            raise AssertionError(f'unsupported input accepted: {name}')
        atomic_json(run.path/'rejected.json', records)

    args = fresh()
    args[4] = torch.tensor([-1,-17], device='cuda')
    cache_before = args[3].clone()
    fused(*args)
    torch.cuda.synchronize()
    torch.testing.assert_close(args[3], cache_before, atol=0, rtol=0)
    # Shared read-only positions/slots remain supported; distinct valid slots.
    args=fresh();args[4]=args[1]
    reference=[t.clone() for t in args]
    extension().fused(*reference)
    fused(*args);torch.cuda.synchronize()
    for actual,expected in zip(args,reference):torch.testing.assert_close(actual,expected,atol=0,rtol=0)
    run.finish('completed', {'read_only_index_alias_matches_disjoint_reference':True,'invalid_cases':len(records), 'all_negative_slots_leave_cache_unchanged':True,
        'limits':['finite representative values; not all bit patterns or arbitrary dtype/layout support',
                  'no invalid out-of-bounds launch is deliberately issued; checks execute before kernel launch']})
except BaseException as exc:
    run.finish('failed', {'error':str(exc)})
    raise
