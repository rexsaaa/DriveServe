# DriveServe 最低要求覆盖矩阵

依据主规范第 4 节；S1已验收，当前S2 in_progress；M1四项、M2四项、M3五项、M5五项、M6-01/02/03已有最低范围单项验证（21/27），其余6项仍待补齐。源码预检和 CPU 基础工具不等于主线验收。

状态：planned → in_progress → implemented → validated；实际阻塞保留原要求并记录原因。S2 必须逐项满足以下 27 项。

| 要求 ID | 最低验收阶段 | 要求摘要 | 状态 | 代码/报告位置 | 实验 run ID | artifact 引用 | 累计讲解 | 限制 |
|---|---|---|---|---|---|---|---|---|
| M1-01 | S2 | 锁定源码与相关调用链 | validated | docs/engine-diagnostics.md；patches/ | 20261014T234421+0800-7a0f81e8d0；20261014T235030+0800-0698208fe6 | 引擎events与Nsight；固定上游源码 | docs/engine-diagnostics.md | 明确MQ/直接异步分支；HTTP/MQ边界未逐函数测时 |
| M1-02 | S2 | 可开关真实运行时插桩 | validated | driveserve/engine_trace.py；reports/s2-policies-diagnostic.json | 20261015T011130+0800-3793338358；20261015T012037+0800-9b08a6bcd4 | 开启/关闭各36条token一致、原始events与phase计时 | docs/engine-diagnostics.md | 两套开关观测；非严格因果开销，S3独立重复待补 |
| M1-03 | S2 | 前缀、排队和 Decode 实际分析 | validated | reports/s2-policies-diagnostic.json；reports/s2-nsight-engine.json | 20261015T011130+0800-3793338358；20261014T235030+0800-0698208fe6 | 长短等待、热点冲刷、真实RECOMPUTE、GPU时间线 | docs/engine-diagnostics.md | 合成受限KV场景；不是业务瓶颈或最终尾延迟 |
| M1-04 | S2 | baseline 与初步诊断 | validated | reports/s2-b1-selection.json；reports/s2-policies-b1.json | 20261015T012409+0800-cdccab201c；20261015T012606+0800-ce5b9d7e98 | B0/四候选/原始逐请求和phase计量 | docs/cache-scheduler.md | 合成引擎B1；单次有限调优，服务基线与S3重复待做 |
| M2-01 | S2 | 冷热缓存策略接入真实引擎 | validated | driveserve/engine_policies.py；reports/s2-policies-diagnostic.json | 20261015T011228+0800-120d7bc9b3；20261015T011939+0800-d80494c6ab | prefix_reuse/evict事件，992token热点保留 | docs/cache-scheduler.md | V0非chunked；同GPU池；O(空闲候选)淘汰 |
| M2-02 | S2 | KV 生命周期与不变量 | validated | scripts/check_policy_allocator.py；reports/s2-policies-diagnostic.json | 20261015T011132+0800-0fb6412fb9；20261015T011629+0800-568d0d26a1 | 真实allocator4项；GPU792快照、取消/共享/抢占 | docs/cache-scheduler.md | 支持范围内验证；swap/beam/跨卡路径未验 |
| M2-03 | S2 | 真实长度感知与基本公平性 | validated | driveserve/engine_policies.py；reports/s2-policies-diagnostic.json | 20261015T011327+0800-1fbc3669fc；20261015T011629+0800-568d0d26a1 | 9次实际重排、aged-long先于新短请求 | docs/cache-scheduler.md | 老化只保证admission顺序；长请求TTFT有退化 |
| M2-04 | S2 | cache/scheduler 四组对照 | validated | reports/s2-policies-b1.json；reports/s2-policies-diagnostic.json | 5bcc38d下Graph/4四组；run清单见报告 | 输入hash和输出一致、长短等待/TTFT/吞吐/失败 | docs/cache-scheduler.md | 一次B1主比较，无稳定整体吞吐收益；S3独立重复待做 |
| M3-01 | S2 | 模型兼容与固定 K 基线 | validated | reports/s2-spec-v3-validation.json；ADR0002 | 20261015T020944+0800-375dd7bfab；020849-9778d9fb9b | 固定K41/41贪心相同、32条随机业务31正确，与target相同 | docs/speculation.md | 对齐词表派生模型；仅V0单卡FP16 PyTorch sampler |
| M3-02 | S2 | 滑动窗口驱动运行时 K | validated | driveserve/spec_control.py；reports/s2-spec-v3-validation.json | 20261015T021050+0800-5b2fd720a9；020654-7938b0451c | 实际K变更、proposal/verification宽度、连续接受分母 | docs/speculation.md | 最大K预留；CPU同步计数；无整体加速承诺 |
| M3-03 | S2 | 验证/回滚/结束与控制轨迹 | validated | reports/s2-spec-v3-validation.json；s2-spec-top5.json | 20261015T020529+0800-9bdef7cb4e；021050-5b2fd720a9 | 拒绝/bonus/EOS/长度/上下文、120000原生分布及10000修复采样、2286token均为各自target argmax | docs/speculation.md | 动态39/41贪心一致；两处同前缀FP16近似/并列证据保留，非逐token等同保证 |
| M3-04 | S2 | 实际 Draft 蒸馏训练与产物 | validated | scripts/train_draft.py；reports/s2-training-128.json；s2-training-recovery.json | 20261015T021108+0800-6af044d14a；020833-07a7e69dc5 | 472条合格教师训练、128步LoRA；实际SIGTERM全状态等同；模型/完整checkpoint OSS读回 | docs/distillation-protocol.md | 小规模序列级蒸馏；合成任务；不训练Target、不做logit蒸馏 |
| M3-05 | S2 | 训练后真实评测与贡献分离 | validated | reports/s2-distillation.json；s2-trained-assets-oss.json | 20261015T021836+0800-852a602bf2；022049-74a7f6e583；022202-34d8d09bd2 | 同137请求原/新fixed及新adaptive；全部128业务121正确；接受率83.90%/86.92%/88.61% | docs/distillation-protocol.md | 单次带trace；未超过Target吞吐；动态136/137序列一致，long-2既有数值边界保留 |
| M4-01 | S2 | AWQ 校准导出与真实部署 | in_progress | reports/s1-awq-format-smoke.json | 20261014T223537+0800-a2fa74210b | 上游模型 provenance | docs/stages/S1/README.md | 仅上游 AWQ 加载成功，自主校准/导出未做 |
| M4-02 | S2 | 通用/领域校准比较 | planned | 无 | 无 | 无 | docs/stages/S1/README.md | 尚未实现或实机验证 |
| M4-03 | S2 | 代表层/层组敏感性实验 | planned | 无 | 无 | 无 | docs/stages/S1/README.md | 尚未实现或实机验证 |
| M4-04 | S2 | 多 Group Size 与性能/质量 | planned | 无 | 无 | 无 | docs/stages/S1/README.md | 尚未实现或实机验证 |
| M4-05 | S2 | 显存口径与混合精度范围 | planned | 无 | 无 | 无 | docs/stages/S1/README.md | 尚未实现或实机验证 |
| M5-01 | S2 | 数据布局与上游能力核查 | validated | docs/rope-cache.md；reports/s2-rope-cache.json | 20261014T232203+0800-63f35c079d | 固定 vLLM 与 FlashInfer 源码 hash | docs/rope-cache.md | 限定固定vLLM/FlashInfer版本与独立算子；S3独立重复待补 |
| M5-02 | S2 | 自定义真实融合 CUDA 实现 | validated | csrc/rope_cache.cu；reports/s2-rope-cache.json；SHA 72cce3a | 20261014T232203+0800-63f35c079d | correctness.json / timings.json / sanitizer command.log | docs/rope-cache.md | 独立 FP16 Q28/KV4/D128；未接入服务 |
| M5-03 | S2 | 数值、边界与内存检查 | validated | csrc/rope_cache.cu；reports/s2-rope-cache.json；SHA 72cce3a | 20261014T232203+0800-63f35c079d；20261014T232723+0800-3129a211fa | correctness.json / timings.json / sanitizer command.log | docs/rope-cache.md | 48 组正确性、16 组 memcheck；未穷尽全部输入 |
| M5-04 | S2 | 等价 CUDA Event 微基准 | validated | csrc/rope_cache.cu；reports/s2-rope-cache.json；SHA 72cce3a | 20261014T232203+0800-63f35c079d | correctness.json / timings.json / sanitizer command.log | docs/rope-cache.md | 6 形状、各20样本；初次 graph 微基准，独立重复待补 |
| M5-05 | S2 | 源码/计时与适用上游对照 | validated | docs/rope-cache.md；reports/s2-rope-cache.json | 20261014T232203+0800-63f35c079d | 固定 vLLM 与 FlashInfer 源码 hash | docs/rope-cache.md | 限定固定vLLM/FlashInfer版本与独立算子；S3独立重复待补 |
| M6-01 | S2 | 实际 FA2 Prefill 评测 | validated | scripts/benchmark_fa2.py；reports/s2-fa2-prefill.json | 20261014T235957+0800-280a7d5829 | 8形状数值/320计时样本/16份kernel trace | docs/fa2-prefill.md | 原生flash对照，非自研Attention；独立重复与服务性能另验 |
| M6-02 | S2 | 真实 Nsight Systems 时间线 | validated | scripts/analyze_nsys.py；reports/s2-nsight-engine.json | 20261014T235030+0800-0698208fe6 | reports/s2-profile-assets.json；原始nsys-rep | docs/engine-diagnostics.md | 单卡合成负载；kernel间隙不等于GPU空闲，TP2通信待补 |
| M6-03 | S2 | 单卡/双副本/TP2 实机运行 | validated | reports/s1-tp2-smoke.json；reports/s2-dual-replica-smoke.json | 20261014T221618+0800-9dac230faf；20261015T002157+0800-1d676c0ba7 | 原始服务/客户端/物理GPU快照 | docs/stages/S2/README.md | 三部署均实跑；并发等配置未匹配，公平性能建议属M6-04 |
| M6-04 | S2 | 多长度/并发部署建议 | planned | 无 | 无 | 无 | docs/stages/S1/README.md | 尚未实现或实机验证 |

S1 基础验证另见阶段报告；此矩阵没有将 mock、metadata 或上游代码标为个人实现完成。后续阶段报告保留对应覆盖快照。
