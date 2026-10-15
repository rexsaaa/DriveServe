"""S4 opt-in implementation: TTL-aware exact-order heaps."""
import heapq
import math
import time
from driveserve.engine_policies import ColdHotEvictor
from driveserve.engine_trace import emit

class HeapColdHotEvictor(ColdHotEvictor):
    """Preserve cold/hot/LRU order; versioned lazy heaps with bounded rebuilding.

    The pinned allocator has at most one resident block per content hash. Only
    zero-reference free candidates enter these indices. Active reuse histories
    remain in the inherited reuse table and are reclassified upon release.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._cold, self._hot, self._expiry = [], [], []
        self._versions, self._by_hash = {}, {}
        self._serial = self.stale_pops = self.heap_rebuilds = 0

    def _index(self, block_id, now):
        meta = self.free_table[block_id]
        self._serial += 1
        generation = self._serial
        self._versions[block_id] = generation
        hot = self.is_hot(meta.content_hash, now)
        key = (meta.last_accessed, -meta.num_hashed_tokens, block_id, generation)
        heapq.heappush(self._hot if hot else self._cold, key)
        if hot:
            last = self.reuse[meta.content_hash][1]
            deadline = last + self.hot_ttl_s
            # Earliest representable clock value satisfying the reference
            # subtraction predicate, rather than assuming rounded addition
            # is its exact inverse. Real monotonic clocks and TTL are finite.
            while deadline - last < self.hot_ttl_s:
                deadline = math.nextafter(deadline, math.inf)
            previous = math.nextafter(deadline, -math.inf)
            while previous - last >= self.hot_ttl_s:
                deadline, previous = previous, math.nextafter(previous, -math.inf)
            heapq.heappush(self._expiry, (deadline, block_id, generation))

    def _compact(self, now):
        # Lazy entries must not grow with the number of requests indefinitely.
        entries = len(self._cold) + len(self._hot) + len(self._expiry)
        if entries <= max(64, 4 * len(self.free_table)):
            return
        self._cold.clear(); self._hot.clear(); self._expiry.clear()
        self._versions.clear()
        for block_id in self.free_table:
            self._index(block_id, now)
        self.heap_rebuilds += 1

    def _expire(self, now):
        while self._expiry and self._expiry[0][0] <= now:
            _, block_id, generation = heapq.heappop(self._expiry)
            if self._versions.get(block_id) != generation:
                self.stale_pops += 1
                continue
            # Deadline addition and the reference's now-last subtraction can
            # round differently at an exact float boundary. Preserve the
            # reference predicate without spinning at this same timestamp.
            if self.is_hot(self.free_table[block_id].content_hash, now):
                heapq.heappush(self._expiry,(math.nextafter(now,math.inf),block_id,generation))
                continue
            # Reinsert with a new version. The old hot-heap entry is now stale.
            self._index(block_id, now)

    def add(self, block_id, content_hash, num_hashed_tokens, last_accessed):
        if content_hash in self._by_hash:
            raise ValueError('allocator contract: one free block per content hash')
        super().add(block_id, content_hash, num_hashed_tokens, last_accessed)
        self._by_hash[content_hash] = block_id
        now = self.clock(); self._index(block_id, now); self._compact(now)

    def remove(self, block_id):
        meta = self.free_table[block_id]
        super().remove(block_id)
        del self._by_hash[meta.content_hash]; del self._versions[block_id]
        self._compact(self.clock())

    def update(self, block_id, last_accessed):
        super().update(block_id, last_accessed)
        now = self.clock(); self._index(block_id, now); self._compact(now)

    def record_reuse(self, content_hash):
        super().record_reuse(content_hash)
        now = self.clock()
        if content_hash in self._by_hash:
            self._index(self._by_hash[content_hash], now)
        self._compact(now)

    def _take(self, heap):
        while heap:
            _, _, block_id, generation = heapq.heappop(heap)
            if self._versions.get(block_id) == generation:
                return block_id
            self.stale_pops += 1
        return None

    def evict(self):
        if not self.free_table:
            raise ValueError('No usable cache memory left')
        started, now = time.perf_counter_ns(), self.clock()
        self._expire(now)
        block_id = self._take(self._cold)
        if block_id is None:
            block_id = self._take(self._hot)
        assert block_id is not None
        meta = self.free_table.pop(block_id)
        hot = self.is_hot(meta.content_hash, now)
        del self._versions[block_id]; del self._by_hash[meta.content_hash]
        self.reuse.pop(meta.content_hash, None)
        self._compact(now)
        duration = time.perf_counter_ns() - started
        self.evictions += 1; self.selection_ns += duration
        emit('policy.cache_evict', block_id=block_id, hot=hot,
             candidates=len(self.free_table)+1, selection_ns=duration,
             implementation='heap', stale_pops=self.stale_pops, heap_rebuilds=self.heap_rebuilds)
        return block_id, meta.content_hash

    def assert_index_invariants(self):
        assert set(self._versions)==set(self.free_table)
        assert self._by_hash=={m.content_hash:bid for bid,m in self.free_table.items()}
        entries=len(self._cold)+len(self._hot)+len(self._expiry)
        assert entries<=max(64,4*len(self.free_table))
        return {'heap_entries':entries,'heap_rebuilds':self.heap_rebuilds,'stale_pops':self.stale_pops}
