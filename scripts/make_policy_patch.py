"""Rebuild the complete policy overlay patch against the fixed upstream source."""
import difflib
import hashlib
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
lock = json.loads((root / 'patches/vllm-v0.8.5-observers.json').read_text())
upstream = root / 'third_party' / ('vllm-' + lock['vllm_commit'])
# Observer suffixes are sourced from the checked existing patch, not site-packages.
observer_suffixes = {}
for part in (root / 'patches' / lock['patch']).read_text().split('--- a/')[1:]:
    path = part.splitlines()[0]
    observer_suffixes[path] = '\n'.join(line[1:] for line in part.splitlines() if line.startswith('+') and not line.startswith('+++')) + '\n'
paths = list(observer_suffixes) + ['vllm/core/block/prefix_caching_block.py']
patches, entries = [], []
for name in paths:
    original = (upstream / name).read_text()
    modified = original + observer_suffixes.get(name, '')
    def replace(old, new):
        global modified
        assert modified.count(old) == 1, (name, old, modified.count(old))
        modified = modified.replace(old, new)
    if name.endswith('/scheduler.py'):
        replace('        self.waiting.append(seq_group)\n', '        if _driveserve_length_aging:\n            _driveserve_register_arrival(seq_group)\n        self.waiting.append(seq_group)\n')
        replace('        seq_groups: List[ScheduledSequenceGroup] = []\n\n        waiting_queue = self.waiting\n', '        seq_groups: List[ScheduledSequenceGroup] = []\n\n        if _driveserve_length_aging:\n            _driveserve_order_waiting(self, enable_chunking)\n        waiting_queue = self.waiting\n')
        replace('            # It assumes the scheduled_seq_groups is ordered by\n', '            if (is_first_prefill and _driveserve_reuse_enabled\n                    and not self.scheduler_config.chunked_prefill_enabled):\n                _driveserve_record_reuse(self.block_manager, seq_group,\n                                         common_computed_block_nums)\n\n            # It assumes the scheduled_seq_groups is ordered by\n')
        modified += '''\n# DriveServe policies: explicit opt-in; native allocation/budget checks retained.\n_driveserve_length_aging = _driveserve_os.environ.get("DRIVESERVE_LENGTH_AGING") == "1"\n_driveserve_reuse_enabled = (_driveserve_os.environ.get("DRIVESERVE_CACHE_POLICY") == "cold_hot"\n                             or bool(_driveserve_os.environ.get("DRIVESERVE_TRACE_DIR")))\nfrom driveserve.engine_policies import (order_waiting as _driveserve_order_waiting,\n    register_arrival as _driveserve_register_arrival, record_prefix_reuse as _driveserve_record_reuse)\n'''
    elif name.endswith('/prefix_caching_block.py'):
        # Preserve the continuous RUNNING prefill cache, refresh WAITING after eviction.
        replace('from vllm.sequence import Sequence\n', 'from vllm.sequence import Sequence, SequenceStatus\n')
        replace('        if num_computed_tokens_prev is not None and seq.is_prefill():\n',
                '        if (num_computed_tokens_prev is not None and seq.is_prefill()\n'
                '                and seq.status == SequenceStatus.RUNNING):\n')
        # Rename import only: both constructor and reset use this local factory.
        replace('from vllm.core.evictor import EvictionPolicy, Evictor, make_evictor', 'from vllm.core.evictor import EvictionPolicy, Evictor, make_evictor as _native_make_evictor')
        modified += '''\n\n# DriveServe opt-in replacement; unchanged native allocator owns refs and hashes.\nimport os as _driveserve_os\nfrom driveserve.engine_policies import make_policy_evictor as _policy_make_evictor\ndef make_evictor(eviction_policy):\n    policy = _driveserve_os.environ.get("DRIVESERVE_CACHE_POLICY", "native")\n    if policy == "cold_hot":\n        return _policy_make_evictor()\n    if policy != "native":\n        raise ValueError("unknown DriveServe cache policy")\n    return _native_make_evictor(eviction_policy)\n'''
    patches.extend(difflib.unified_diff(original.splitlines(True), modified.splitlines(True), fromfile='a/'+name, tofile='b/'+name))
    entries.append({'path':name, 'upstream_sha256':hashlib.sha256(original.encode()).hexdigest(), 'patched_sha256':hashlib.sha256(modified.encode()).hexdigest()})
(root/'patches/vllm-v0.8.5-policies.patch').write_text(''.join(patches))
lock.update(patch='vllm-v0.8.5-policies.patch', files=entries)
(root/'patches/vllm-v0.8.5-policies.json').write_text(json.dumps(lock, indent=2)+'\n')
