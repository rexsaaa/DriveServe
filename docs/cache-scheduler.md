# S2 真实引擎缓存与长度调度

> S3更新：策略三轮比较与Graph生命周期已完成，见[独立重复](s3-stability.md)、[边界报告](../reports/s3-boundaries.json)和[S3累计讲解](stages/S3/README.md)。下文保留S2实现与初测来源，不把旧单次结果混成S3计时。

本页记录实现、失败修复和真实 GPU 验证。M2 最低范围已有证据；累计阶段状态见stages/S2/acceptance.md。

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

## 固定 SHA 的实机结果

所有成功GPU运行代码为 `890bb0b`；未修改原wheel。21项CPU检查：`20261015T011138+0800-8533f297ad`；4项真实分配器检查：`20261015T011132+0800-0fb6412fb9`；原wheel陈旧计数复现与修复后回归：`20261015T011119+0800-e8b715c270`、`20261015T011125+0800-45c20fee11`。原版4→4、修复4→0均实测通过各自预期。

开启观察器的四组各36条、关闭观察器的四组各36条，总计288条成功、无失败，各组输入hash一致且输出token逐条一致。四组均使用相同正确性补丁。以下是关闭观察器、每组一次的描述性观测；吞吐=1152输出tokens/11个计量phase时长和。短组<512tokens，长组≥512；阶段外模型加载、Graph编译、reset和不变量检查不计入。没有HTTP开销、最终P99或统计显著性声明。

| 策略 | run ID | 计量秒数 | 输出token/s | 短组平均TTFT ms | 长组平均TTFT ms | 冲刷后热点cached tokens |
|---|---|---:|---:|---:|---:|---:|
| native | 20261015T012037+0800-9b08a6bcd4 | 10.8236 | 106.43 | 680.33 | 309.16 | 0 |
| cache | 20261015T011939+0800-d80494c6ab | 10.7381 | 107.28 | 679.94 | 303.81 | 992 |
| scheduler | 20261015T011840+0800-1f5f58762e | 10.9647 | 105.06 | 76.15 | 595.53 | 0 |
| both | 20261015T011742+0800-72731f17ed | 10.8344 | 106.33 | 77.96 | 588.67 | 992 |

冷热保留使两个512-token热点在冷流量后仍跳过各496 tokens；完整原生LRU策略在该场景为0。省去Prefill不意味着Decode每token减少KV读取；热点场景只有两条探测请求，不能推广为生产加速百分比。长度策略在实际 `_schedule_prefills` 改变9次队列顺序；混合场景的RECOMPUTE抢占由3次变为0，短请求更早，但长请求平均首token更慢。这是可观测的取舍，不保证所有负载有益。下一步用有限原生参数调优形成B1，协议见 baseline-protocol.md。

生命周期独立运行：native `20261015T011527+0800-65f798c630`，both `20261015T011629+0800-568d0d26a1`。各16个请求，14完成、2主动取消（running/waiting各一），结果逐项一致；各792次allocator/block-table检查，结束free_total=128/128；各一次真实RECOMPUTE抢占。取消前两条shared请求共享32个已computed块；取消一条不破坏另一条。人为等待0.27秒后，aged-long在4条96token新请求之前被admission，老化机制实测生效。该有限场景不是无限流量下的公平性证明。

原始 requests、workload、phases、逐步snapshots、events与外层command.log均保留；`scripts/analyze_policies.py` 先逐文件verify_assets，再重聚合，报告为 reports/s2-policies-diagnostic.json 与 reports/s2-policies-timing.json。淘汰统计从计量请求事件窗口选取，排除warmup和显式reset；原生无淘汰事件插桩时用null，不把缺测记作0。

### 可追问的实现与证据

- 为什么统计位置在首次Prefill metadata？分配/去重命中不等于减少实际计算，完整命中最后token还要重算；使用真实跳过的完整块更保守。
- 为什么不能只用缓存命中率解释快慢？LRU与冷热的扫描成本不同，长度排序同时改变批次与抢占；报告分开Prefill复用、队列、吞吐、长短TTFT与负面影响。
- 什么保证不淘汰活动块？候选仍由上游refcount降到0时加入，实际选择仅遍历free_table，allocator原断言、独立分配器测试和GPU逐步block-table检查共同约束。
- 为什么失败不是把断言删掉？最小原wheel复现确认WAITING计数陈旧，修正tracker状态条件再重放同一压力负载，保留失败日志和前后SHA。
- 能写什么简历事实？“在固定vLLM V0引擎接入冷热前缀保留与带老化的长度admission；完成四组真实对照、共享/取消/抢占与KV不变量验证，记录短长请求取舍。”不能写已达生产P99目标或最终端到端提升。

## 调优原生 B1 下的主比较

有限预算与选择规则先在5bcc38d固定，随后保留原版B0及三个Graph候选。全部36条均与已验证参考token一致。未改wheel B0为106.808 token/s；原生策略+共同正确性修复的候选为eager/4：106.434，Graph/2：95.154，Graph/4：109.649，Graph/8：109.635。按预定计量总时长最小规则选择Graph/4；它与Graph/8仅约1.3ms差，不能宣称统计优越。选择重放脚本 `scripts/select_baseline.py`，候选原始记录与配置见 reports/s2-b1-selection.json。

保持Graph/4及128块KV不变，按同协议运行个人策略，结果见下表。四组各36成功、0失败，全部输入hash及输出token一致，code SHA均5bcc38d。Graph捕获在计量前；日志确认原生路径实际捕获3个形状，Graph/4约0.05GiB捕获开销。各一次独立运行，仅作为S2初步诊断，S3重复与服务负载仍待做。

| 策略 | run ID | 输出token/s | 短组平均TTFT ms | 长组平均TTFT ms | 冲刷后热点cached tokens |
|---|---|---:|---:|---:|---:|
| native | 20261015T012606+0800-ce5b9d7e98 | 109.649 | 665.36 | 303.78 | 0 |
| cache | 20261015T012846+0800-93ef43c867 | 110.042 | 668.75 | 300.65 | 992 |
| scheduler | 20261015T012944+0800-bc12157ab2 | 108.941 | 75.82 | 579.71 | 0 |
| both | 20261015T013044+0800-17a808ecd3 | 109.469 | 76.83 | 575.48 | 992 |

这里没有稳定的整体吞吐提升证据，保留原生策略作为默认基线。冷热规则在特定热点冲刷中减少Prefill，长度规则缩短短请求等待但推迟长请求；二者保留显式开关用于后续有目标的负载分析。不能把冷热的局部TTFT收益推广为所有流量收益，也不能把原生CUDA Graph的改善归为个人实现。

M2-04的四组主比较最低要求至此满足；M1也形成了B0、有限调优B1、前缀/排队/Decode证据及下一步诊断。六线完整S2仍未验收。关键正确性决策见 docs/decisions/0003-waiting-prefix-correctness.md。
