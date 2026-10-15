# DriveServe 最低要求覆盖矩阵（S4）

27/27最低要求在S2基础上保持验证；下表完整保留S3基线证据，并在后文关联S4受影响要求的新证据。阶段整体状态以 [验收报告](stages/S4/acceptance.md) 为准，单项 validated 不代替完整阶段验收。

| 要求 | 状态 | 代码/原基础证据 | S3或沿用报告 | run ID | 实际证据 | 限制 |
|---|---|---|---|---|---|---|
| M1-01 | validated | docs/engine-diagnostics.md；patches/ | docs/engine-diagnostics.md | 20261014T234421+0800-7a0f81e8d0 | 固定上游调用链与S2阅读路线保留，源码未改 | HTTP/MQ函数未逐函数计时 |
| M1-02 | validated | driveserve/engine_trace.py；reports/s2-policies-diagnostic.json | reports/s3-stability.json | 20261015T122356+0800-923b5c3f1f；20261015T124650+0800-11696fc4f1；20261015T130908+0800-88a508271b | trace开关各3次，每配置36条token/status相同；总时间差+0.259/+0.703/+0.729% | 包含运行波动，非单独隔离的因果开销 |
| M1-03 | validated | reports/s2-policies-diagnostic.json；reports/s2-nsight-engine.json | reports/s3-stability.json | 20261015T121957+0800-25fb8ec53a；20261015T124549+0800-ab03cc3fb1；20261015T130704+0800-7c3e8ba20c | Graph/4原生B1三次；逐请求/phase重聚合；S2 Nsight仍有效 | 合成KV压力；不预设业务KV访存主导 |
| M1-04 | validated | reports/s2-b1-selection.json；reports/s2-policies-b1.json | reports/s3-stability.json | 20261015T121957+0800-25fb8ec53a；20261015T124549+0800-ab03cc3fb1；20261015T130704+0800-7c3e8ba20c | Graph/4原生B1三次；逐请求/phase重聚合；S2 Nsight仍有效 | 合成KV压力；不预设业务KV访存主导 |
| M2-01 | validated | driveserve/engine_policies.py；reports/s2-policies-diagnostic.json | reports/s3-stability.json | 20261015T122257+0800-838051c8e6；20261015T124448+0800-0189156ea7；20261015T130603+0800-b72c615b1d | native/cache/scheduler/both各3次；cache/both热点992tokens；每轮四策略36条输出一致 | 同GPU零引用保留；整体吞吐收益不推广 |
| M2-02 | validated | scripts/check_policy_allocator.py；reports/s2-policies-diagnostic.json | reports/s3-boundaries.json | 20261015T132730+0800-ddf4db2eda；20261015T132852+0800-4c0d791494 | 真实allocator4检查；Graph共享/两次取消/抢占/重用/不变量 | V0非chunked单卡；swap/beam/跨卡自研路径未验 |
| M2-03 | validated | driveserve/engine_policies.py；reports/s2-policies-diagnostic.json | reports/s3-boundaries.json | 20261015T132852+0800-4c0d791494 | 老化长请求先于4条新短请求；正式三轮短组等待改善与长组退化分别保留 | admission老化不承诺全程无饥饿 |
| M2-04 | validated | reports/s2-policies-b1.json；reports/s2-policies-diagnostic.json | reports/s3-stability.json | 20261015T122257+0800-838051c8e6；20261015T124448+0800-0189156ea7；20261015T130603+0800-b72c615b1d | native/cache/scheduler/both各3次；cache/both热点992tokens；每轮四策略36条输出一致 | 同GPU零引用保留；整体吞吐收益不推广 |
| M3-01 | validated | reports/s2-spec-v3-validation.json；ADR0002 | reports/s3-stability.json | 20261015T122607+0800-b27ba90790；20261015T124753+0800-bb41d345a7；20261015T131348+0800-974f59428b | 原fixed Graph三轮每轮137/137与Target token相同 | FP16有限负载；eager历史数值分歧不删 |
| M3-02 | validated | driveserve/spec_control.py；reports/s2-spec-v3-validation.json | reports/s3-boundaries.json | 20261015T133245+0800-b1950426b4 | Graph随机与greedy、实际K切换/拒绝/bonus/EOS/长度/上下文；S2 CUDA分布修复验证保留 | 随机序列不要求逐token相同；非所有模型分布证明 |
| M3-03 | validated | reports/s2-spec-v3-validation.json；s2-spec-top5.json | reports/s3-boundaries.json | 20261015T133245+0800-b1950426b4 | Graph随机与greedy、实际K切换/拒绝/bonus/EOS/长度/上下文；S2 CUDA分布修复验证保留 | 随机序列不要求逐token相同；非所有模型分布证明 |
| M3-04 | validated | scripts/train_draft.py；reports/s2-training-128.json；s2-training-recovery.json | reports/s3-boundaries.json | 20261015T132729+0800-5ea0a1a933 | 128步LoRA及全状态SIGTERM恢复沿用S2；新审计四段训练ID均为合格train472 | 序列级蒸馏；不重复训练；final-test未送模型 |
| M3-05 | validated | reports/s2-distillation.json；s2-trained-assets-oss.json | reports/s3-stability.json | 20261015T122720+0800-af18356140；20261015T124910+0800-8be5ad0342；20261015T131012+0800-53f0706411 | 原/新fixed及新adaptive贡献分离；fixed接受率另3次trace；Graph业务每轮121/128 | 动态K无稳定增量优势；fixed TTFT增加 |
| M4-01 | validated | scripts/quantize_awq.py；reports/s2-awq.json；s2-awq-g128-oss.json | reports/s3-awq-reproducibility.json | 20261015T115848+0800-1eee776d86 | 独立28层校准13文件和21局部误差精确复现；复用原OSS对象 | 同环境同recipe，不保证跨硬件精确相同 |
| M4-02 | validated | scripts/freeze_awq_data.py；reports/s2-awq.json | reports/s3-stability.json | 20261015T123033+0800-9f34b026ed；20261015T125243+0800-a64ed19437；20261015T131735+0800-2c839decfa | 三组AWQ/Marlin各3次；general118未过120门槛，领域128/64及Marlin121 | 输出长度改变；不同后端long-1输出不同 |
| M4-03 | validated | scripts/quantize_awq.py；reports/s2-awq.json | reports/s3-awq-reproducibility.json | 20261015T111741+0800-284a52ba00；20261015T115848+0800-1eee776d86 | 0/13/27层各7线性模块；21误差独立重现；group64改善23.6744%未达25%切换线 | 局部校准失真；不等于任务损失 |
| M4-04 | validated | scripts/benchmark_speculation.py；reports/s2-awq.json | reports/s3-stability.json | 20261015T123033+0800-9f34b026ed；20261015T125243+0800-a64ed19437；20261015T131735+0800-2c839decfa | 三组AWQ/Marlin各3次；general118未过120门槛，领域128/64及Marlin121 | 输出长度改变；不同后端long-1输出不同 |
| M4-05 | validated | scripts/analyze_awq.py；reports/s2-awq.json | reports/s2-awq.json | 20261015T112635+0800-330eac66b8；20261015T112738+0800-819e8c611c | 权重15.231→5.571GB、固定KV8192及同总预算容量沿用；S3每run显存与实际512块复核 | 容量非满载服务；未验证物理24GB |
| M5-01 | validated | docs/rope-cache.md；reports/s2-rope-cache.json | docs/rope-cache.md | 20261014T232203+0800-63f35c079d | 固定vLLM/FlashInfer源码能力对照保留；CUDA源修复前后未变 | 仅固定上游版本；无公平同设备同形状融合接口不强行比较 |
| M5-02 | validated | csrc/rope_cache.cu；reports/s2-rope-cache.json；SHA 72cce3a | reports/s3-stability.json | 20261015T123302+0800-9d535c5f49；20261015T125611+0800-001acb43f6；20261015T131822+0800-c97527d390 | 自编独立融合CUDA原型；每轮48正确性和六shape Event | FP16 NeoX Q28/KV4 D128；无服务接入 |
| M5-03 | validated | csrc/rope_cache.cu；reports/s2-rope-cache.json；SHA 72cce3a | reports/s3-boundaries.json | 20261015T133043+0800-fa4030991a；20261015T133046+0800-0aa1b3ebba；20261015T133051+0800-4bf0dd851e；20261015T133100+0800-df13969b6d | 索引别名4类前后探针、24拒绝/只读alias正例、48数值及16 memcheck零错误 | 前探针拦截dispatch，未执行危险kernel；未穷尽输入 |
| M5-04 | validated | csrc/rope_cache.cu；reports/s2-rope-cache.json；SHA 72cce3a | reports/s3-stability.json | 20261015T123302+0800-9d535c5f49；20261015T125611+0800-001acb43f6；20261015T131822+0800-c97527d390 | 六形状×三进程×各20 Event样本；保留每run中位数及波动 | Graph缓存热微基准；不推导端到端收益 |
| M5-05 | validated | docs/rope-cache.md；reports/s2-rope-cache.json | docs/rope-cache.md | 20261014T232203+0800-63f35c079d | 固定vLLM/FlashInfer源码能力对照保留；CUDA源修复前后未变 | 仅固定上游版本；无公平同设备同形状融合接口不强行比较 |
| M6-01 | validated | scripts/benchmark_fa2.py；reports/s2-fa2-prefill.json | reports/s3-stability.json | 20261015T123313+0800-60d76bbef9；20261015T125622+0800-a070db4db3；20261015T131834+0800-0c1e863f7d | 八形状×三进程；实际FA2与torch flash路径、FP32参考和Event | 复用上游FA2，非自研Attention |
| M6-02 | validated | scripts/analyze_nsys.py；reports/s2-nsight-engine.json | reports/s2-nsight-engine.json | 20261014T235030+0800-0698208fe6 | 70,804 kernel真实时间线保留；正式计时不启Nsight | 间隙不等于GPU空闲；无TP2因果通信profile |
| M6-03 | validated | reports/s1-tp2-smoke.json；reports/s2-dual-replica-smoke.json | reports/s3-stability.json | 20261015T123752+0800-40b024fa79；20261015T125855+0800-5f98fb2303；20261015T131900+0800-9ec6aac84b | 三部署各3次，2304/2304完成；两长度/两并发、轮询/两卡预算；TP2波动与质量差异保留 | 每cell64 P99探索；首轮TP2更快原因未知；无开环SLO |
| M6-04 | validated | scripts/benchmark_deployments.py；reports/s2-deployments.json | reports/s3-stability.json | 20261015T123752+0800-40b024fa79；20261015T125855+0800-5f98fb2303；20261015T131900+0800-9ec6aac84b | 三部署各3次，2304/2304完成；两长度/两并发、轮询/两卡预算；TP2波动与质量差异保留 | 每cell64 P99探索；首轮TP2更快原因未知；无开环SLO |

每项artifact为对应experiments/runs/<run_id>/manifest.json所列原始文件，hash通过证据审计；正式源码SHA由run manifest及reports/s3-timing-*-state.json关联，不能将文档提交SHA替代实验SHA。累计讲解见 [README](stages/S4/README.md)，源码路线、追问与边界覆盖全部六线；六条简历见 [resume](stages/S4/resume.md)。

## S4增量（其余要求沿用上述S3已验收能力）

| 要求 | 实际新增与验证 | code/run/report | 限制 |
|---|---|---|---|
| M1-02/M1-03 | 正式计时与维护诊断分离，记录真实take/expire/compact及GC；不将方法名当重建 | diagnose_heap_maintenance.py；143023-7f85f5a6d8；s4-heap-maintenance.json | CPU诊断可扰动性能；不归因旧run未记事件 |
| M2-01 | 真实引擎heap索引、冷/热/到期三堆、版本与有界重建；20k差分/5000更新/12TTL边界 | 8728669；135301-9d76ee90ac；s4-boundaries.json | 有界空间不保证单操作对数上界 |
| M2-02 | scan/heap各4真实allocator；Graph两组各792快照/32共享块/2取消/1抢占，16输出/status一致 | s4-boundaries-state.json；s4-boundaries.json | V0非chunked单卡受支持路径 |
| M2-03/M2-04 | native/scheduler/scan cache/both/heap cache/both各3次36请求；每轮输出一致、heap/scan复用相同 | 05bcac1/d37aa46/b8e91be；s4-depth.json的run清单 | 小池服务无明确总体加速；长组代价保留 |
| M5-01/M5-05 | 固定上游能力审计沿用，原CUDA源与S3相同，新v2独立入口及v1/上游等工作量消融 | rope_cache_tiled.cu/rope_cache_v2.cpp；s4-boundaries.json | 不宣称新版上游普遍无融合 |
| M5-02/M5-03 | scalar tile/half2/auto实跑，275全检查/99memcheck，三入口各24拒绝、只读alias正例 | 8728669；135320-4d5332d0b4等，s4-boundaries.json | 有限FP16/布局范围，非服务接入 |
| M5-04 | 六shape×五方案×三进程，各20 Event样本/Graph100操作 | s4-depth.json；s4-timing-r1/r2/r3-state.json | 不计host同步/dispatch；大T scalar退化 |

每个run均包含manifest里的code/environment/model/data/config与assets hash；完整原始记录由证据审计及独立GitHub复算核验。M3训练/分布、M4AWQ、M6FA2/三部署未改执行逻辑，沿用上述S3实现和局限，不重做训练制造进度。累计讲解见本目录README，S4两个专题与六条事实简历见resume。

## S5新增证据（阶段尚在执行，尚未验收）

S1–S4已验收能力持续保留；下列开发证据不替代S5三轮正式重复、冻结final-test质量、资产和远端复算门槛。

| 要求 | 已有S5实际证据 | 当前限制与后续 |
|---|---|---|
| M1-02/M1-03 | openloop.py记录planned/header-sent/首末chunk/finish，全程deadline含semaphore；39项CPU含真实HTTP异常fixture；三部署开发384请求完成 | fixture不是模型成绩；正式队列、尾部、goodput等待三轮 |
| M2-02/M2-04 | s5-business-development.json：native/cache/scheduler/both各128输出一致、121正确、21824cached tokens | 自然业务没有额外缓存复用；真实压力和生命周期沿用S4，不据自然结果扩大支持范围 |
| M3-01/M3-02/M3-03 | s5-apc-compatibility.json：FP16/AWQ各Target/fixed/adaptive的四候选每组137输出一致；随机AWQ trace实际K切换/拒绝/bonus/EOS/截断 | 与同一quantized Target比较；不是整体语言分布统计证明；仍是单卡V0非chunked |
| M3-04/M3-05 | 训练Draft实际加载到上述所有spec配置；128步序列蒸馏和中断恢复沿用S2/S3 | 不重训冒充新增进展；正式FP16与AWQ贡献对照未完成 |
| M4-01/M4-05 | 实际解析Target AWQ/Draft None，输出与Target匹配；旧三组校准、层误差和资源报告保留 | AWQ×spec开发显示负收益，未默认开启；最终质量门槛事前冻结但未运行 |
| M5-01至M5-05 | S4冻结CUDA/三轮/275 correctness/99memcheck沿用，源码未改 | 独立算子，未接服务；不把新服务收益归因CUDA |
| M6-03/M6-04 | s5-openloop-development-v2.json：3部署×4cell×32请求，4/32req/s，成功缓存reset与失败修复记录 | 仅开发小样本；正式每cell256×3、含drain/失败/质量，P99仍探索性；S3 TP2首轮原因未知 |

正式计划configs/s5-timing-plan-v2-r1/r2/r3.json已冻结；旧v1模型矩阵APC关闭、从未执行，保留以说明选择变化。configs/s5-final-quality.json固定十profile与256完整test，尚未送模型；不能据最终结果调参与反复选择。S5验收状态以独立acceptance报告为准。

S5正式三轮现已完成：M2四策略各3次128业务、输出相同且复用21824tokens；M3/M4六模型各3次137请求、12组spec与同quant Target逐token相同，均121/128。M6九HTTP进程9216/9216完成，完整分布/发送滞后/失败分母/SLO及质量goodput由reports/s5-openloop.json重算；P99仍探索性。三轮表docs/s5-results.md；最终test/GPU回归/资产和独立checkout尚待完成。
