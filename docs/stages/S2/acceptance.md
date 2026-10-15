# S2 最小六线版本验收

当前状态：**accepted**。27/27最低要求已按声明范围验证，247份终态run的原始文件哈希、正式代码记录及Git包含通过；144个OSS对象共51,794,986,555bytes完整回读。GitHub独立checkout通过24项CPU回归，AWQ、部署、B1策略和蒸馏四份完整报告从原始记录重算精确一致。验收报告为 [s2-acceptance.json](../../../reports/s2-acceptance.json)，阶段tag为 `stage-2-minimum`。

| 验收条件 | 实际证据 | 限制 |
|---|---|---|
| 27项覆盖 | docs/coverage.md及每项run | 各自限定profile，不是全部同时开启 |
| 每线回放与匹配对照 | 本目录replay.md；B1、AWQ及三部署报告 | 初测，不宣称统计显著性 |
| 正确性/任务/失败处理 | allocator、CUDA memcheck、分布采样、137业务边界、768HTTP请求 | FP16并列和TP2长填充差异保留，默认关闭未稳妥优化 |
| 贡献分离 | native/cache/scheduler/both；原/新Draft fixed与新adaptive；三组AWQ | AutoAWQ/FA2等上游贡献明确 |
| 探索性尾延迟 | 部署每cell64请求，失败/超时同时报告 | P99不作为生产SLO |
| 累计讲解及六条简历 | README.md、resume.md、replay.md | 用户尚未复述/追问验证 |
| 训练恢复和长任务 | SIGTERM第9步保存、续至16与连续参考全状态等同；AWQ逐层落盘 | AWQ整组重跑，未部署自动开机/agent唤醒 |
| 持久留存与恢复入口 | 144个OSS对象约51.795GB均完整读回；三组模型与训练元数据恢复探测 | 小探测不替代全量恢复；无真实宿主迁移 |

S2复用S1固定环境、源码和模型恢复证据。S3仍须独立重复、边界/质量阈值与计时可靠性，S4至少两项深化，S5组合与独立final-test，S6干净checkout及最终材料；当前不将这些后续工作标完成。

首次独立读回发现历史蒸馏分组指标未进入通用聚合入口，cf88450补齐分组计算和受run集合约束的实验说明；旧报告数值未改，第二次远端读回精确一致。见 [读回报告](../../../reports/s2-github-release-readback.json) 与 [证据审计](../../../reports/s2-evidence-audit.json)。
