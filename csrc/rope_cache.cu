// Project implementation. Semantic references: vLLM v0.8.5
// pos_encoding_kernels.cu and reshape_and_cache_flash in cache_kernels.cu.
#include <ATen/ATen.h>
#include <ATen/cuda/CUDAContext.h>
#include <c10/cuda/CUDAGuard.h>
#include <c10/cuda/CUDAException.h>
#include <cassert>

namespace {
constexpr int D = 128, QH = 28, KVH = 4, HALF_D = D / 2;

// A token owns its Q/K rotations and its two cache writes. Distinct nonnegative
// slots are a validated precondition, so no cross-block synchronization is used.
__global__ void rope_cache_kernel(c10::Half* projection,
    const int64_t* positions, const c10::Half* cos_sin, c10::Half* cache,
    const int64_t* slots, int64_t row_stride, int64_t cache_slots,
    int64_t positions_capacity) {
  const int64_t token = blockIdx.x;
  const int64_t pos = positions[token], slot = slots[token];
  assert(pos >= 0 && pos < positions_capacity);
  assert(slot < cache_slots);
  c10::Half* row = projection + token * row_stride;
  const int offset = threadIdx.x % HALF_D;
  const c10::Half cosine = cos_sin[pos * D + offset];
  const c10::Half sine = cos_sin[pos * D + HALF_D + offset];
  for (int pair = threadIdx.x; pair < QH * HALF_D; pair += blockDim.x) {
    const int index = (pair / HALF_D) * D + offset;
    const c10::Half x = row[index], y = row[index + HALF_D];
    // Match upstream Half arithmetic, including intermediate FP16 rounding.
    row[index] = x * cosine - y * sine;
    row[index + HALF_D] = y * cosine + x * sine;
  }
  for (int pair = threadIdx.x; pair < KVH * HALF_D; pair += blockDim.x) {
    const int index = (pair / HALF_D) * D + offset;
    const int ki = QH * D + index, vi = (QH + KVH) * D + index;
    const c10::Half x = row[ki], y = row[ki + HALF_D];
    const c10::Half rx = x * cosine - y * sine;
    const c10::Half ry = y * cosine + x * sine;
    row[ki] = rx;
    row[ki + HALF_D] = ry;
    if (slot >= 0) {
      const int64_t target = slot * KVH * D + index;
      cache[target] = rx;
      cache[target + HALF_D] = ry;
      cache[cache_slots * KVH * D + target] = row[vi];
      cache[cache_slots * KVH * D + target + HALF_D] = row[vi + HALF_D];
    }
  }
}
}  // namespace

void fused_rope_cache_cuda(at::Tensor projection, at::Tensor positions,
                          at::Tensor cos_sin, at::Tensor cache,
                          at::Tensor slots) {
  TORCH_CHECK(projection.is_cuda(), "projection must be CUDA");
  for (const auto& tensor : {positions, cos_sin, cache, slots}) {
    TORCH_CHECK(tensor.device() == projection.device(), "all tensors must share a CUDA device");
  }
  TORCH_CHECK(projection.scalar_type() == at::kHalf && cos_sin.scalar_type() == at::kHalf &&
              cache.scalar_type() == at::kHalf, "only FP16 is supported");
  TORCH_CHECK(positions.scalar_type() == at::kLong && slots.scalar_type() == at::kLong,
              "positions and slots must be int64");
  TORCH_CHECK(projection.dim() == 3 && projection.size(1) == QH + 2 * KVH &&
              projection.size(2) == D, "projection must be [T,36,128]");
  TORCH_CHECK(projection.stride(2) == 1 && projection.stride(1) == D &&
              projection.stride(0) >= (QH + 2 * KVH) * D,
              "only packed heads with optional token-row padding are supported");
  const int64_t tokens = projection.size(0);
  TORCH_CHECK(positions.dim() == 1 && slots.dim() == 1 && positions.numel() == tokens &&
              slots.numel() == tokens && positions.is_contiguous() && slots.is_contiguous(),
              "positions and slots must be contiguous [T]");
  TORCH_CHECK(cos_sin.dim() == 2 && cos_sin.size(1) == D && cos_sin.is_contiguous(),
              "cos/sin table must be contiguous [positions,128]");
  TORCH_CHECK(cache.dim() == 5 && cache.size(0) == 2 && cache.size(3) == KVH &&
              cache.size(4) == D && cache.is_contiguous() && cache.size(1) > 0 &&
              (cache.size(2) == 16 || cache.size(2) == 32),
              "cache must be contiguous [2,blocks,16|32,4,128]");
  if (tokens == 0) return;
  const c10::cuda::CUDAGuard device_guard(projection.device());
  rope_cache_kernel<<<tokens, 256, 0, at::cuda::getCurrentCUDAStream()>>>(
      projection.data_ptr<c10::Half>(), positions.data_ptr<int64_t>(),
      cos_sin.data_ptr<c10::Half>(), cache.data_ptr<c10::Half>(),
      slots.data_ptr<int64_t>(), projection.stride(0), cache.size(1) * cache.size(2),
      cos_sin.size(0));
  C10_CUDA_KERNEL_LAUNCH_CHECK();
}
