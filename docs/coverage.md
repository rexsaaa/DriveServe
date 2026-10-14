# DriveServe 最低要求覆盖矩阵

依据主规范第 4 节；当前 S1 in_progress，27 项均未达到 validated。源码预检和 CPU 基础工具不等于主线验收。

状态：planned → in_progress → implemented → validated；实际阻塞保留原要求并记录原因。S2 必须逐项满足以下 27 项。

| 要求 ID | 最低验收阶段 | 要求摘要 | 状态 | 代码/报告位置 | 实验 run ID | artifact 引用 | 累计讲解 | 限制 |
|---|---|---|---|---|---|---|---|---|
| M1-01 | S2 | 锁定源码与相关调用链 | in_progress | docs/compatibility.md（仅源码预检） | 无 | 无 | docs/stages/S1/README.md | 完整调用链与运行插桩待完成 |
| M1-02 | S2 | 可开关真实运行时插桩 | planned | 无 | 无 | 无 | docs/stages/S1/README.md | 尚未实现或实机验证 |
| M1-03 | S2 | 前缀、排队和 Decode 实际分析 | planned | 无 | 无 | 无 | docs/stages/S1/README.md | 尚未实现或实机验证 |
| M1-04 | S2 | baseline 与初步诊断 | planned | 无 | 无 | 无 | docs/stages/S1/README.md | 尚未实现或实机验证 |
| M2-01 | S2 | 冷热缓存策略接入真实引擎 | planned | 无 | 无 | 无 | docs/stages/S1/README.md | 尚未实现或实机验证 |
| M2-02 | S2 | KV 生命周期与不变量 | planned | 无 | 无 | 无 | docs/stages/S1/README.md | 尚未实现或实机验证 |
| M2-03 | S2 | 真实长度感知与基本公平性 | planned | 无 | 无 | 无 | docs/stages/S1/README.md | 尚未实现或实机验证 |
| M2-04 | S2 | cache/scheduler 四组对照 | planned | 无 | 无 | 无 | docs/stages/S1/README.md | 尚未实现或实机验证 |
| M3-01 | S2 | 模型兼容与固定 K 基线 | in_progress | reports/model-preflight.json（未运行权重） | 无 | 无 | docs/stages/S1/README.md | 配置词表维度不同，固定 K 尚未运行 |
| M3-02 | S2 | 滑动窗口驱动运行时 K | planned | 无 | 无 | 无 | docs/stages/S1/README.md | 尚未实现或实机验证 |
| M3-03 | S2 | 验证/回滚/结束与控制轨迹 | planned | 无 | 无 | 无 | docs/stages/S1/README.md | 尚未实现或实机验证 |
| M3-04 | S2 | 实际 Draft 蒸馏训练与产物 | planned | 无 | 无 | 无 | docs/stages/S1/README.md | 尚未实现或实机验证 |
| M3-05 | S2 | 训练后真实评测与贡献分离 | planned | 无 | 无 | 无 | docs/stages/S1/README.md | 尚未实现或实机验证 |
| M4-01 | S2 | AWQ 校准导出与真实部署 | planned | 无 | 无 | 无 | docs/stages/S1/README.md | 尚未实现或实机验证 |
| M4-02 | S2 | 通用/领域校准比较 | planned | 无 | 无 | 无 | docs/stages/S1/README.md | 尚未实现或实机验证 |
| M4-03 | S2 | 代表层/层组敏感性实验 | planned | 无 | 无 | 无 | docs/stages/S1/README.md | 尚未实现或实机验证 |
| M4-04 | S2 | 多 Group Size 与性能/质量 | planned | 无 | 无 | 无 | docs/stages/S1/README.md | 尚未实现或实机验证 |
| M4-05 | S2 | 显存口径与混合精度范围 | planned | 无 | 无 | 无 | docs/stages/S1/README.md | 尚未实现或实机验证 |
| M5-01 | S2 | 数据布局与上游能力核查 | planned | 无 | 无 | 无 | docs/stages/S1/README.md | 尚未实现或实机验证 |
| M5-02 | S2 | 自定义真实融合 CUDA 实现 | planned | 无 | 无 | 无 | docs/stages/S1/README.md | 尚未实现或实机验证 |
| M5-03 | S2 | 数值、边界与内存检查 | planned | 无 | 无 | 无 | docs/stages/S1/README.md | 尚未实现或实机验证 |
| M5-04 | S2 | 等价 CUDA Event 微基准 | planned | 无 | 无 | 无 | docs/stages/S1/README.md | 尚未实现或实机验证 |
| M5-05 | S2 | 源码/计时与适用上游对照 | planned | 无 | 无 | 无 | docs/stages/S1/README.md | 尚未实现或实机验证 |
| M6-01 | S2 | 实际 FA2 Prefill 评测 | planned | 无 | 无 | 无 | docs/stages/S1/README.md | 尚未实现或实机验证 |
| M6-02 | S2 | 真实 Nsight Systems 时间线 | planned | 无 | 无 | 无 | docs/stages/S1/README.md | 尚未实现或实机验证 |
| M6-03 | S2 | 单卡/双副本/TP2 实机运行 | planned | 无 | 无 | 无 | docs/stages/S1/README.md | 尚未实现或实机验证 |
| M6-04 | S2 | 多长度/并发部署建议 | planned | 无 | 无 | 无 | docs/stages/S1/README.md | 尚未实现或实机验证 |

S1 基础验证另见阶段报告；此矩阵没有将 mock、metadata 或上游代码标为个人实现完成。后续阶段报告保留对应覆盖快照。
