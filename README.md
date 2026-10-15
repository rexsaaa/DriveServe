# DriveServe

面向结构化车载决策代理任务的vLLM推理优化与压缩实验项目，覆盖源码诊断、缓存调度、推测蒸馏、AWQ、独立CUDA融合和双卡部署六条主线。

**S1–S5已验收，S6最终发布核查中。** 最新已验收版本为`stage-5-release-candidate`（`df805a5`）。项目不包含真实车辆闭环或安全验证；独立CUDA没有接入推理服务。

- [快速开始](docs/quickstart.md)：恢复小型HTTP依赖并创建完整CPU测试环境，不需要GPU或模型。
- [最终报告](docs/final-report.md)、[结果与阶段版本](docs/results-index.md)：真实指标、负结果与原始证据。
- [六线累计讲解](docs/stages/S6/README.md)、[事实版简历](docs/stages/S6/resume.md)、[学习核验](docs/learning-guide.md)。
- [复现说明](docs/reproduce.md)、[资产与环境](docs/assets.md)、[27项覆盖矩阵](docs/coverage.md)。
- [当前进度](docs/progress.md)、[S6验收](docs/stages/S6/acceptance.md)、[实施规范](docs/DriveServe-实施与验收规范.md)。

S5完成三轮39个计时进程、9216/9216 HTTP请求，以及十个冻结profile各256条最终质量评估：均为236条规则正确。FP16推测缩短本次波次总时间但增加首字延迟；AWQ×推测三轮更慢，默认关闭。高rate自然负载仍有大量请求不满足预设SLO，P99只作探索性结果。完整条件见[组合与部署讨论](docs/s5-discussion.md)。

固定环境为vLLM0.8.5、torch2.6.0+cu124、Transformers4.51.3；实际硬件为两张各约48GB的RTX4090，无NVLink、P2P失败。模型和环境留存在授权OSS中，182对象约53.126GB；Git记录源码、补丁、锁、数据及原始实验证据，凭据不入库。恢复需要项目OSS账户权限。

仓库：<https://github.com/rexsaaa/DriveServe>。Git提交使用中文与阶段前缀，阶段tag只在验收后创建。原导入规范包保留在`DriveServe-实施规范包/`，当前执行记录以根目录docs为准。
