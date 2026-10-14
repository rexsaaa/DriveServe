# DriveServe 进度记录

更新：2026-10-15T01:23:05.616223+08:00（Asia/Shanghai）。**S1 已验收，当前 S2 in_progress**。S1 是内部准备版；还没有六线完整发布版、最终P99/SLO或端到端加速结论。验收清单与存储hash见 [s1-acceptance.json](../reports/s1-acceptance.json)。

## 阶段状态

| 阶段 | 状态 | tag |
|---|---|---|
| S1 基础环境 | accepted | stage-1-foundation |
| S2 六线最小闭环 | in_progress | 无 |
| S3 工程与实验完善 | not_started | 无 |
| S4 至少两个深化专题 | not_started | 无 |
| S5 组合及完整场景验收 | not_started | 无 |
| S6 发布与材料固化 | not_started | 无 |

覆盖矩阵目前 **14/27 项达到声明范围的最低验证**：M1-01/02/03、M2-01/02/03、M5五项、M6-01/02/03。其余13项仍待补齐；单项通过不能代替S2验收。详见 [coverage.md](coverage.md)、[S1累计讲解](stages/S1/README.md)、[S2实施中讲解](stages/S2/README.md)。

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
- 报告 reports/s2-policies-diagnostic.json、s2-policies-timing.json；累计解释 docs/cache-scheduler.md。四组均含共同正确性修复，调优B1尚待完成。M2-04保留in_progress。
- HTTP源码路线已补MQ实际默认分支，M1最低调用链、可关闭观察器及实际长短/前缀/Decode分析已有证据；B0/B1诊断待闭环。

## 环境、持久资产和资源

- 两张RTX4090，各报告49140MiB；驱动550.163.01，系统nvcc12.1；独立torch2.6.0+cu124 / vLLM0.8.5 / Transformers4.51.3。原系统torch未改。上游SHA为ba41cc90e8ef7f236347b2f1599eec2cbb9e1f0d。
- GPU环境 `/hy-tmp/driveserve/venv-rebuilt`；原wheel不修改。观察器使用 `/hy-tmp/driveserve/vllm-observers-v1` 隔离overlay，补丁与原/目标hash进Git，迁移后重建。
- 拓扑NODE、无NVLink；TP2实测P2P失败，自定义all-reduce关闭。24GB配置适配与真实迁移保留限制。
- `/hy-netdisk`在本容器仍解析为overlay，不认定为任意迁移持久盘；当前留存由GitHub与OSS实现。模型前缀 `oss://DriveServe/s1-models-7b5208b2777b`；环境对象见收据。
- 项目OSS资产共31,154,341,435字节（约31.15GB），按截图单价估算约0.2991元/天；不含用户已有镜像。用户已取消原30GB限制，常规留存自主执行，新增其他付费资源仍需决定。
- GPU按量，用户保持开机，无固定截止日。资源计划、风险、实验顺序见 [resource-plan.md](resource-plan.md)。

## 接续工作

当前GPU批次已结束，没有遗留服务。正式实验代码890bb0b，完整原始记录在experiments/runs并纳入本次证据提交。主仓库新增B0/Graph/max_seqs入口和预先冻结协议，接下来在干净SHA执行。

1. 按 docs/baseline-protocol.md 保留未改原wheel B0，有限搜索Graph与max_seqs=2/4/8的原生B1，选定后重做主四组；所有差异与负结果保留。
2. M3运行时K、真实教师生成/LoRA序列蒸馏及完整checkpoint续训；M4自主AWQ、通用/领域数据、代表层敏感性/group64和128。
3. M6匹配单卡/双副本/TP2的多长度并发对照，冻结正式四类数据/独立测试。27项全部通过后才进行S2验收和tag。

## 失败与边界

- 原Draft词表151936，Target152064；原始固定K启动失败。派生Draft只增加128行零embedding，338个原张量已有值不变；会改变softmax归一化，不能称训练或原分布不变。见ADR0002。
- 上游AWQ比普通模型多错dev-0003-01；共同错误dev-0002-02不删除，不用教师输出覆盖规则真值。
- 初始CUDA编译因Ninja不在PATH失败，修正环境bin路径后成功；原失败run保留。
- 旧Run只封存根层文件，嵌套trace已有Git留存；reports/s2-profile-assets.json补hash，新Run递归封存并有篡改回归测试，未改写旧manifest。
- Nsight父目录缺失后工具写临时报告；按工具日志取回，复制SHA一致并成功解析，告警与收据保留。
- SSH代理CONNECT后断开、HTTPS HTTP2和PyPI代理TLS失败均保留；Git已用原deploy key、严格主机校验直连ssh.github.com:443推送成功，CPU重建改用直连PyPI；不修改Codex连接/认证。

## 最短恢复入口

读AGENTS、规范、本文件和阶段报告；`git status --short --branch`、`git log -5 --oneline`，用 `python3 -m driveserve status` 核对PID/boot_id/start_ticks。参考 [reproduce.md](reproduce.md) 从Git与完成收据恢复。记录器30秒心跳，OSS每包/环境快照完成时原子落盘；训练以后另验。没有部署自动开机、agent自动唤醒或后台定时同步。用户学习状态仍是材料已生成、尚未验证掌握。

