# 源码预检与实机兼容矩阵

源码基准：vLLM v0.8.5 / `ba41cc90e8ef7f236347b2f1599eec2cbb9e1f0d`。以下只表示源码检查，均不是 GPU 功能验收。

| 主线 | 真实源码入口 | 发现 / 下一步 |
|---|---|---|
| M1 | `vllm/entrypoints/openai/serving_chat.py` → `vllm/engine/async_llm_engine.py` → `vllm/engine/llm_engine.py` → `vllm/core/scheduler.py::Scheduler.schedule`（1493） | 待完整函数链与真实事件插桩、开销对照 |
| M2 | `vllm/core/block_manager.py::SelfAttnBlockSpaceManager`；`vllm/core/block/prefix_caching_block.py::_maybe_allocate_evicted_block_id`（324） | 原生淘汰只处理 refcount=0 的缓存块；必须保留 hash/引用计数不变量，不得仅外部排序 |
| M3 | `vllm/spec_decode/spec_decode_worker.py::execute_model`（454）及 `_run_speculative_decoding_step`（758） | `num_lookahead_slots` 在运行请求中传递且广播给其他 worker；控制器、EOS/rollback、训练与固定 K 均待实现。1250 附近的词表相等断言与当前模型 metadata 冲突 |
| M4 | `vllm/model_executor/layers/quantization/awq.py::AWQConfig` | 该原生 AWQ 路径要求 FP16 激活，最低 capability=75；Group Size、导出器与 Marlin 实际兼容待检查，不用 BF16 冒充此路径的 W4A16 |
| M5 | `vllm/model_executor/layers/rotary_embedding.py::RotaryEmbedding.forward_cuda`（167）；`csrc/cache_kernels.cu` | 待核对 NeoX RoPE、GQA、slot_mapping、Paged KV 数据布局及上游已有融合；没有自定义 CUDA 实现 |
| M6 | `vllm/attention/backends/flash_attn.py`（808 等） | 存在 `flash_attn_varlen_func` 及 fa_version 参数；实际 FA2 kernel、Nsight、TP2 未验证。拓扑检测为 NODE，不是 NVLink |

| 配置项 | 当前事实 | 验收状态 |
|---|---|---|
| GPU | 2×报告 49140 MiB 的 RTX 4090；预装 torch 简单 matmul 成功 | 设备 smoke；不是 vLLM 成功 |
| 驱动 / 编译器 | 550.163.01 / nvcc 12.1 | vLLM 候选依赖 torch 2.6.0；独立环境待验证 |
| Target / Draft | revision 固定；tokenizer 文件同 hash，模板及 BOS/EOS 相同，配置词表维度不同 | 预检发现缺口；未加载权重 |
| AWQ / FA2 / 图模式 / TP2 | 有源码入口 | 实机待验收 |

链接中的行号只适用于上述固定 SHA。恢复源码使用 `scripts/restore_upstream.py`。上游代码不能记为个人实现；这份预检不满足 M1-01 的完整调用链，也不满足任何运行验收项。
