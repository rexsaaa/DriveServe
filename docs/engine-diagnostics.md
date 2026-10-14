# V0 引擎诊断与源码路线

当前是实施准备：观察器和隔离补丁已编写，实机开关对照待执行。上游固定 vLLM 0.8.5 / `ba41cc90e8ef7f236347b2f1599eec2cbb9e1f0d`。不将代码存在当作诊断结论。

## 实际路径

HTTP 路径从 `entrypoints/openai/serving_chat.py::OpenAIServingChat.create_chat_completion` 调用 engine_client.generate，经 `engine/async_llm_engine.py::AsyncLLMEngine.generate/add_request/engine_step` 的请求跟踪及异步引擎转交。同步诊断直接调用 `LLMEngine.add_request/step`，共享下列 V0 调度、块管理与模型路径，不包含 HTTP/SSE 开销。

`engine/llm_engine.py::LLMEngine.step` 调用 `core/scheduler.py::Scheduler.schedule`，内部 `_schedule` 决定 waiting/running/swapped 处理，并经 `core/block_manager.py::SelfAttnBlockSpaceManager` allocate/append_slots/free 管理块表。APC 的引用计数、computed hash 与零引用淘汰在 `core/block/prefix_caching_block.py`，原生策略保持不变。

引擎构建 ExecuteModelRequest，经 `executor/executor_base.py` 和单卡 `uniproc_executor.py` 的 worker 调用，进入 `worker/worker_base.py::LocalOrDistributedWorkerBase.execute_model`，再到 `worker/model_runner.py::ModelRunner.execute_model`。Qwen2Attention.forward 在 `model_executor/models/qwen2.py` 做 QKV 投影、RoPE 和 Attention；FA2 后端在 `attention/backends/flash_attn.py` 写 KV 并分派 prefill/decode kernel。Sampler 输出返回 LLMEngine 的 `_process_model_outputs`，推进序列、结束/释放并形成 RequestOutput；HTTP 模式再由 serving_chat 输出流返回。

这里保留版本中的实际类名；没有杜撰 V1 KVCacheManager 作为 V0 调用链。下一步用实际事件检查经过哪些分支，再关联 GPU 时间线。

## 观察器和复现方式

`patches/vllm-v0.8.5-observers.patch` 只在四个模块末尾加入显式环境开关。`DRIVESERVE_TRACE_DIR` 未设置时不装饰方法。启用后观察 schedule、enqueue、allocate、append/free、ModelRunner.execute_model 和 LLMEngine.step，不改变原返回对象、参数或决策；异常原样传播。仅记录请求 ID、长度、块表、队列数量和主机时钟，不记录 prompt 正文。

`scripts/build_vllm_overlay.py` 对 wheel 中待修改文件核对固定上游 hash，复制这四个文件后用零 fuzz 应用补丁，并校验修改前后 hash。其余文件链接到固定环境的原 wheel；不改 site-packages。迁移后需重建环境与 overlay，不能只复制这些本地软链接。

```bash
/hy-tmp/driveserve/venv-rebuilt/bin/python scripts/build_vllm_overlay.py --destination /hy-tmp/driveserve/vllm-observers-v1
/hy-tmp/driveserve/venv-rebuilt/bin/python scripts/diagnose_engine.py --overlay /hy-tmp/driveserve/vllm-observers-v1
/hy-tmp/driveserve/venv-rebuilt/bin/python scripts/diagnose_engine.py --overlay /hy-tmp/driveserve/vllm-observers-v1 --trace
```

后两条需 clean 工作树并顺序运行。负载是三波、每波8个请求，prompt为96–1536 tokens，固定32输出 token、ignore_eos，用于机制诊断；不是车载业务质量测试。保持相同种子、调度/KV预算与热点前缀，单独热身，保存完整 token ID 与输出。它不是调优 B1 或正式 P99 对照。

所有 `host_call_ns` 都是 Python 方法墙钟，可能含等待、dispatch 或采样；不额外同步 GPU，不能当 CUDA kernel 时间。观察器自身序列化/文件写入会增加开销，要通过启停两种状态的完整负载比较。原始事件与输出必须实际产生后才能填写分析。
