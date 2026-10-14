# V0 引擎诊断与源码路线

S1 期间的 S2 实施准备已取得一对实机开关对照，尚未形成六线完整验收。上游固定 vLLM 0.8.5 / `ba41cc90e8ef7f236347b2f1599eec2cbb9e1f0d`。不将代码存在当作诊断结论。

## 实际路径

HTTP 路径从 `entrypoints/openai/serving_chat.py::OpenAIServingChat.create_chat_completion` 调用 engine_client.generate，经 `engine/async_llm_engine.py::AsyncLLMEngine.generate/add_request/engine_step` 的请求跟踪及异步引擎转交。同步诊断直接调用 `LLMEngine.add_request/step`，共享下列 V0 调度、块管理与模型路径，不包含 HTTP/SSE 开销。

`engine/llm_engine.py::LLMEngine.step` 调用 `core/scheduler.py::Scheduler.schedule`，内部 `_schedule` 决定 waiting/running/swapped 处理，并经 `core/block_manager.py::SelfAttnBlockSpaceManager` allocate/append_slots/free 管理块表。APC 的引用计数、computed hash 与零引用淘汰在 `core/block/prefix_caching_block.py`，原生策略保持不变。

引擎构建 ExecuteModelRequest，经 `executor/executor_base.py` 和单卡 `uniproc_executor.py` 的 worker 调用，进入 `worker/worker_base.py::LocalOrDistributedWorkerBase.execute_model`，再到 `worker/model_runner.py::ModelRunner.execute_model`。Qwen2Attention.forward 在 `model_executor/models/qwen2.py` 做 QKV 投影、RoPE 和 Attention；FA2 后端在 `attention/backends/flash_attn.py` 写 KV 并分派 prefill/decode kernel。Sampler 输出返回 LLMEngine 的 `_process_model_outputs`，推进序列、结束/释放并形成 RequestOutput；HTTP 模式再由 serving_chat 输出流返回。

这里保留版本中的实际类名；没有杜撰 V1 KVCacheManager 作为 V0 调用链。实际事件已验证同步 V0 的入队、调度、块分配/追加/释放、模型执行与输出；HTTP异步边界未插桩，已另行采集单卡GPU时间线。

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


## 首次实机结果和可追问内容

固定代码 `3676c86`、相同合成输入与配置，开启观察器 run `20261014T234421+0800-7a0f81e8d0`，关闭 run `20261014T234558+0800-8bd9655f6c`。24/24 输出 token 序列一致。累计 engine.step 墙钟分别4.217070112秒与4.157272374秒，观察差为+1.438%；只有一对运行，不能将全部差异严格归因于插桩，更不能声称零开销。分组等待原始观测和重聚合结果见 reports/s2-engine-diagnostic.json。

包含热身的事件有225次调度、25次入队/分配、775次append、50次free调用（含幂等重复free，不能当50个独立块释放）、226次ModelRunner调用。waiting最大8、running最大4，没有抢占/swapped。因此确实观察到排队，但没有证据声称KV饱和或抢占瓶颈。观察器尚不覆盖取消、共享fork和实际淘汰的全部细节，不是M2生命周期验收。

第一波模型输出报告cached tokens为0，后两波各1664，来自三个热点prompt的1024+128+512。这个字段按上游RequestOutput语义记录，不能直接等同于精确跳过的Prefill token数，也不能计入每次Decode访问作为新命中。下一步在匹配冷/热起点和更受限KV池中检验缓存策略，先建立B0/B1再归因。

为什么ModelRunner的16.6ms decode主机中位数不是GPU kernel时间？因为该调用含dispatch、采样和可能的等待，GPU执行异步；需Nsight关联CUDA API、实际kernel和间隙。为什么观察到前缀命中不证明自研cache有效？因为这次仍是原生APC，所有决策未修改。为什么一次开关实验不能保证输出分布全面不变？这里只有固定种子贪心及24条合成轨迹，不涵盖随机采样、取消或并发故障。

重聚合命令：

```bash
python3 scripts/analyze_engine_trace.py --trace-on experiments/runs/20261014T234421+0800-7a0f81e8d0 --trace-off experiments/runs/20261014T234558+0800-8bd9655f6c --output /tmp/driveserve-engine-reaggregate.json
```

诊断脚本新增 `--profile`，通过CUDA Profiler API仅捕获热身后的负载，并在ModelRunner加入Prefill/Decode NVTX范围。Nsight CLI 2024.5.1已按NVIDIA包SHA256下载解包到项目临时工具目录；真实采集结果见下文。profile运行单列，禁止进入上述计时对照。


## Nsight 实际时间线

capture wrapper `20261014T235018+0800-d4622dd168` / engine `20261014T235030+0800-0698208fe6`，代码 `2779f66`，Nsight Systems 2024.5.1。CUDA Profiler API 在热身后开始、24条请求结束后停止；NVTX 按实际 attention metadata 区分 Prefill/Decode。原始 `.nsys-rep`、工具CSV和额外资产索引均保留在Git，见 reports/s2-profile-assets.json。

捕获70,804个kernel，全部通过同进程CUDA API correlation ID与NVTX区间关联。下表单位毫秒，单位样本是一次ModelRunner批次调用，不是单请求：

| 阶段 | 区间数 | 主机调用中位数 | kernel时间并集中位数 | 首尾kernel跨度中位数 | kernel间隙中位数 |
|---|---:|---:|---:|---:|---:|
| Prefill | 7 | 148.7785 | 147.8672 | 148.5927 | 0.7724 |
| Decode | 186 | 18.0905 | 15.9414 | 17.9739 | 2.0460 |

Decode 每批的关联launch API累计耗时中位数2.5005ms；CPU API与GPU可重叠，不能直接相加。kernel间隙可包含内存操作、其他工作或等待，不等于整卡空闲，也不能直接断言CPU瓶颈。工具的NVTX GPU projection还包含memcpy/memset，所以它与这里只看kernel的跨度有小差异。

三个主要GEMM kernel合计占本次kernel时长和约90.94%；还捕获了实际flash_fwd和splitkv kernel。本次小并发、上下文≤1536的合成负载不能支撑“KV访存主导”或“显存不足”的结论；下一步应在长上下文/更受限KV预算下做匹配对照。单卡时间线没有TP2通信证据。profiling带有观察器且改变运行成本，不与无profile基线计算性能收益。

首次输出父目录不存在，nsys记录了告警并将完整报告写入`/tmp/nsys-report-24ff.nsys-rep`；已按日志位置逐字节复制到`artifacts/profiles/engine-observers-v1.nsys-rep`，两份SHA256一致，导出/解析成功。保留告警与import收据，没有重复跑一次来隐藏问题。以后采集前先创建输出目录。

```bash
NSYS=/hy-tmp/driveserve/tools/nsight-systems-2024.5/opt/nvidia/nsight-systems-cli/2024.5.1/target-linux-x64/nsys
mkdir -p artifacts/profiles
"$NSYS" profile --trace=cuda,nvtx,osrt --sample=none --cpuctxsw=none --capture-range=cudaProfilerApi --capture-range-end=stop --output=artifacts/profiles/new-capture /hy-tmp/driveserve/venv-rebuilt/bin/python scripts/diagnose_engine.py --overlay /hy-tmp/driveserve/vllm-observers-v1 --trace --profile
"$NSYS" export --type sqlite --output artifacts/profiles/new-capture.sqlite artifacts/profiles/new-capture.nsys-rep
python3 scripts/analyze_nsys.py --sqlite artifacts/profiles/new-capture.sqlite --nsys-rep artifacts/profiles/new-capture.nsys-rep --report /tmp/driveserve-new-profile.json
```

嵌套日志核验修复：旧Run.finish只封存根层文件，engine-trace子目录已由Git保存，但旧manifest未包含其hash。额外索引补齐旧证据，不改写旧manifest；新Run递归封存，并有“改动嵌套事件文件必须被发现”的回归测试。
