# S4 两项深化验收

状态：**accepted**。两项实质实现、11项边界、24进程三轮消融和独立维护诊断已完成。独立GitHub checkout `730c5d5` 实际通过28 CPU测试、4份产物逐字节复算和483份run审计；验收记录见[报告](../../../reports/s4-acceptance.json)，读回见[原始记录](../../../reports/s4-github-readback/readback.json)。S4验收提交创建 `stage-4-depth`，不改变已核验执行代码。

| S4条件 | 已有证据 | 限制/决定 |
|---|---|---|
| 至少两个实质专题 | heap_policy.py真实三堆索引、代际与有界重建；rope_cache_tiled.cu实际scalar/half2 CUDA | 不只是重命名上游开关；原算法/原v1保留 |
| 引擎或CUDA真实修改与运行 | 两者均在8728669固定实现；11边界报告s4-boundaries.json，三轮s4-depth.json | 受支持范围单卡V0非chunked、FP16固定CUDA布局 |
| 正确性/消融/成本/结论 | 20k差分、5000更新排空、12TTL边界、两allocator各4、两Graph生命周期16输出/status一致；275全CUDA/99memcheck/三入口各24拒绝；6引擎、8CPU规模/方案、6CUDA shape×5方案各3进程 | 大池CPU更快且额外内存；小池服务差异小；scalar大T退化；不推导整体GPU利用率 |
| 负结果及合理回退 | cache heap三轮差异方向不稳定；默认scan。CUDA v1保留，auto cutoff32固定；正式表包括单操作最大停顿 | 没有把所有操作叫O(log N)，没有只展示最快shape |
| 原因与限制可深入解释 | s4-heap-maintenance.json：16384池首次8192 stale pops、TTL批量4352重分类；128池10重建与GC事件分别记录 | 新诊断不能重建旧run未记录的GC；trace时间不并入正式计时 |
| 保持六线并累计讲解 | 本目录README/replay/resume/coverage，27项基础证据保留且受影响项追加S4 | M3训练、M4AWQ、M6FA2/部署未改核心，不重复训练冒充进度；S3 TP2不确定性保留 |

实现8728669；三轮源码05bcac1/d37aa46/b8e91be，源码/配置/输入/环境指纹经聚合器核验一致。S3 stage-3-validated仍可独立获取，S4所有本阶段门槛已通过，验收tag随本次提交创建。

没有新模型权重或依赖，沿用144个OSS对象51,794,986,555bytes完整读回收据与S3九个当前小成员恢复；新增源码及所有原始CPU/GPU记录由Git留存。CUDA构建产物位于临时盘、可按保存源码/环境重建；不称已验证宿主迁移或物理24GB。

最终test未送模型。后续S5负责业务组合、开环goodput、最终测试和部署；独立CUDA不计服务收益。学习状态仍为材料已交付、用户尚未复述/追问验证。
