# DriveServe 进度记录

更新：2026-10-15T02:13:00+08:00（Asia/Shanghai）。**S1 已验收，当前 S2 in_progress**。S1 是内部准备版；还没有六线完整发布版、最终P99/SLO或端到端加速结论。验收清单与存储hash见 [s1-acceptance.json](../reports/s1-acceptance.json)。

## 阶段状态

| 阶段 | 状态 | tag |
|---|---|---|
| S1 基础环境 | accepted | stage-1-foundation |
| S2 六线最小闭环 | in_progress | 无 |
| S3 工程与实验完善 | not_started | 无 |
| S4 至少两个深化专题 | not_started | 无 |
| S5 组合及完整场景验收 | not_started | 无 |
| S6 发布与材料固化 | not_started | 无 |

覆盖矩阵目前 **19/27 项达到声明范围的最低验证**：M1四项、M2四项、M5五项、M6-01/02/03。其余8项仍待补齐；单项通过不能代替S2验收。详见 [coverage.md](coverage.md)、[S1累计讲解](stages/S1/README.md)、[S2实施中讲解](stages/S2/README.md)。

## 可追溯结果

| 工作 | 主要证据 | 结论与限制 |
|---|---|---|
| CPU基础与恢复 | 20261015T001330+0800-01723773af；20261014T214445+0800-77a7a9a4f4 | 当前21项CPU检查通过（新增20261015T011138+0800-8533f297ad）；真实SIGTERM后从3条恢复至128条，拒绝重复任务；不是训练恢复 |
| GPU环境全新重建 | 20261014T221232+0800-1dbfa02c19 | 153项锁定依赖，pip check与双卡算术通过 |
| GitHub新checkout重建 | 20261015T000808+0800-57ee7ceb1e；20261015T001205+0800-2367879bb2 | 取回d2f0cf8及7项profile资产hash；代理失败保留，直连CPU重建后18项检查通过 |
| 单卡/TP2/Graph | reports/s1-tp2-smoke.json；s1-graph-clean-smoke.json | 每组32条成功、31条规则全字段正确；Graph固定clean SHA95e48c3，非torch.compile |
| 固定K=3 | reports/s1-fixed-k-smoke.json；s1-fixed-k-memory.json | 32条贪心文本与普通模型一致；fraction0.40的15次显存采样22762–22826MiB；非真实24GB卡验证 |
| 上游AWQ格式 | reports/s1-awq-format-smoke.json | W4A16/group128/native AWQ：32成功、30正确；未自主校准，未测Marlin |
| 模型OSS留存 | 20261014T231207+0800-1392c8d2a8；reports/s1-oss-models-receipt.json | 39/39包、27,023,759,360字节上传并逐包完整读回，含4组模型；新目录配置恢复也成功 |
| 环境本体OSS留存 | 20261015T001204+0800-124e348b03；reports/s1-environment-receipt.json | 4,130,582,075字节压缩快照；36,662个文件/链接条目本地与云端回读验证；跨宿主仍需检查并按锁重建 |
| 自定义CUDA融合 | reports/s2-rope-cache.json；docs/rope-cache.md | 48组正确性、4类非法索引、16组memcheck零错误、6形状初次微基准；独立FP16 Q28/KV4 D128原型 |
| 可关闭引擎观察器 | reports/s2-engine-diagnostic.json | 24条开关对照输出token一致，主机step累计4.21707/4.15727秒；一对观测差1.44%，无严格因果开销估计 |
| Nsight实测 | reports/s2-nsight-engine.json | 70,804个kernel关联7个Prefill/186个Decode区间；小负载GEMM占主导，无KV饱和证据 |
| FA2 Prefill对照 | reports/s2-fa2-prefill.json | 8形状、双方显式FP32参考通过；与torch原生flash耗时接近，属于上游能力比较 |
| 双副本真实链路 | reports/s2-dual-replica-smoke.json | 两张物理卡各16条成功，总32成功、31正确；全局并发4，不能与早期并发2的TP2算加速 |

客户端requests+measurement重聚合与summary一致。服务验证后受控SIGTERM，interrupted表示停止，不替代客户端成功判定；所有错误响应、失败重试与旧dirty探索保留。

## S2 本轮真实进展

- 代码 f46b334 接入冷热evictor和带老化的真实admission，890bb0b修复压力场景发现的上游WAITING前缀计数陈旧问题；原wheel最小复现与修复回归均保留。
- 开/关观察器共8组×36条全部成功，逐请求输入hash及输出token一致；两组生命周期各14完成+2主动取消，各792次不变量检查，全池128块最后均可释放/复用。
- 无插桩初测native/cache/scheduler/both分别106.43/107.28/105.06/106.33输出token/s。冷热冲刷后复用992tokens vs 0；长度规则改善短请求首token但长请求平均首token变慢，未观察到整体吞吐明显改善，不能宣称全面加速。
- 报告 reports/s2-policies-diagnostic.json、s2-policies-timing.json；累计解释 docs/cache-scheduler.md。四组均含共同正确性修复，调优B1与主四组现已完成（5bcc38d），报告另见s2-b1-selection.json/s2-policies-b1.json；M2四项最低范围通过。
- HTTP源码路线已补MQ实际默认分支，M1最低调用链、可关闭观察器及实际长短/前缀/Decode分析已有证据；B0/B1初步诊断已闭环；缺陷修复边界见ADR0003。

## 环境、持久资产和资源

- 两张RTX4090，各报告49140MiB；驱动550.163.01，系统nvcc12.1；独立torch2.6.0+cu124 / vLLM0.8.5 / Transformers4.51.3。原系统torch未改。上游SHA为ba41cc90e8ef7f236347b2f1599eec2cbb9e1f0d。
- GPU环境 `/hy-tmp/driveserve/venv-rebuilt`；原wheel不修改。观察器使用 `/hy-tmp/driveserve/vllm-observers-v1` 隔离overlay，补丁与原/目标hash进Git，迁移后重建。
- 拓扑NODE、无NVLink；TP2实测P2P失败，自定义all-reduce关闭。24GB配置适配与真实迁移保留限制。
- `/hy-netdisk`在本容器仍解析为overlay，不认定为任意迁移持久盘；当前留存由GitHub与OSS实现。模型前缀 `oss://DriveServe/s1-models-7b5208b2777b`；环境对象见收据。
- 项目OSS资产共31,154,341,435字节（约31.15GB），按截图单价估算约0.2991元/天；不含用户已有镜像。用户已取消原30GB限制，常规留存自主执行，新增其他付费资源仍需决定。
- GPU按量，用户保持开机，无固定截止日。资源计划、风险、实验顺序见 [resource-plan.md](resource-plan.md)。

## 接续工作

更新2026-10-15T01:32:00.931813+08:00：当前GPU批次全部结束，没有遗留服务。最新正式实验代码5bcc38d：原版B0、Graph/2/4/8候选与Graph/4三项策略复测均完成，全部36条输出一致。选择Graph/4为本合成引擎场景B1；无稳定整体吞吐收益，默认保留原生LRU/FCFS。原始run已封存；前一证据提交已从GitHub另一checkout读回核验28个run、98个资产，收据reports/s2-policies-github-readback.json。

下一步无需用户新增预算或范围决定：
1. M3在最大K预留下实现运行时K及连续接受前缀轨迹；在冻结数据用途后真实教师生成、LoRA序列蒸馏、优化器/调度器/RNG完整中断续训和训练后真实推测比较。
2. M4准备独立校准/训练工具依赖（不覆盖现有GPU锁环境），获取有许可的通用语料，完成自主AWQ、通用/领域/代表层敏感性及group64/128导出。
3. M6匹配单卡/双副本/TP2多长度并发对照，冻结正式四类数据/独立测试。27项全部通过后再做S2验收与tag。S3独立重复不能用当前单次诊断替代。

## 失败与边界

- 原Draft词表151936，Target152064；原始固定K启动失败。派生Draft只增加128行零embedding，338个原张量已有值不变；会改变softmax归一化，不能称训练或原分布不变。见ADR0002。
- 上游AWQ比普通模型多错dev-0003-01；共同错误dev-0002-02不删除，不用教师输出覆盖规则真值。
- 初始CUDA编译因Ninja不在PATH失败，修正环境bin路径后成功；原失败run保留。
- 旧Run只封存根层文件，嵌套trace已有Git留存；reports/s2-profile-assets.json补hash，新Run递归封存并有篡改回归测试，未改写旧manifest。
- Nsight父目录缺失后工具写临时报告；按工具日志取回，复制SHA一致并成功解析，告警与收据保留。
- SSH代理CONNECT后断开、HTTPS HTTP2和PyPI代理TLS失败均保留；Git已用原deploy key、严格主机校验直连ssh.github.com:443推送成功，CPU重建改用直连PyPI；不修改Codex连接/认证。

## 最短恢复入口

读AGENTS、规范、本文件和阶段报告；`git status --short --branch`、`git log -5 --oneline`，用 `python3 -m driveserve status` 核对PID/boot_id/start_ticks。参考 [reproduce.md](reproduce.md) 从Git与完成收据恢复。记录器30秒心跳，OSS每包/环境快照完成时原子落盘；训练以后另验。没有部署自动开机、agent自动唤醒或后台定时同步。用户学习状态仍是材料已生成、尚未验证掌握。


### M3 当前实施单元

已编写独立spec overlay与实际K控制、连续接受口径及事前冻结验证入口；尚无本轮GPU证据，不提升M3状态为validated。准备固定代码后顺序执行target/fixed/adaptive与原生CUDA拒绝采样分布检查。当前无GPU任务。

M3首轮证据：Target/固定K41条全部输出一致；120000次原生CUDA拒绝采样频率检查通过。adaptive实际发生2→3→4→3，但上游固定K指标的整除假设触发失败，保留run并用动态实际分母修复；待复测，不宣称M3完成。

M3实机出现必须解决的正确性缺口：f821577动态K已运行且41条完成，但长输出仅39/41贪心一致；随机8业务Target8正确、fixed0、adaptive2，多条无效JSON。已保留完整原始报告s2-spec-initial.json。下一步用原wheel/逐请求seed/MQA与batch-expansion对照及top5 logprob定位；在解决前不验收M3或发布动态K默认配置。蒸馏数据、附加依赖和教师生成入口已准备，协议见distillation-protocol.md，训练仍未发生。


### 2026-10-15 02:05 接续点

原wheel随机采样也0/8正确（015807-c0d453c875），unseeded与batch-expansion分别8/8；锁定源码的PyTorch sampler按seq_ids而非sample_indices初始化随机行，已实现修复和NaN哨兵回归入口，待固定代码后的CUDA与模型复测。v3 overlay同时修正spec_indices过滤后的seed映射。

两处长输出贪心分歧已有相同前缀top5证据（reports/s2-spec-top5.json）：long-0单步两token并列，K3相差0.015625；long-2单步差0.03125，adaptive两token并列。fixedK3也重现long-0；仍保留39/41与40/41原始口径，不承诺不同计算形状FP16逐token恒等。随机明显质量损坏另按缺陷修复，不混为数值误差。

数据已冻结train512/calibration256/dev128/test256，组与内容隔离；test只在S5使用。训练附加依赖accelerate1.6.0/peft0.15.2已安装且原153项环境未变，pip check通过。LoRA训练/完整checkpoint/状态对照/导出入口已实现，尚未运行训练。当前GPU空闲；下一步先v3采样回归，生成640条教师train/dev，再实测SIGTERM续训。无需新增授权。

2026-10-15 02:08：fb76fab下CUDA采样复现已验证原版20行仅4行写入，v3覆盖全部行；10000次已知分布最大频率误差0.0008，seed复现相同。v3固定/动态温度0.7全41条均完成、32业务均31正确；对比旧错误已消失，target同配置主对照与v3贪心回归仍待做。教师640条已全部生成；train512中472符合规则与自然结束，40规则错误保留排除，dev121/128正确。CPU24项通过。下一单元：实际中断续训对照及教师资产OSS留存，训练尚未发生。

2026-10-15 02:13：M3-01/02/03最低支持范围验证完成，总覆盖19/27。v3固定K41/41、动态39/41贪心一致，两处FP16近似/并列的同前缀top5均保留；2286个spec诊断token均是各自Target最大logprob。随机target/fixed/adaptive各32业务31正确。全部诊断时GPU1存在教师/训练，时间不用于性能主张。

实际训练恢复run020833-07a7e69dc5已通过：SIGTERM后第9步保存、续到16步，adapter/optimizer/scheduler/CPU-CUDA RNG和每步loss/LR/样本顺序全部bitwise相同。128步正式训练run021108-6af044d14a在GPU1运行，父记录021101-ce1acb975d；根目录/hy-tmp/driveserve/training/recovery-v1/resumed，latest.json每8步及中断后原子保存。接管先核PID/manifest，勿重复训练。

教师与训练wheel等6个OSS对象3,471,360bytes已读回，reports/s2-teacher-oss-receipt.json；恢复关键checkpoint的OSS上传仍在run021131-9671fe54bb。接下来导出Draft、固定K训练前后/训练后动态开发集对照及完整留存。AWQ工具层与等token校准入口已准备，尚未安装/执行；通用WikiText固定revision/许可已从镜像元数据核对，直连/代理TLS失败保留为网络限制。

2026-10-15 02:16：128步训练run021108-6af044d14a已完成，cursor1024（472条训练循环），汇总s2-training-128.json。恢复关键checkpoint17个OSS对象444,743,680bytes读回通过（s2-training-recovery-oss.json）。当前无GPU任务；下一步独立合并导出与frozen-dev训练贡献对照。AWQ附加层v1因six缺失pip check失败，run021357-2ec6ce3a6f保留；v2锁定six1.17.0补齐，待安装。AWQ校准与代表层敏感性入口及事前选择规则见awq-protocol.md，尚无量化产物。

2026-10-15 02:20：Draft权重导出run021712-fde3f70ccc完成约3.10GB。预检发现transformers.save_pretrained重新序列化tokenizer使文件hash不同；从原对齐Draft复制4个已验证tokenizer文件，另建v2目录并硬链接相同权重，保留v1证据，未重训。目标frozen-dev128实际121正确（021726-84cb11e9f5），训练前固定K对照结果待聚合。AWQ v2附加依赖pip check/import通过、原环境未变；通用/领域各32×512token已生成并校验，来源manifest见data/manifests/awq-calibration-v1.json；尚未运行量化。量化输出改1GB分片方便当前磁盘逐片OSS读回，评测入口增加显式quantization与实际KV/多口径显存记录。
