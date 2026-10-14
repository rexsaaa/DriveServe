# S2 最短实现闭环与源码接入准备

状态：S1已验收，当前S2实施中；M5/M6部分项目已有实际证据，M2/M3/M4设计仍不代表实现完成。所有入口对应 vLLM v0.8.5 / `ba41cc90e8ef7f236347b2f1599eec2cbb9e1f0d`。核心修改采用固定上游 + 版本化补丁，并验证从干净源码重放，不直接留下无法恢复的 site-packages 修改。

## M1：先测量真实事件

从 `serving_chat.py`、`async_llm_engine.py`、`llm_engine.py` 到 `Scheduler.schedule`、block manager、GPU worker 和 `FlashAttentionImpl.forward` 建立完整函数链。插桩以显式开关输出 request_id、阶段、单调时钟、队列长度、实际 token/块数量。CPU enqueue/调用耗时与 GPU 完成时间分开；GPU kernel 时间交给 CUDA Event/Nsight，不能将异步 Python 调用时间当 kernel 时间。

先构造固定开发负载和原生 B0/B1，记录 Prefix 复用、长短排队、Decode 开销是否真实存在。插桩关闭/打开匹配比较；当前服务小样本不算调优基线或已证实瓶颈。

## M2：同一 GPU 池的冷热淘汰和带老化的 admission

`prefix_caching_block.py::_incr_refcount_cached_block` 在命中时增加引用，从 evictor 移除重新使用的块；`_decr_refcount_cached_block` 仅在 refcount=0 时放入 evictor；`_maybe_allocate_evicted_block_id` 淘汰后同时维护 hash 映射，并断言零引用。这些不变量必须保留。

计划按 content_hash 的有效复用计数与最近复用时间划分冷/热，仅影响零引用候选的淘汰次序；物理块重用时清理旧 hash 的策略状态，元数据有界。不能用分配次数冒充命中次数，不能触碰仍被请求引用的块。原生 `LRUEvictor` 是对照，不将已有 APC 记作个人贡献。

调度在引擎 waiting/admission 路径使用已知 prompt token 数，加入等待年龄阈值提升长请求优先级；不读取真实未来输出长度。原生、仅 cache、仅 scheduler、组合四组使用同轨迹、同 KV 预算、同冷/热起点，报告长短分组与失败；取消、共享、抢占、块重用需要真实生命周期检查。

## M3：固定最大预留内的运行时 K 与实际训练

V0 `SpecDecodeWorker.execute_model` 从 `ExecuteModelRequest.num_lookahead_slots` 读取 K 并广播；`_run_speculative_decoding_step` 用该 K 提议、评分、验证和构造输出。先在 eager、单卡、batch 范围内实现，保留上游拒绝采样和 EOS 逻辑。

候选方案是 scheduler 按最大 K 预留 KV，worker 在此上限内根据近期窗口选择实际 K，再广播给相关 worker。这样不会因临时调大 K 超过分配预算，但预留显存不会随实际 K 自动下降，须明确代价。控制器需要有滞回、最短保持期及回退固定 K，决策轨迹必须包含实际提议和有效接受计数。

上游 `spec_decode/metrics.py` 注释指出 accepted_tokens 可能包括第一个拒绝位置之后独立判定接受的 token；项目口径要统计实际连续接受前缀，排除 target bonus，不能直接照搬计数宣称 68%。动态 K 时接受长度与效率分母也不能继续当固定 K。

蒸馏采用冻结 Target 的序列级监督，先生成独立 train/dev 数据并记录过滤，再对 1.5B 做小规模实际训练；保留 optimizer、scheduler、RNG 与步数 checkpoint，并执行一次中断续训。最终评测加载训练产物，分离固定 K 下训练前后与固定 Draft 下 K 控制收益。词表零填充导出不是训练。

## M4：自主 AWQ 校准和有限敏感性

当前格式检查强制原生 `--quantization awq`；日志说明可用 awq_marlin，但本次没有测 Marlin。原生 AWQ 只接受 FP16 激活、4bit 权重，输入分组维度必须整除、输出维度满足 pack_factor=8。后续优先验证 group64/128 的真实导出和后端支持，不凭配置能写就判定可运行。

使用领域 calibration split 和有许可记录的通用语料，控制实际 token 预算。通用候选为 Salesforce/wikitext 的 wikitext-2-raw-v1 train；下载前核实 revision、许可和内容，尚未取得数据。代表层选早/中/晚层组，保持其余量化配置固定比较任务质量与误差，再决定保留高精度范围。已有上游 AWQ 权重不进入“个人校准成功”计数。

产物会占磁盘；当前临时盘约剩 16GiB，只做有理由的有限组合，先有备份收据再轮换可再生成的临时文件。固定 KV 与固定总显存两种比较分别报告，不能将 nvidia-smi 总量当权重大小。

## M5：限定 FA 后端布局的独立融合原型

`RotaryEmbedding.forward_cuda` 调用原生 rotary_embedding 原地更新 Q/K；`flash_attn.py` 随后调用 reshape_and_cache_flash。所选路径的两者分开，不能由此推断所有上游后端都无融合；正式比较前复查适用的上游融合实现。

首版支持 NeoX RoPE、FP16、head_dim128、Q28/KV4 的 GQA 和 FA KV 布局 `[2, blocks, block_size, kv_heads, head_dim]`。slot_mapping 指定写槽，负槽不写 KV；Q 的旋转语义仍要与参考一致。融合实现一次完成声明的 Q/K 旋转与 KV 写入，分别检查 Q、缓存 K/V、未写槽、边界和受支持 stride。重复有效写槽等未定义输入须拒绝或限定。

系统有 nvcc12.1 和 compute-sanitizer，实际 torch 为 cu124；扩展构建、48 组正确性和16组内存检查已完成，见 rope-cache.md。使用等价上游独立执行路径作对照，CUDA Event 排除编译、分配和预热；独立微基准不宣称端到端 TPOT 改善。

## M6：FA2 与部署分析

已有 FA2 合成 Prefill 数值/kernel 预检和单卡/TP2 请求。后续加入代表性 Prefill 长度、实际 Nsight Systems 时间线（已安装并采集真实nsys时间线，见engine-diagnostics.md），以及相同两卡总预算下的双副本/TP2 比较。副本路由、前缀亲和、客户端到达轨迹需要记录。

实际拓扑无 NVLink，P2P 检查失败，自定义 all-reduce 已关闭。先测通信/执行时间线再解释 TP2；不开启 profiling 的运行用于正式计时。现有 PyTorch trace 不替代 Nsight，不从显存变小推断利用率提高。

## 实施顺序与发布门槛

S1持久资产读回已通过；接续完善数据/负载冻结与 M1 事件，再做 M2 引擎集成和 M3 控制/训练；M4 导出、M5 独立算子和 M6 profiling 可按单机资源错开。每个有意义单元提交实现与所需测试，固定 SHA 运行后成组提交证据和累计讲解。只有全部 27 项有真实证据才能接受 S2；允许负收益，但不跳过训练、校准、自定义 kernel 或引擎接入。
