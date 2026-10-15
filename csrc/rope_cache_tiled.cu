// S4 opt-in head-tile implementation: head tiles and half2 preserve FP16 intermediate rounding.
#include <ATen/ATen.h>
#include <ATen/cuda/CUDAContext.h>
#include <c10/cuda/CUDAGuard.h>
#include <c10/cuda/CUDAException.h>
#include <cuda_fp16.h>
#include <cassert>
#include <cstdint>
namespace {
constexpr int D=128, QH=28, KVH=4;
__global__ void tiled_scalar(c10::Half* projection, const int64_t* positions,
    const c10::Half* table, c10::Half* cache, const int64_t* slots,
    int64_t row_stride, int64_t cache_slots, int64_t position_capacity) {
  const int64_t token=blockIdx.x, pos=positions[token], slot=slots[token];
  assert(pos>=0 && pos<position_capacity); assert(slot<cache_slots);
  const int head=blockIdx.y*4+threadIdx.x/64, dim=threadIdx.x%64;
  c10::Half* row=projection+token*row_stride;
  const c10::Half c=table[pos*D+dim], s=table[pos*D+64+dim];
  const c10::Half x=row[head*D+dim], y=row[head*D+dim+64];
  const c10::Half rx=x*c-y*s, ry=y*c+x*s;
  row[head*D+dim]=rx; row[head*D+dim+64]=ry;
  if (head>=QH && slot>=0) {
    const int kv_head=head-QH;
    const int64_t target=slot*KVH*D+kv_head*D+dim;
    cache[target]=rx; cache[target+64]=ry;
    cache[cache_slots*KVH*D+target]=row[(QH+KVH+kv_head)*D+dim];
    cache[cache_slots*KVH*D+target+64]=row[(QH+KVH+kv_head)*D+dim+64];
  }
}
__global__ void tiled_half2(__half* projection, const int64_t* positions,
    const __half* table, __half* cache, const int64_t* slots,
    int64_t row_stride, int64_t cache_slots, int64_t position_capacity) {
  const int64_t token=blockIdx.x, pos=positions[token], slot=slots[token];
  assert(pos>=0 && pos<position_capacity); assert(slot<cache_slots);
  const int head=blockIdx.y*4+threadIdx.x/32, dim=2*(threadIdx.x%32);
  __half* row=projection+token*row_stride;
  const __half2 c=*reinterpret_cast<const __half2*>(table+pos*D+dim);
  const __half2 s=*reinterpret_cast<const __half2*>(table+pos*D+64+dim);
  const __half2 x=*reinterpret_cast<const __half2*>(row+head*D+dim);
  const __half2 y=*reinterpret_cast<const __half2*>(row+head*D+dim+64);
  // Separate intrinsics deliberately avoid FMA and keep each FP16 rounding.
  const __half2 rx=__hsub2_rn(__hmul2_rn(x,c),__hmul2_rn(y,s));
  const __half2 ry=__hadd2_rn(__hmul2_rn(y,c),__hmul2_rn(x,s));
  *reinterpret_cast<__half2*>(row+head*D+dim)=rx;
  *reinterpret_cast<__half2*>(row+head*D+dim+64)=ry;
  if (head>=QH && slot>=0) {
    const int kv_head=head-QH;
    const int64_t target=slot*KVH*D+kv_head*D+dim;
    *reinterpret_cast<__half2*>(cache+target)=rx;
    *reinterpret_cast<__half2*>(cache+target+64)=ry;
    *reinterpret_cast<__half2*>(cache+cache_slots*KVH*D+target)=
      *reinterpret_cast<const __half2*>(row+(QH+KVH+kv_head)*D+dim);
    *reinterpret_cast<__half2*>(cache+cache_slots*KVH*D+target+64)=
      *reinterpret_cast<const __half2*>(row+(QH+KVH+kv_head)*D+dim+64);
  }
}
}
void tiled_rope_cache_cuda(at::Tensor projection,at::Tensor positions,
    at::Tensor cos_sin,at::Tensor cache,at::Tensor slots,bool vectorized) {
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

  dim3 grid(tokens,8);
  if (vectorized) {
    TORCH_CHECK(projection.stride(0)%2==0 &&
      reinterpret_cast<uintptr_t>(projection.data_ptr())%4==0 &&
      reinterpret_cast<uintptr_t>(cos_sin.data_ptr())%4==0 &&
      reinterpret_cast<uintptr_t>(cache.data_ptr())%4==0,
      "half2 requires aligned pointers and an even token-row stride");
    tiled_half2<<<grid,128,0,at::cuda::getCurrentCUDAStream()>>>(
      reinterpret_cast<__half*>(projection.data_ptr<c10::Half>()), positions.data_ptr<int64_t>(),
      reinterpret_cast<const __half*>(cos_sin.data_ptr<c10::Half>()),
      reinterpret_cast<__half*>(cache.data_ptr<c10::Half>()), slots.data_ptr<int64_t>(),
      projection.stride(0),cache.size(1)*cache.size(2),cos_sin.size(0));
  } else {
    tiled_scalar<<<grid,256,0,at::cuda::getCurrentCUDAStream()>>>(
      projection.data_ptr<c10::Half>(), positions.data_ptr<int64_t>(),
      cos_sin.data_ptr<c10::Half>(), cache.data_ptr<c10::Half>(), slots.data_ptr<int64_t>(),
      projection.stride(0),cache.size(1)*cache.size(2),cos_sin.size(0));
  }
  C10_CUDA_KERNEL_LAUNCH_CHECK();
}
