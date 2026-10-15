"""Limited standalone CUDA operator; not integrated into the serving engine."""

from functools import lru_cache
import os
from pathlib import Path


@lru_cache(maxsize=1)
def extension():
    from torch.utils.cpp_extension import load
    root = Path(__file__).resolve().parents[1]
    # Binary outputs belong to temporary storage and must be rebuilt on migration.
    build = Path(os.environ.get("DRIVESERVE_CUDA_BUILD", "/hy-tmp/driveserve/build/rope-cache-v1"))
    build.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("MAX_JOBS", "2")
    return load(name="driveserve_rope_cache_v1", sources=[str(root / "csrc/rope_cache.cpp"),
                str(root / "csrc/rope_cache.cu")], build_directory=str(build),
                extra_cflags=["-O3"], extra_cuda_cflags=["-O3", "-lineinfo"], verbose=True)


def validate_indices(positions, slots, position_capacity, slot_capacity):
    """Validate trusted launch data once, outside the timed region (synchronizes)."""
    p, s = positions.cpu(), slots.cpu()
    if p.numel() and (p.min().item() < 0 or p.max().item() >= position_capacity):
        raise ValueError("position outside cos/sin table")
    used = s[s >= 0]
    if used.numel() and used.max().item() >= slot_capacity:
        raise ValueError("slot outside KV cache")
    if used.unique().numel() != used.numel():
        raise ValueError("duplicate writable slots are not supported")


def reject_write_aliases(projection, positions, cos_sin, cache, slots):
    """Writable projection/cache must not share storage with any other input.

    Empty tensors do not access their storage. Positions and slots may share
    read-only storage; aliasing indices with writable data can corrupt later
    index reads even when every index passed the prelaunch range check.
    """
    tensors=[projection,positions,cos_sin,cache,slots]
    for writable in (0,3):
        left=tensors[writable]
        if not left.numel():
            continue
        for index,right in enumerate(tensors):
            if index!=writable and right.numel() and left.untyped_storage().data_ptr()==right.untyped_storage().data_ptr():
                raise ValueError('writable projection/cache must not alias any other input')


def fused(projection, positions, cos_sin, cache, slots):
    """Checked entry; writable storage must be disjoint from all other inputs."""
    reject_write_aliases(projection, positions, cos_sin, cache, slots)
    validate_indices(positions, slots, cos_sin.shape[0], cache.shape[1] * cache.shape[2])
    extension().fused(projection, positions, cos_sin, cache, slots)
