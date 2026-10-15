# DriveServe

面向结构化车载决策**代理任务**的 vLLM 推理优化实验项目。它不是真实车辆的感知—规划—控制系统。

**S1、S2已验收。** `stage-2-minimum`是首个六线最小完整版本，27/27最低要求有证据；S3已完成三轮54进程和16项边界验证，独立远端/资产复核中，尚未验收。 已实现真实缓存/调度与运行时K，完成128步Draft序列蒸馏、三组自主AWQ、独立CUDA融合及FA2/Nsight/三部署对照。Graph固定K在本次负载中缩短总时间但TTFT增加；没有生产SLO声明；局部负结果和质量差异保留。原始规范中的百分比是目标占位值。

- 执行规范：[docs/DriveServe-实施与验收规范.md](docs/DriveServe-实施与验收规范.md)
- 当前进度：[docs/progress.md](docs/progress.md)
- 逐项覆盖：[docs/coverage.md](docs/coverage.md)
- 原始导入包保留在 `DriveServe-实施规范包/`；后续执行记录以根目录 `docs/` 为准。

远程仓库：<https://github.com/rexsaaa/DriveServe>。已验证 SSH 写入并推送 main，提交采用 `所属阶段 类型：中文说明` 格式。

当前可运行的 CPU / GPU 服务入口及边界见 [复现说明](docs/reproduce.md)。使用 `python3 -m driveserve status` 检查任务真实进程；已验收材料见 [S2 累计讲解](docs/stages/S2/README.md)；当前验证材料见 [S3 累计讲解](docs/stages/S3/README.md)、[六线回放](docs/stages/S3/replay.md)和[独立重复](docs/s3-stability.md)。活动日志先落盘，结束并验证 hash 后再提交。

项目按 S1 基础环境 → S2 六线最小闭环 → S3 工程与实验完善 → S4 至少两个深化点 → S5 组合验收 → S6 发布推进。仅在完整证据通过对应阶段门槛后创建阶段 tag。
