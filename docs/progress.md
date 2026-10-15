# DriveServe 当前进度

更新：2026-10-15T11:24:49.701321+08:00（Asia/Shanghai）。**S1 accepted，S2 in_progress，21/27 最低要求已验证**。无 S2 tag；S3–S6 尚未验收。M1 四项、M2 四项、M3 五项、M5 五项、M6-01/02/03 达到声明范围；仍需补齐 M4 五项和 M6-04。逐项证据见 [覆盖矩阵](coverage.md)，累计讲解见 [S2](stages/S2/README.md)。

## 本次恢复与正在运行的工作

此前会话改为只读并发生 bubblewrap namespace 错误，现已恢复执行权限。GitHub main 已读回确认7002e6b，工作树接管时干净。此前两组AWQ均已完成28层和独立导出，不能重新运行冒充新进度。

- 已完成domain/group128：20261015T022410+0800-8f072791c4，/hy-tmp/driveserve/models/awq-domain-g128-v1。
- 已完成general/group128：20261015T022843+0800-a2b942b160，artifacts/models/awq-general-g128-v1。
- 两组各导出5,582,377,217bytes；原始run资产逐项hash已核验，各有28层进度和21项代表线性层误差。实际原生AWQ加载各137请求完成：领域121/128业务正确、通用118/128；此时GPU1同时校准，时间仅作诊断，不进性能主对照。
- GPU1正在domain/group64：父20261015T111726+0800-faf9d8406c，内20261015T111741+0800-284a52ba00，输出artifacts/models/awq-domain-g64-v1。每层原子保存layer-XX.json及心跳，无法完整续量化时新run重做整组。
- group128两模型的OSS留存正在20261015T111737+0800-33240e94e0，收据artifacts/backup/s2-awq-g128/receipt.json；未读回完成前不记为持久化成功。

当前任务的进程指纹快照见 [active-tasks.json](../reports/active-tasks.json)。接管时重新验证manifest、PID/boot_id/start_ticks和GPU占用；快照不是当前存活证明。没有自动开机或agent自动唤醒。

## 下一步执行顺序

1. 等group64实际导出并校验，完成其原生AWQ加载；保留三个量化产物及云端完整读回。
2. 两张GPU都空闲后，串行进行FP16/general128/domain128/domain64的固定512 KV块主比较；另外测FP16与选择的量化配置在同0.5总显存比例下的实际KV容量。入口scripts/benchmark_speculation.py，--purpose timing禁止trace/logprobs并检查GPU独占，--automatic-kv为容量配置。
3. 聚合校准来源、group、质量、代表层局部误差、权重/运行显存，按docs/awq-protocol.md事前规则选择候选；不能用输出token变多后的吞吐单独宣称等工作量加速。
4. 两卡空闲时运行scripts/benchmark_deployments.py的single/replica/tp2；相同64 dev请求，prompt512/1536、global concurrency1/8、每卡利用率0.45、全局maxseq8、Graph、APC关闭。双副本和TP2同两卡预算，单卡单独计资源效率。首次P99仅探索。
5. M4五项及M6-04证据、恢复可获取性和累计材料齐全后才验收S2并打tag。继续S3独立重复/边界，S4至少两个实测深化，S5组合及最终测试，S6干净checkout与发布材料。

当前无新预算、凭据或范围决定需要用户处理。

## 六条主线的当前证据

| 主线 | 实际工作 | 证据与边界 |
|---|---|---|
| M1 | 锁定V0源码链，可关闭观察器，真实Nsight | engine-diagnostics.md；s2-nsight-engine.json：70,804 kernels，小负载GEMM占主导，未证明KV瓶颈 |
| M2 | 冷热evictor与真实waiting admission老化；修复WAITING缓存计数陈旧 | s2-policies-*.json，288/288输出一致，两次各792不变量快照；Graph/4 B1下没有稳定整体吞吐收益 |
| M3 | 实际K滑窗控制、原生拒绝/结束路径；真实教师与128步LoRA、全状态中断续训、模型真实加载 | s2-spec-v3-validation.json、s2-training-recovery.json、s2-distillation.json；新fixed接受率83.90%→86.92%，初测仍未超过Target吞吐 |
| M4 | 自主AWQ两种校准源group128已导出/加载，group64运行；固定预算和代表层误差已有真实记录 | s2-awq初步结果待聚合；未完成多group性能/显存主比较与全部产物留存 |
| M5 | 自定义独立RoPE+KV append CUDA | s2-rope-cache.json：48数值、16 memcheck、6形状计时；FP16/Q28/KV4/D128，未接入服务 |
| M6 | 实际FA2八形状、Nsight、单/双副本/TP2冒烟 | 冒烟并发不匹配，不计算部署加速；公平矩阵代码已实现，尚待实际运行 |

## 数据、训练与正确性边界

- data/frozen-v1：train512、calibration256、dev128、final-test256；组与exact scene content隔离，与旧fixture无重复；共同任务模板不证明跨模板/真实道路泛化。final-test留待S5，从未进入训练/校准/调参。
- 教师只生成train/dev640条。train472合格、40规则错误保留排除；dev121/128正确。训练128 optimizer步、microbatch2×accum4、LoRA rank8，消费1024条循环样本；仅答案含EOS的交叉熵，不做logit蒸馏。
- 真实SIGTERM在第8步checkpoint出现后发送，第9步保存退出；恢复到16步与连续参考的adapter/optimizer/scheduler/RNG/每步loss-LR-样本顺序bitwise相同。最终模型/完整checkpoint均OSS读回。
- 相同137开发+边界请求：原Draft fixed和trained fixed均与Target137/137序列相同，trained adaptive136/137；业务均121/128正确。long-2的第124token差异保留，旧诊断有同前缀FP16近似/并列证据，新run未另采logprob，非逐token严格等同保证。
- 随机采样发现原版MQA按seq_ids而非sample_indices初始化：20行只写4行。v3修正行覆盖及过滤后的seed映射，CUDA已知分布与真实模型回归通过。动态K固定分母指标失败也单独修复/留痕，不伪造Prometheus值。
- 原始Draft词表151936与Target152064不兼容；零填充128行仅解决维度，改变softmax且不算训练。trained模型另有真实训练证据，不覆盖原Draft。

## 环境、资产与资源

两张RTX4090各49140MiB，驱动550.163.01，无NVLink；TP2 P2P失败、custom all-reduce关闭。torch2.6.0+cu124/vLLM0.8.5/transformers4.51.3；153项基础环境未覆盖。上游ba41cc90e8ef7f236347b2f1599eec2cbb9e1f0d，补丁overlay独立于wheel。训练与AWQ工具以锁定附加层加载，不改变推理环境。

- GPU环境/hy-tmp/driveserve/venv-rebuilt；训练层training-deps-v1；AWQ层awq-deps-v2。v1因six缺失失败保留，v2的pip check/import已通过。
- runtime模型在/hy-tmp/driveserve/models；trained Draft使用draft-distilled-v2，权重与v1相同，tokenizer复制原文件以保持字节级兼容。
- 已确认OSS98对象34,920,080,955bytes，估算0.33523元/天，暂不含尚在上传的AWQ两模型。收据s1-oss-models-receipt.json、s1-environment-receipt.json、s2-teacher-oss-receipt.json、s2-training-recovery-oss.json、s2-trained-assets-oss.json。
- 原始模型39包与环境4.13GB快照已完整读回；153依赖全新环境重建及GitHub独立checkout已验证。没做真实宿主迁移、真实24GB卡验证。
- /hy-netdisk实际为overlay，不能宣称任意迁移持久；GitHub与OSS承担留存。5个重复下载权重18,318,739,032bytes已在验证运行副本+完整OSS收据后回收（022735-6e1ccae122），原模型和云端未删。
- GPU按量开机无固定截止日；用户取消OSS30GB上限，项目常规留存自主执行。新增其他付费资源/范围变化才需决定。

S1 tag为stage-1-foundation；S1验收报告、旧失败和阶段演进均保留在Git。用户学习状态是材料已生成，未验证复述/追问掌握。
