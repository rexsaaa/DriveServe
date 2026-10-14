#include <torch/extension.h>

void fused_rope_cache_cuda(at::Tensor projection, at::Tensor positions,
                          at::Tensor cos_sin, at::Tensor cache,
                          at::Tensor slots);

PYBIND11_MODULE(TORCH_EXTENSION_NAME, module) {
  module.def("fused", &fused_rope_cache_cuda,
             "NeoX RoPE and FA-layout KV append (FP16 Q28/KV4 D128)");
}
