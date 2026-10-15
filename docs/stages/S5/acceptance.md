# S5组合与完整场景验收

状态：**accepted**。验收报告为[reports/s5-acceptance.json](../../../reports/s5-acceptance.json)，阶段tag为`stage-5-release-candidate`。独立GitHub候选`2083875`实际通过39项CPU测试、六份产物逐字节复算、650份run及182对象收据审计；最终验收提交仅追加记录与材料状态。

| 门槛 | 实际结果与证据 |
|---|---|
| 组合/消融 | 三轮39进程：六模型及四策略各3次，9HTTP进程9216/9216完成，APC原生基线；[主表](../../s5-results.md) |
| 冻结最终质量 | 十profile各256完成/JSON有效、236正确；四spec与同Target256条token/结束一致；调度两条JSON格式差异保留；[质量](../../../reports/s5-final-quality.json) |
| 最后回归 | 39CPU、两组allocator、275CUDA检查、三入口各24拒绝、99memcheck、两组Graph生命周期；16输出/status一致；[回归](../../../reports/s5-final-gpu.json) |
| 资产 | 历史及新增36wheel完整读回共182对象53,125,961,275bytes；当前182列表/10小成员恢复通过；[当前核验](../../../reports/s5-assets.json) |
| 独立复算 | GitHub干净checkout `2083875`，39CPU、六产物精确相同、650run、36锁引用匹配备份；[读回](../../../reports/s5-github-readback/readback.json) |
| 累计交付 | [六线讲解](README.md)、[回放](replay.md)、[27项覆盖](coverage.md)、[六条事实简历](resume.md)、[最终配置](../../s5-compatibility.md) |

默认FP16 Target/native APC；AWQ×spec三轮负收益，默认关闭。动态K没有稳定额外优势，heap的小池服务收益不明确；独立CUDA没有服务接入。自然HTTP高rate仍有大量请求未满足SLO，P99仅每cell256×3探索性统计。

无生产稳定尾部、实车安全、物理24GB或宿主迁移声明。最终test未参与调参，用户掌握仍待核验。S5完成后继续S6最终发布；本tag是已验收候选版。
