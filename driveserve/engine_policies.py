"""Opt-in V0 policies; no tensor, hash, reference-count or block-table mutation.

The pinned source patch calls record_prefix_reuse only for first prefills.
Cold/hot metadata counts full blocks actually skipped, not allocation/dedup hits.
"""
from dataclasses import dataclass
import os
import time

from driveserve.engine_trace import emit


@dataclass
class FreeBlock:
    content_hash: int
    num_hashed_tokens: int
    last_accessed: float


class ColdHotEvictor:
    """Zero-ref candidates only. O(free cached blocks) selection, O(resident) state."""
    def __init__(self, hot_threshold=2, hot_ttl_s=30.0, clock=time.monotonic):
        if hot_threshold < 1 or hot_ttl_s <= 0:
            raise ValueError("positive hot threshold and TTL required")
        self.free_table = {}
        self.reuse = {}
        self.hot_threshold, self.hot_ttl_s, self.clock = hot_threshold, hot_ttl_s, clock
        self.evictions = self.selection_ns = self.reused_blocks = 0

    def __contains__(self, block_id):
        return block_id in self.free_table

    @property
    def num_blocks(self):
        return len(self.free_table)

    def add(self, block_id, content_hash, num_hashed_tokens, last_accessed):
        if block_id in self.free_table:
            raise ValueError("candidate already present")
        self.free_table[block_id] = FreeBlock(content_hash, num_hashed_tokens, last_accessed)

    def remove(self, block_id):
        # Reactivation preserves reuse history. Actual eviction removes it.
        if block_id not in self.free_table:
            raise ValueError("candidate missing")
        del self.free_table[block_id]

    def update(self, block_id, last_accessed):
        self.free_table[block_id].last_accessed = last_accessed

    def record_reuse(self, content_hash):
        now = self.clock()
        count, last = self.reuse.get(content_hash, (0, now))
        if now - last >= self.hot_ttl_s:
            count = 0
        self.reuse[content_hash] = (min(count + 1, self.hot_threshold), now)
        self.reused_blocks += 1

    def is_hot(self, content_hash, now):
        count, last = self.reuse.get(content_hash, (0, now))
        return count >= self.hot_threshold and now - last < self.hot_ttl_s

    def evict(self):
        if not self.free_table:
            raise ValueError("No usable cache memory left")
        start, now = time.perf_counter_ns(), self.clock()
        block_id = min(self.free_table, key=lambda i: (
            self.is_hot(self.free_table[i].content_hash, now),
            self.free_table[i].last_accessed, -self.free_table[i].num_hashed_tokens, i))
        meta = self.free_table.pop(block_id)
        hot = self.is_hot(meta.content_hash, now)
        self.reuse.pop(meta.content_hash, None)
        duration = time.perf_counter_ns() - start
        self.evictions += 1
        self.selection_ns += duration
        emit("policy.cache_evict", block_id=block_id, hot=hot,
             candidates=len(self.free_table) + 1, selection_ns=duration)
        return block_id, meta.content_hash


def make_policy_evictor():
    return ColdHotEvictor(int(os.environ.get("DRIVESERVE_HOT_REUSES", "2")),
                          float(os.environ.get("DRIVESERVE_HOT_TTL_S", "30")))


def gpu_allocator(manager):
    from vllm.utils import Device
    return manager.block_allocator._allocators[Device.GPU]


def record_prefix_reuse(manager, seq_group, computed_ids):
    """First non-chunked prefill only; omit any partially reused final block.

    Upstream recomputes the last token on a full prompt hit. Recording only
    full skipped blocks is conservative and avoids counting that whole block.
    """
    if not computed_ids:
        return
    seq = seq_group.get_seqs()[0]
    skipped_tokens = min(len(computed_ids) * manager.block_size, seq.get_len() - 1)
    count = skipped_tokens // manager.block_size
    allocator = gpu_allocator(manager)
    blocks = manager.block_tables[seq.seq_id].blocks[:count]
    assert [b.block_id for b in blocks] == list(computed_ids[:count])
    for block in blocks:
        assert allocator._refcounter.get(block.block_id) > 0
        assert allocator._cached_blocks[block.content_hash] == block.block_id
        assert allocator.block_is_computed(block.block_id)
        if isinstance(allocator.evictor, ColdHotEvictor):
            allocator.evictor.record_reuse(block.content_hash)
    emit("policy.prefix_reuse", request_id=seq_group.request_id,
         full_reused_blocks=count, skipped_tokens=skipped_tokens,
         computed_blocks=len(computed_ids), scope="first_prefill_actual_prefix")


def register_arrival(seq_group):
    # Monotonic time cannot be changed by client-supplied wall arrival timestamps.
    seq_group._driveserve_enqueued_at = time.monotonic()


def order_waiting(scheduler, enable_chunking):
    cfg = scheduler.scheduler_config
    if enable_chunking or cfg.is_multi_step or cfg.policy != "fcfs":
        raise ValueError("length-aging requires V0 non-chunked single-step FCFS")
    if not scheduler.waiting:
        return
    age_s = float(os.environ.get("DRIVESERVE_AGING_S", "0.5"))
    if age_s <= 0:
        raise ValueError("aging threshold must be positive")
    now, started = time.monotonic(), time.perf_counter_ns()
    before = list(scheduler.waiting)
    def key(group):
        arrived = group._driveserve_enqueued_at
        if now - arrived >= age_s:
            return (0, arrived, 0)
        return (1, group.get_seqs()[0].get_prompt_len(), arrived)
    ordered = sorted(before, key=key)
    scheduler.waiting.clear()
    scheduler.waiting.extend(ordered)
    emit("policy.admission_order", before=[g.request_id for g in before],
         after=[g.request_id for g in ordered],
         aged=[g.request_id for g in ordered if now - g._driveserve_enqueued_at >= age_s],
         ages_s={g.request_id: now - g._driveserve_enqueued_at for g in ordered},
         host_order_ns=time.perf_counter_ns() - started)


def assert_allocator_invariants(allocator):
    """Diagnostic only, O(pool); never enabled in latency measurements."""
    cached = allocator._cached_blocks
    free = allocator.evictor.free_table
    assert len(set(cached.values())) == len(cached)
    for content_hash, block_id in cached.items():
        refs = allocator._refcounter.get(block_id)
        assert refs >= 0
        assert (block_id in free) == (refs == 0)
        if refs == 0:
            assert free[block_id].content_hash == content_hash
    for block_id, meta in free.items():
        assert cached[meta.content_hash] == block_id
        assert allocator._refcounter.get(block_id) == 0
    if isinstance(allocator.evictor, ColdHotEvictor):
        assert set(allocator.evictor.reuse).issubset(cached)
    return {"cached": len(cached), "evictable": len(free),
            "free_total": allocator.get_num_free_blocks(),
            "total": allocator.get_num_total_blocks()}
