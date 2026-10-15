# S3 工程与实验完善验收

当前状态：**accepted**。三轮54独立进程和16项边界诊断完成；414份终态run原始hash/Git包含、9个OSS小成员重新下载、GitHub独立checkout的28项CPU检查与5个文件逐字节复算全部通过。正式记录见 [s3-acceptance.json](../../../reports/s3-acceptance.json)，可获取版本为 `stage-3-validated`。

| S3条件 | 实际证据 | 限制 |
|---|---|---|
| 声明支持范围关键边界 | reports/s3-boundaries.json：28 CPU、4 allocator、两次Graph生命周期各792快照/32共享块/2取消/1抢占、24拒绝/48正常CUDA/16 memcheck；随机Graph与数据隔离 | 不支持范围仍明确；索引别名修复前截获dispatch，未运行危险kernel |
| 核心独立重复 | reports/s3-stability.json：3轮54进程/39指标组，每run原值/样本标准差/范围；s3-boundaries-fixed.json各Draft3次计数 | 每cell64 P99探索；TP2波动原因未知；固定K诊断与计时分离 |
| 原生B1公平对照 | S2有限eager/Graph、maxseq2/4/8选B1=Graph/4；S3所有策略沿用；FP16 Graph Target作推测/量化参考 | 不是全局最优调参；不关闭Graph制造差距 |
| 原始记录可回溯和复算 | analyze_replication.py、analyze_s3_boundaries.py及state/run/asset hash；远端独立重聚合通过 | GitHub副本bff5a6a精确重聚合四份JSON及一张生成表 |
| 既有基础能力与修复回归 | S2六线/128步训练/全状态恢复保留；S3 CUDA入口修复后受影响数值/内存检查通过；27项覆盖已更新 | CUDA .cu/.cpp未改；没有为文档变化重复训练 |
| 累计讲解、失败与可信度 | 本目录README/replay/resume/coverage；保留通用AWQ门槛失败、长请求退化、动态K负结果、TP2速度和质量差异 | 用户尚未复述/追问验证；S4–S6未验收 |

默认仍为FP16 Target及原生策略。独立实验入口保留cache/scheduler、原/蒸馏Draft fixed与adaptive、三组AWQ/Marlin、CUDA融合及FA2；S5才验证适用组合及最终test，单项百分比不相加。

资产沿用144个OSS对象51,794,986,555bytes完整读回收据，当前9个小成员恢复探针已通过，见reports/s3-restore/summary.json；本地/hy-netdisk仍是overlay，不证明跨主机持久化。未发生宿主迁移，也未验证物理24GB卡。GPU按量开机没有已知截止日，OSS项目留存已授权，不新增其他付费资源。

关键提交：88ed620冻结首轮、e3a133f聚合与第二轮、ab8f4ce第三轮与数据/兼容材料、ba54e8d索引alias修补与三轮封存、bff5a6a边界/累计/资产归档。完整读回见 [readback.json](../../../reports/s3-github-readback/readback.json)，最初在clone未完成前启动验证的失败保留在同目录attempt1.json；其未执行测试，clone完成后正常通过。

S4进入两个专题：精确语义的冷热淘汰堆索引、独立CUDA head tile/half2消融。它们目前仅为准备稿，S3验收不等于S4完成。
