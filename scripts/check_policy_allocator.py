"""Exercise the actual patched upstream allocator, without model inference."""
import os
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from driveserve.engine_policies import ColdHotEvictor, assert_allocator_invariants
from vllm.core.block.prefix_caching_block import PrefixCachingBlockAllocator


class AllocatorTests(unittest.TestCase):
    def setUp(self):
        os.environ['DRIVESERVE_CACHE_POLICY'] = 'cold_hot'
        self.a = PrefixCachingBlockAllocator(4, 4)
        self.assertIsInstance(self.a.evictor, ColdHotEvictor)

    def block(self, value):
        b = self.a.allocate_immutable_block(None, [value] * 4)
        self.a.mark_blocks_as_computed([])
        assert_allocator_invariants(self.a)
        return b

    def test_shared_reference_never_evicts_active(self):
        a = self.block(10)
        b = self.block(10)
        shared = a.block_id
        self.assertEqual(shared, b.block_id)
        self.assertEqual(self.a._refcounter.get(shared), 2)
        self.a.free(a)
        self.assertNotIn(shared, self.a.evictor)
        for v in range(20, 60):
            other = self.block(v)
            self.assertNotEqual(other.block_id, shared)
            self.a.free(other)
            assert_allocator_invariants(self.a)
        self.assertFalse(self.a.reset_prefix_cache())
        self.a.free(b)
        self.assertIn(shared, self.a.evictor)
        self.assertTrue(self.a.reset_prefix_cache())
        self.assertEqual(self.a.get_num_free_blocks(), 4)
        self.assertFalse(self.a.evictor.reuse)
        assert_allocator_invariants(self.a)

    def test_hot_retained_cold_reused_hash_cleared(self):
        hot = self.block(10)
        hot_id, hot_hash = hot.block_id, hot.content_hash
        self.a.evictor.record_reuse(hot_hash)
        self.a.evictor.record_reuse(hot_hash)
        self.a.free(hot)
        for v in range(20, 100):
            block = self.block(v)
            self.a.free(block)
            assert_allocator_invariants(self.a)
        self.assertEqual(self.a._cached_blocks[hot_hash], hot_id)
        self.assertLessEqual(len(self.a.evictor.reuse), 4)
        self.assertGreater(self.a.evictor.evictions, 0)
        self.assertTrue(self.a.reset_prefix_cache())
        self.assertFalse(self.a.evictor.reuse)

    def test_allocation_dedup_is_not_effective_reuse(self):
        a = self.a.allocate_immutable_block(None, [5] * 4)
        b = self.a.allocate_immutable_block(None, [5] * 4)
        self.assertEqual(a.block_id, b.block_id)
        self.assertFalse(self.a.evictor.reuse)
        mutable = self.a.allocate_mutable_block(None)
        mutable.append_token_ids([5] * 4)  # Promotion/dedup also must not count.
        self.assertEqual(a.block_id, mutable.block_id)
        self.assertFalse(self.a.evictor.reuse)
        for block in [a, b, mutable]:
            self.a.free(block)
        assert_allocator_invariants(self.a)

    def test_mutable_fork_copy_on_write(self):
        parent = self.a.allocate_mutable_block(None)
        parent.append_token_ids([1, 2])
        child, = self.a.fork(parent)
        shared = parent.block_id
        self.assertEqual(child.block_id, shared)
        child.append_token_ids([3])
        self.assertNotEqual(child.block_id, parent.block_id)
        self.assertEqual(parent.token_ids, [1, 2])
        self.assertEqual(child.token_ids, [1, 2, 3])
        self.assertEqual(self.a.clear_copy_on_writes(), [(shared, child.block_id)])
        self.a.free(child)
        self.a.free(parent)
        self.assertEqual(self.a.get_num_free_blocks(), 4)
        assert_allocator_invariants(self.a)


if __name__ == '__main__':
    unittest.main(verbosity=2)
