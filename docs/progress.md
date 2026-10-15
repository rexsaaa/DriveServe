# DriveServe 当前进度

更新：2026-10-15T11:49:19.294833+08:00。S1 accepted；S2 verification_pending，27/27最低要求validated，尚未创建S2 tag。S3–S6未验收。当前无GPU或备份任务运行，无新增预算/凭据/范围问题需要用户处理。

## 本轮完成与证据

- 三组自主AWQ（domain128/general128/domain64）完成28层校准/导出；四模型固定KV137请求全部完成，FP16/domain128/domain64业务121/128，general128为118/128。代表21层平均失真64比128低23.6744%，按事前规则仍选领域128候选；FP16保留默认。详见docs/awq-results.md与reports/s2-awq.json。
- 实际逻辑权重15,231,233,024→5,570,747,392bytes；固定KV8192tokens独占测试与同0.5总预算容量分开，FP16/领域128各172480/338304token槽位，不称已验证满载服务容量。首次shape元数据失败及修复保留。
- 三部署×两长度×两并发共768/768完成，逐请求重聚合。并发8双副本总吞吐高于TP2，并发1TP2 E2E较低；长填充单卡/副本44/64、TP2 43/64，dev-030不同。不能凭拓扑或单次数据宣称稳定收益；详见docs/deployments.md。
- group128 30包、group64 16包全部OSS完整回读；项目累计144对象51,794,986,555bytes，估算0.49723元/天。恢复脚本另取回三组config及trained config/checkpoint元数据，收据s2-restore-*.json。
- 中文阶段提交3d055ae已推送；当前未提交的工作是S2累计讲解、27项覆盖、部署聚合、完整收据和证据审计入口，待作为发布准备单元提交。先前失败、原始run和模型保留。

## 保持成立的六线基础

M1固定源码链/可关闭观察器/Nsight；M2真实冷热淘汰与长度老化、共享取消抢占及B1四对照；M3实际K、原生采样修复、128步真实蒸馏、SIGTERM全状态续训与贡献分离；M4三组AWQ与误差/显存分解；M5独立自定义CUDA、48数值/16memcheck/6计时形状；M6真实FA2/时间线/公平部署。逐项见coverage.md，累计从零讲解及六主题简历在docs/stages/S2。

train512/calibration256/dev128/final-test256隔离，最终test未用于模型评测。原/新Draft fixed在137请求均与Target相同，trained adaptive136/137；全部业务121/128。接受率83.90%→86.92%，单次带trace吞吐未超过Target，默认仍关闭。不能把FP16近似/并列边界改成严格序列等同保证。

## 环境、留存与恢复

两张RTX4090各49140MiB、driver550.163.01、无NVLink/P2P失败；torch2.6.0+cu124、vLLM0.8.5、transformers4.51.3，153基础依赖锁。GPU Python为/hy-tmp/driveserve/venv-rebuilt/bin/python；训练training-deps-v1、AWQ awq-deps-v2，原wheel不改。上游ba41cc90e8ef7f236347b2f1599eec2cbb9e1f0d。Target/Draft在/hy-tmp模型目录，通用128与领域64在artifacts/models。

/hy-netdisk仍为overlay，GitHub+OSS承担持久化。约4.2GiB临时盘和11GiB overlay可用（以df复核），不要在/hy-tmp堆备份暂存；此前只回收经运行副本与OSS全量校验的5个冗余下载权重。真实宿主迁移和物理24GB卡未验证。GPU按量开机无固定截止日；OSS已取消30GB上限，其他新增资源需决定。

## 下一步

1. 本地证据审计：所有终态run hash、clean正式代码、Git包含、OSS收据、材料链接；更新有问题的记录而不删失败。
2. 推送S2发布准备提交，独立GitHub checkout取回并重聚合关键报告、运行CPU回归；通过后封存验收报告、coverage快照和stage-2-minimum tag，再读回tag。
3. 继续S3：至少三次独立重复、质量阈值、编译/后端与支持边界、TP2差异诊断、服务计时可靠性和原生B1；S4至少两项实质深化；S5组合/final-test；S6最终复现与发布。

任务接管以manifest PID/boot/start_ticks和GPU实际占用为准；reports/active-tasks.json只是快照。没有自动开机或agent唤醒。用户材料已生成，尚未实际复述/追问验证。
