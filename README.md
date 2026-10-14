# DriveServe

面向结构化车载决策**代理任务**的 vLLM 推理优化实验项目。它不是真实车辆的感知—规划—控制系统。

当前处于 **S1 基础建设，尚未验收**。没有已发布阶段、六线完整实现或性能收益结论。原始规范中的百分比是目标占位值。

- 执行规范：[docs/DriveServe-实施与验收规范.md](docs/DriveServe-实施与验收规范.md)
- 当前进度：[docs/progress.md](docs/progress.md)
- 逐项覆盖：[docs/coverage.md](docs/coverage.md)
- 原始导入包保留在 `DriveServe-实施规范包/`；后续执行记录以根目录 `docs/` 为准。

远程仓库：<https://github.com/rexsaaa/DriveServe>。已验证 SSH 写入并推送 main，后续提交采用 `S1 类型：中文说明` 格式。

当前可运行的 CPU 入口及边界见 [复现说明](docs/reproduce.md)。使用 `python3 -m driveserve status` 检查任务真实进程；阶段材料见 [S1 累计讲解](docs/stages/S1/README.md)。活动日志先落盘，结束并验证 hash 后再提交。

项目按 S1 基础环境 → S2 六线最小闭环 → S3 工程与实验完善 → S4 至少两个深化点 → S5 组合验收 → S6 发布推进。仅在完整证据通过对应阶段门槛后创建阶段 tag。
