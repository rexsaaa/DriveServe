# 从零到 S2 的累计讲解与追问

本项目用结构化车载决策代理任务研究推理基础设施；输入是道路、障碍与车辆状态，输出 action、speed_band、must_yield。规则真值独立于模型输出。这里没有感知、控制或真实车辆安全验证。阶段验收、结果数值和发布版本以同目录的验收报告为准；以下讲解覆盖 S1 到 S2 的实际工程。

## 全景和演进

从空仓库开始，先建立场景生成、评分器、SSE 客户端、环境锁定和运行证据协议。S1 在真实双 RTX 4090 上跑通 Qwen2.5-7B-Instruct、1.5B Draft、单卡和 TP2，并用全新环境重建与 OSS 下载校验验证恢复入口。实际每卡报告 49140MiB，没有 NVLink，P2P 检查失败；不能把这些结果外推成真实 24GB 卡或已发生宿主迁移。

S2 沿六条线形成可回放的实现和实验。先用固定 vLLM 0.8.5 源码、开关观察器和 Nsight 确认真实执行，再接入冷热淘汰和长度 admission。随后实现运行时 K、修复采样边界、完成教师生成和 128 步 LoRA 蒸馏；独立完成三组 AWQ 校准、CUDA 融合原型、FA2 及 HTTP 三部署对照。它们是不同 profile，不能声称全部同时打开。默认保留 FP16 Target 和原生策略，实验优化不自动成为发布默认。

正式数据是 train512/calibration256/dev128/final-test256，场景组与精确内容跨 split 隔离，与旧 fixture 无重复。公共规则与模板仍共享，不证明跨模板泛化。S2 用 dev 作选择，final-test 留到 S5。教师640条只来自 train/dev；472条合格 train 进入训练，40条规则错误保留并排除。独立规则质量与模仿教师的 loss 是两种指标。

所有正式实验要求 clean Git SHA，保存环境、配置、模型/数据 hash、原始输出和进程指纹。任务中断后先检查 PID、boot_id、start_ticks，避免重复启动。训练保存优化器、scheduler、RNG 和数据 cursor；AWQ 只保存逐层进度，意外中断须重新校准整组。GitHub 保存源码和小证据；OSS 保存权重、训练状态和环境并逐包完整读回。没有后台自动开机或会话自动恢复承诺。

## 源码阅读路线：跟随实际输入

1. 从 `driveserve/task.py` 的场景校验、`messages` 和 `score` 开始，理解 oracle；读 `scripts/freeze_task_data.py` 和 data/frozen-v1/manifest.json 核对用途隔离。
2. HTTP 请求经过固定上游的 OpenAIServingChat/OpenAIServingCompletion、MQLLMEngineClient 和 MQLLMEngine，再到 LLMEngine；同步实验直接进入 LLMEngine。读 [完整调用链](../../engine-diagnostics.md)，不要忽略 MQ 进程边界。
3. 依次读 Scheduler.schedule、SelfAttnBlockSpaceManager、PrefixCachingBlockAllocator，再读 `driveserve/engine_trace.py` 和 `engine_policies.py`。用一个 request_id 跟踪 enqueue→schedule→allocate→ModelRunner→output→free。
4. 读 Qwen2Attention.forward、RotaryEmbedding、FlashAttentionImpl.forward，关联 `csrc/rope_cache.cu` 的 packed QKV 和 cache slot；用 Nsight correlation ID 关联 CPU launch 和 GPU kernel。
5. 读 `driveserve/spec_control.py` 与 spec patch，再沿 `generate_teacher.py`→`train_draft.py`→`export_draft.py`→`benchmark_speculation.py` 跟踪 Draft 的实际产物。
6. 沿 `freeze_awq_data.py`→`quantize_awq.py`→`benchmark_speculation.py`→`analyze_awq.py` 检查 W4 产物；最后读 `benchmark_deployments.py` 和 `analyze_deployments.py`，从逐请求 SSE 重新计算结果。

## M1：源码和诊断

研究机会是区分排队、前缀复用、CPU dispatch 和 GPU 计算，不能先假定 KV 访存是瓶颈。原生 vLLM 已有 APC、调度、FA2 和部分指标。项目增量是在锁定文件上加入可关闭观察器及 NVTX，保存真实 enqueue/schedule/KV/model/output 事件；没有重写引擎。

一次请求用 request_id 连接入队、分配和输出。Python 主机方法耗时包含 dispatch/等待，不能作为 CUDA 时间；Nsight 通过同进程 correlation ID 连接 launch 与 kernel。本次 70,804 个 kernel 的时间线显示主要 GEMM 占时长和约 90.94%，只支持“小负载以 GEMM 为主”的观测，不能推出业务 KV 带宽瓶颈。

正确性由观察器开关下的相同输出核对；初诊24条相同，后续压力36条也相同。一次开关计时差约1.4%，包含运行波动，不是严格因果开销。源码未插桩的 HTTP/MQ 函数没有逐函数耗时结论。S3 应补独立重复和异常请求，不用增加日志量冒充更强证据。

追问：为什么要同时记录 host 和 GPU？前者解释引擎控制成本，后者区分实际计算与间隙。为什么不能把间隙全部当空闲？还可能有内存操作、其他 stream 或等待。为什么没观察到预设瓶颈也有效？诊断的作用是决定下一步，不是验证原稿措辞。证据与复现见 [引擎诊断](../../engine-diagnostics.md)。

## M2：冷热缓存与长度调度

原生 APC 按 hash 复用完整块，并在零引用候选中淘汰。项目 `ColdHotEvictor` 用首次 Prefill 真正跳过的连续完整块计有效复用，两次变热、30秒未复用回冷；先淘汰冷块，再按最近访问、前缀长度和 block_id 排序。元数据以 content_hash 为键，淘汰清理，重新激活保留历史；同批去重、promotion 和 Decode 不重复加命中。

一次 WAITING 请求进入 `_schedule_prefills` 时，等待超过0.25秒的按入队时间优先，否则按已知 prompt 长度。原始 token/KV/maxseq admission 检查仍生效，不读取未来输出长度，老化不能越过资源不足。这是同一 GPU KV 池的保留优先级，不是 CPU/GPU 交换。

首次压力实验发现 WAITING 前缀缓存计数在块淘汰后陈旧。用真实原生分配器复现4→4的错误，补丁让 WAITING 重新查 resident hash，RUNNING 连续 Prefill 才沿用计数，修复后4→0。四策略均用同一正确性补丁；不能把修复算性能创新。原始失败日志仍保留。

四组对照是 native/cache/scheduler/both，B1 经有限 eager/Graph、maxseq2/4/8 比较选 Graph/4。288条开关输出一致，两个生命周期实验各792次不变量检查覆盖共享、running/waiting取消、块重用与 RECOMPUTE。冷热策略在热点冲刷后保留992tokens复用；短请求更早但长请求 TTFT 增加，整体吞吐未证明稳定收益。扫描候选是 O(空闲块数)，需要 S3 测维护成本。

追问：为什么活动块不能淘汰？上游 refcount 和共享 block table 仍引用它。为什么命中增加不保证吞吐增加？省去的是 Prefill，而 Decode、扫描和排队可能主导。为什么有老化仍不承诺无饥饿？仅控制 admission 顺序，资源和请求执行可继续阻塞。范围限 V0 非 chunked single-step FCFS n=1，swap/beam/TP 未验。源码、数字和复现见 [缓存调度](../../cache-scheduler.md)。

## M3：运行时 K 与实际蒸馏

原生固定 K 的 scheduler 预留候选空间，Draft 提议、Target 验证，拒绝后回滚，处理 bonus/EOS/长度。项目保留最大 K=4 的资源预留，worker 在提议前复制执行请求的外壳并改实际 K。控制器初始2，8批滑窗与8批持有期，接受率低于0.45减K、高于0.8增K，界限1–4。实际 proposal 和 verification 宽度记录在轨迹；不是重启服务换参数。

接受率分子只计连续接受前缀，分母为实际提议数，不含 bonus，计数位于 EOS/长度截断之前。原生固定分母指标不能直接用于动态 K；项目另记实际分母。MQA 带 seed 的原生实现按 seq_ids 而非 sample_indices 初始化随机行，20行只填4行；补丁修正跨度与过滤后 seed 映射，CUDA 分布实验和真实模型回归分别验证。不能将修复说成采样算法创新。

Draft 与 Target 同 tokenizer 但 logits 词表分别151936/152064，零填128行只解决维度且改变 softmax，不等于训练。真实训练另用472条合格教师输出，rank8 LoRA、128 optimizer步、microbatch2×accum4、仅答案含EOS loss。第8步 checkpoint 可见后发 SIGTERM，第9步保存退出，恢复至16步与连续参考的 adapter/优化器/scheduler/RNG/loss/样本顺序 bitwise 相同；最终完整 checkpoint 和合并模型保留。

贡献分离在同137请求比较原 Draft fixed、新 Draft fixed、新 Draft adaptive 和 Target。两种 fixed 均137/137序列相同，adaptive136/137，质量均121/128。接受率83.90%→86.92%，动态88.61%；单次带trace吞吐没有超过Target。近似/并列FP16 logits能解释已诊断位置的分歧，不承诺全序列严格相同或通用分布等同。默认关闭推测，保留可回放 profile。

追问：为什么接受率高还可能慢？Draft成本、验证宽度、CPU同步、batch与bonus共同决定总成本。为什么只比较新adaptive和原fixed不能证明蒸馏贡献？训练和控制器同时变化，须固定K比较训练，再固定Draft比较控制。为什么模型权重恢复不等于续训？优化器动量、LR、RNG和cursor也决定后续更新。详见 [推测](../../speculation.md) 与 [蒸馏](../../distillation-protocol.md)。

## M4：三组 AWQ 与显存口径

目标是测压缩的质量、容量与速度取舍。AutoAWQ 提供 scale 搜索、clip、GEMM打包；项目冻结 WikiText2 train 与领域 calibration，各32×512=16384tokens，导出 general128/domain128/domain64。原 Target、Draft 与上游现成 AWQ 冒烟模型分别保留，不能混淆个人校准产物。

选择0/13/27层覆盖前中后深度，每层7个线性层，固定抽256个校准输入；对 scale 后、clip 前的权重和 clip+W4 的伪反量化权重做FP32 XW比较。relative MSE=平方误差和/参考平方和，是局部失真；两类来源的输入分布不同，不能当同输入因果效果。完整dev规则质量才提供共同任务评价。

推理显式使用原生 awq，记录实际后端、tensor dtype/shape/字节。embedding、lm_head、norm、bias等仍高精度。固定512 KV块比较运行显存；另在相同0.5总预算下让引擎实际分配KV。逻辑权重字节、Torch allocated/reserved、nvidia-smi进程占用和KV容量必须分开。容量是已分配token槽位，不是实测可服务同等数量请求。

事前规则默认domain128；general质量更高才换来源；group64恢复FP16质量，或代表层平均MSE降至少25%且吞吐退化不超过5%并保持候选质量时，才优先64。当前结果及选择见 [AWQ结果](../../awq-results.md)。137请求含128业务和9边界，输出长度会变化，token/s不能单独证明等工作量加速。首次shape元数据误调用失败保留，修复后从新run重测。

追问：为什么不是全模型4bit？大词表embedding/lm_head等仍FP16且scale/zero也占空间。为什么显存总占用可能不降？省出的权重空间被引擎分配给更多KV。为什么MSE好不必然业务好？局部校准失真不等于端到端离散决策质量。后续重点是质量阈值、独立重复和后端一致性；不修改目标或使用final-test调参。协议与完整复现见 [AWQ协议](../../awq-protocol.md)。

## M5：独立 RoPE+KV append 融合

目标是减少相邻小算子的launch和中间读写，不预设服务一定受其限制。上游目标路径先 rotary_embedding，后 reshape_and_cache_flash。项目自己写一个每token一个block、256线程的 CUDA kernel，读packed QKV，旋转Q/K，直接写K/V到slot；Q/K原地更新，V和未写slot保持原值，负slot跳过写cache。

支持FP16、NeoX完整D128、Q28/KV4、cache `[2,blocks,16|32,4,128]`，token行可有尾部填充。slot唯一、连续int64索引、张量不共享存储等是显式前置条件。48数值用例检查Q/K/V/未写区域，16组memcheck无错误，4类非法索引被拒绝。首次因Ninja路径编译失败保留；重建记录nvcc12.1、torch cu124、sm89。

CUDA Event在Graph中测100次等价操作，20样本，随机配对顺序，编译/分配/重置在外；两路径均重复原地旋转，属于缓存热微基准。6形状初测融合更快，但没有服务接入或TPOT结论。固定FlashInfer v0.2.1.post2的RoPE/page是分离接口，不把不同工作量的fused attention放进对照，也不声称所有新版本都无融合。

追问：为什么同时检查未写slot？越界或错误slot可在目标输出正确时破坏别的请求。为什么不能直接拿Python计时？异步GPU会让dispatch与执行混淆。为什么微基准改善不能加到模型吞吐上？占比、依赖和其他瓶颈会改变总收益。源码、原始240样本与命令见 [CUDA原型](../../rope-cache.md)。

## M6：FA2、时间线和部署

FA2复用上游能力，用显式FP32矩阵乘/softmax参考验证，八形状最大绝对误差0.0012522，在atol=rtol=0.003范围。比较对象是PyTorch原生flash SDPA，不关闭成熟flash制造优势；双方kernel trace都证明实际flash路径。两者初测接近，不能写自研Attention加速。

HTTP部署使用同64 dev请求、prompt512/1536、global concurrency1/8，各单元4热身+64测量，FP16/V0/FA2/Graph、APC与chunked关闭。单卡maxseq8；双副本每卡4、按序号轮询；TP2全局8。双副本与TP2均两卡，每卡显存比例0.45；单卡作为一张卡的资源效率参考。输出长度、质量、失败和逐请求SSE都保留，采集与Nsight正式计时分开。

最初的三部署只是不匹配冒烟，后来才补齐本矩阵，不能混用早期并发2/4的数据。TP2无NVLink并不能单凭拓扑判定慢，需分长度/并发看实测。P99在64样本下只是探索性的最大次序统计，S3需要独立重复；SSE chunk不是逐token时间。结果、建议和复现见 [部署结果](../../deployments.md)。

追问：为什么相同GPU数仍需报告预算？maxseq、KV、Graph与cache状态都会改变结果。为什么轮询在并发1未必能用满两卡？闭环请求没有同时在途，第二张卡不会凭空增加并行度。为什么不能把FA2算子数值当模型完整数值证明？模型还有投影、norm、采样及并行归约。FA2/Nsight分别见 [FA2](../../fa2-prefill.md) 与 [诊断](../../engine-diagnostics.md)。

## 分层讲解与学习状态

两分钟介绍：我以规则车载代理任务搭建固定版本vLLM实验平台，亲自实现冷热前缀淘汰、长度老化admission、运行时K控制和RoPE+KV融合CUDA，并实际训练1.5B Draft及导出三组7B AWQ。用共享/取消/抢占检查、训练中断续训、原始请求重聚合和OSS读回验证工程。部分机制有效但整体速度未稳定改善，所以默认仍保留原生FP16；量化节省权重空间与部署适用性分开报告，明确合成任务和小样本限制。

十分钟路线：先讲任务与四类数据用途，再讲运行证据与环境恢复；沿一次请求解释M1/M2，再用K宽度与teacher→LoRA→推理解释M3；用三组AWQ说明质量/局部误差/显存口径；用slot布局和Event对照解释M5；最后按长度与并发解释M6，给出默认配置及未验证范围。深入追问使用每条主线的三个问题和原始报告，不能只背百分比。

材料已生成并可供讲解；用户尚未实际复述或接受追问验证。学习清单：读懂refcount/hash生命周期；手算连续接受率和bonus边界；说明KV容量公式；解释CUDA异步计时；区分teacher loss与oracle质量；从一条原始SSE重算TTFT/TPOT。工程阶段验收不等于用户已掌握。
