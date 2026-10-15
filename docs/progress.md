# DriveServe 当前进度

**S1–S5 accepted；S6实施中，尚未验收。** 已验收tag为stage-1-foundation、stage-2-minimum、stage-3-validated、stage-4-depth和stage-5-release-candidate。常规工作继续自主推进，无预算、凭据或范围问题待用户选择。

## 当前已完成

- S5正式三轮各13任务，共30模型/策略进程及9HTTP部署进程，9216/9216 HTTP请求完成。执行SHA为29cefb3、388b6c4、6867e37；源码/配置/输入/环境指纹一致。原始复算在reports/s5-composition.json、s5-openloop.json，生成主表见[s5-results](s5-results.md)。
- 冻结test256的十profile均在35ae058实际运行一次，全部完成/JSON有效、各236正确；事前FP16最低231、候选最多少2条门槛通过。四spec与各自Target 256 token/结束一致；scheduler/both各2条仅JSON空白差异，解析/字段评分/错误ID集合一致。没有据test调参。见reports/s5-final-quality.json。
- 最后十项回归在35ae058通过：39 CPU、scan/heap各4 allocator、275 CUDA全检查、三入口各24拒绝、99 memcheck、两组Graph生命周期；各792快照/32共享块/2取消，16输出/status相同，实际有抢占。见reports/s5-final-gpu.json。
- 新增36基础wheel完整OSS备份/读回；所有hash与原GPU锁相符。新增38归档1,330,974,720bytes，累计182对象53,125,961,275bytes，约0.510009元/天。收据reports/s5-base-wheels-oss.json；目录内2个未引用旧包已排除，首次盘点保留。

## 结论与边界

FP16 Target/fixed/adaptive总wave秒15.3711±0.0978/13.3646±0.5854/13.1051±0.2269（各137请求、三独立进程）；推测TTFT增加，动态K增量方向跨轮不稳定。AWQ Target9.7624±0.1480，对fixed16.3439±0.5716/adaptive16.5718±1.0062，组合负收益，默认关闭。四policy自然业务没有额外缓存复用，S3/S4压力机制与长组代价仍保留。

高rate自然HTTP用户E2E P99：single5.9832/6.4591/6.4715s，replica4.8709/5.1340/4.8696s，TP2 3.2096/3.7616/3.5032s。三部署均有大量请求不满足自然SLO；自然正确242/256、填充204/256，不混比不同SLO。每cell256×3仍探索性；发送滞后明确保存，S3 TP2波动原因仍未知。完整解释见[讨论](s5-discussion.md)、[兼容与默认配置](s5-compatibility.md)。

128步LoRA及SIGTERM全状态恢复、独立AWQ校准13文件/21误差复现、FA2/Nsight和S4两个深化均沿用真实证据。独立CUDA没有服务接入；不声称生产P99、实车安全、物理24GB或实际宿主迁移。用户掌握尚未核验。

## 环境、接续与下一步

固定GPU Python为/hy-tmp/driveserve/venv-rebuilt/bin/python，torch2.6.0+cu124/vLLM0.8.5/transformers4.51.3；上游ba41cc90e8ef7f236347b2f1599eec2cbb9e1f0d。两RTX4090各49140MiB、driver550.163.01，无NVLink/P2P失败，TP2自定义all-reduce关闭。policy/spec overlay与原模型在/hy-tmp/driveserve；/hy-netdisk实际overlay，GitHub与OSS承担留存。GPU按量、目前保持开机；新增其他付费资源仍需决定。不改Codex认证/隧道/tmux，不依赖Mac。

当前GPU和基础wheel上传均已结束。182对象存在性检查与10小成员恢复通过；本地及独立GitHub候选2083875均通过650份run审计，独立副本实际执行39CPU并逐字节复算六份产物。S5已验收，reports/s5-acceptance.json留存，tag为stage-5-release-candidate。

继续S6：恢复后的wheel路径重写与全新CPU HTTP环境实测、最终README/快速开始/复现/报告与资产索引、累计学习包、独立checkout验证和最终发布tag。现有GPU执行逻辑保持冻结，工具和文档修改不构成再次GPU测速或宿主迁移证据。持续目标不在S5结束。

阶段历史见[历史进度](progress-through-s5-development.md)，当前27项证据见[覆盖](coverage.md)，累计讲解与六条事实简历见[阶段包](stages/S5/README.md)。没有后台定时同步、自动开机或agent自动唤醒；活动任务先核验PID/boot_id/start_ticks，避免重复执行。

本地证据审计reports/s5-evidence-audit.json已通过：650份终态run、182对象收据、全部选定文档链接，无未结束任务和错误。独立远端复算同样已通过。
