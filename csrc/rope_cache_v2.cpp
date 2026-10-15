#include <torch/extension.h>
void fused_rope_cache_cuda(at::Tensor,at::Tensor,at::Tensor,at::Tensor,at::Tensor);
void tiled_rope_cache_cuda(at::Tensor,at::Tensor,at::Tensor,at::Tensor,at::Tensor,bool);
PYBIND11_MODULE(TORCH_EXTENSION_NAME,module) {
  module.def("fused",&fused_rope_cache_cuda,"Unchanged S2 token-block CUDA baseline");
  module.def("tiled",&tiled_rope_cache_cuda,"Head tiles, optional half2; same finite FP16 semantics");
}
