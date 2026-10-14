"""Minimal real-upstream regression: a waiting lookup must not survive eviction."""
import argparse
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from vllm.core.block.cpu_gpu_block_allocator import CpuGpuBlockAllocator
from vllm.core.block.prefix_caching_block import ComputedBlocksTracker
from vllm.sequence import Sequence
from vllm.utils import Device
p=argparse.ArgumentParser();p.add_argument('--expect-stale',action='store_true');args=p.parse_args()
a=CpuGpuBlockAllocator.create('prefix_caching',2,0,4)
g=a._allocators[Device.GPU]
b=g.allocate_immutable_block(None,[1]*4);g.mark_blocks_as_computed([]);g.free(b)
s=Sequence(0,{'type':'token','prompt_token_ids':[1]*4},4)
t=ComputedBlocksTracker(a,4,True)
first=t.get_num_cached_tokens(s)
assert first==4
for value in [2,3]:
 b=g.allocate_immutable_block(None,[value]*4);g.mark_blocks_as_computed([]);g.free(b)
second=t.get_num_cached_tokens(s)
print({'first_cached':first,'after_eviction_cached':second,'expected':0,'stale':second!=0},flush=True)
assert second==(4 if args.expect_stale else 0)
