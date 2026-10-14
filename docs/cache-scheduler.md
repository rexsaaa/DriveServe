# S2 真实引擎缓存与长度调度

本页先记录可执行实现与冻结协议；正式 GPU 证据待固定代码后填入，不能据此认定 M2 通过。

## 接入与状态

`patches/vllm-v0.8.5-policies.patch` 在固定上游 ba41cc90 上重放，包含既有观察器；`build_vllm_overlay.py --patch-lock` 校验全部原始和目标文件 hash，只创建隔离 overlay。原 wheel 与观察器 v1 overlay 保留。

`driveserve/engine_policies.py::ColdHotEvictor` 替换原分配器的 evictor，不改引用计数、hash 构造、block table 或计算。有效复用来自 `Scheduler.schedule` 构造首次 Prefill metadata 时的连续 computed prefix，仅计模型真正跳过的完整块；完整 prompt 命中时最后一个 token 会重算，因此保守地不计该末尾块。分配命中、同批去重、Decode 和 promotion 均不累加。每个 content_hash 连续保留期内有效复用两次成为热块；30 秒未复用后回冷，重计次数。该 TTL 为 monotonic 时间，不是请求轮数。

只有上游零引用候选可被淘汰。先冷后热，再依最近访问时间、最长哈希前缀、block_id 排序；热块仍可在所有候选均热时被淘汰。重新激活仅移出候选，保留历史；实际淘汰清除历史，reset 产生新 evictor。元数据受 resident hash 数限制。首版选择为 O(空闲缓存块数) 扫描，维护成本需实测；没有 CPU/GPU 分层存储，也不能据 Prefill 复用宣称减少每个 Decode token 的 KV 读取。

`Scheduler.add_seq_group` 保存 monotonic 入队时间；`_schedule_prefills` 内直接重排 waiting deque，等待满 0.25 秒的请求按入队时间优先，其余按已知 prompt 长度排序。同优先级稳定，不读取未来输出长度。仍执行原生 token、KV、max_seqs 等 admission 检查；老化只保证顺序优先，不能越过资源不足。显式支持 V0、非 chunked、single-step、FCFS、n=1 的当前配置；不宣称覆盖 speculative、swap、beam、TP 或 chunked 路径。正常抢占回队保留原入队年龄。

## 检查与冻结实验

CPU 检查覆盖热保护/TTL/清理与长度老化；`scripts/check_policy_allocator.py` 在真实上游分配器上检查活动共享块不可淘汰、80 轮块重用、ref/hash 一致性、reset 拒绝活动块、promotion 不计复用、mutable fork/COW。

`configs/s2-policies.json` 固定单卡 FP16、128×16 KV token 容量、max_seqs=4、非 chunked eager、输出32、seed23。`benchmark_policies.py --variant native|cache|scheduler|both` 四组使用同一 barrier wave 序列、相同 token 输入和缓存起点；两次复用后的热 prefix 遭遇冷流量，再探测；另有三轮混合长度。每个场景重置缓存，模型 warmup 与计量流量分开。无外部到达率或业务质量声明。记录逐请求 token、首次输出与后续观察时间、上游 queue metrics、cached tokens、实际 phase 时长、失败及取消。

`--suite lifecycle --trace` 单独执行实际 running/waiting 取消、共享、老化与 Decode 增长的内存压力；每一步检查 allocator 及活动 block table 不变量，属于侵入式正确性实验，不用于性能排名。core 仅在 phase 结束后检查，检查时间在 phase 计时外。`--trace` 用于因果观察，关闭后另做同条件计时；单次结果不是最终尾延迟或严谨显著性结论。

复现：先用锁定 GPU Python 建 overlay，再在干净代码提交运行 `scripts/record_command.py --stage S2 --kind policy-core --formal -- env PYTHONHASHSEED=23 /hy-tmp/driveserve/venv-rebuilt/bin/python scripts/benchmark_policies.py --variant native --trace`，其余 variant 独立运行。正式报告必须引用实际 code SHA、run ID 和 workload hash。

## 压力验证发现的上游缓存计数问题

首个正式 core/native trace：外层 `20261015T010727+0800-3abeb97674`、内层 `20261015T010738+0800-a533eb046d`，SHA f46b334。在 mixed-0-3 被 RECOMPUTE 抢占后，等待期间原前缀块被逐出，但 `ComputedBlocksTracker.get_num_cached_tokens` 对所有 Prefill 状态复用旧数量，含 WAITING 请求；重新分配时计数覆盖一个未 computed 的新块，真实复用断言失败。保留完整日志，不将该运行计入性能成绩。

最小复现 `check_waiting_prefix.py --expect-stale` 在未改动的原 wheel 实际 CpuGpuBlockAllocator/Sequence/ComputedBlocksTracker 上，2个块池缓存4 tokens，淘汰后仍返回4，正确期望为0。开发复现 `20261015T011012+0800-b4a897866d` 为 dirty探索，后续在固定SHA再次记录。

修复只允许 RUNNING 中连续 Prefill 复用 tracker 的旧计数，WAITING 每次查询重新查实际 resident hash。所有四组共享此正确性修复；表格的 native 因此表示原生 LRU/FCFS + 修复，不冒称未经修改的 B0。上游原wheel不动，v1失败overlay保留，新建v2。该修复与冷热/长度策略分离，chunked整体尚未验证。
