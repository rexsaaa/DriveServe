# DriveServe 当前进度

更新：2026-10-15T11:49:19.294833+08:00。S1 accepted；S2 accepted，27/27最低要求validated，验收报告reports/s2-acceptance.json；stage-2-minimum已推送并从GitHub读回，指向5dc0a8e。S3 in_progress，S4–S6未验收。当前先固定S3协议和重复/Graph入口，尚未启动新GPU任务，无新增预算/凭据/范围问题需要用户处理。

## 本轮完成与证据

- 三组自主AWQ（domain128/general128/domain64）完成28层校准/导出；四模型固定KV137请求全部完成，FP16/domain128/domain64业务121/128，general128为118/128。代表21层平均失真64比128低23.6744%，按事前规则仍选领域128候选；FP16保留默认。详见docs/awq-results.md与reports/s2-awq.json。
- 实际逻辑权重15,231,233,024→5,570,747,392bytes；固定KV8192tokens独占测试与同0.5总预算容量分开，FP16/领域128各172480/338304token槽位，不称已验证满载服务容量。首次shape元数据失败及修复保留。
- 三部署×两长度×两并发共768/768完成，逐请求重聚合。并发8双副本总吞吐高于TP2，并发1TP2 E2E较低；长填充单卡/副本44/64、TP2 43/64，dev-030不同。不能凭拓扑或单次数据宣称稳定收益；详见docs/deployments.md。
- group128 30包、group64 16包全部OSS完整回读；项目累计144对象51,794,986,555bytes，估算0.49723元/天。恢复脚本另取回三组config及trained config/checkpoint元数据，收据s2-restore-*.json。
- 发布准备4720da7与重聚合修复cf88450已推送并在独立checkout核验；247终态run全部hash有效，CPU24通过，四份完整核心报告精确重聚合。当前提交S2验收与读回证据，先前失败和模型均保留。

## 保持成立的六线基础

M1固定源码链/可关闭观察器/Nsight；M2真实冷热淘汰与长度老化、共享取消抢占及B1四对照；M3实际K、原生采样修复、128步真实蒸馏、SIGTERM全状态续训与贡献分离；M4三组AWQ与误差/显存分解；M5独立自定义CUDA、48数值/16memcheck/6计时形状；M6真实FA2/时间线/公平部署。逐项见coverage.md，累计从零讲解及六主题简历在docs/stages/S2。

train512/calibration256/dev128/final-test256隔离，最终test未用于模型评测。原/新Draft fixed在137请求均与Target相同，trained adaptive136/137；全部业务121/128。接受率83.90%→86.92%，单次带trace吞吐未超过Target，默认仍关闭。不能把FP16近似/并列边界改成严格序列等同保证。

## 环境、留存与恢复

两张RTX4090各49140MiB、driver550.163.01、无NVLink/P2P失败；torch2.6.0+cu124、vLLM0.8.5、transformers4.51.3，153基础依赖锁。GPU Python为/hy-tmp/driveserve/venv-rebuilt/bin/python；训练training-deps-v1、AWQ awq-deps-v2，原wheel不改。上游ba41cc90e8ef7f236347b2f1599eec2cbb9e1f0d。Target/Draft在/hy-tmp模型目录，通用128与领域64在artifacts/models。

/hy-netdisk仍为overlay，GitHub+OSS承担持久化。约4.2GiB临时盘和13GiB overlay可用（以df复核），不要在/hy-tmp堆备份暂存；此前只回收经运行副本与OSS全量校验的5个冗余下载权重。真实宿主迁移和物理24GB卡未验证。GPU按量开机无固定截止日；OSS已取消30GB上限，其他新增资源需决定。

## 下一步

1. S2 tag读回已通过，reports/s2-tag-readback.json；后续改动归S3，S2历史版本不变。
2. S3按docs/s3-validation-protocol.md执行：先独立重复领域128校准（GPU1），同时在GPU0跑Graph与CUDA边界诊断，随后两卡空闲且无备份时串行三次独立计时；固定质量阈值，诊断TP2差异与服务计时。
3. S4至少两项实质深化；S5组合/final-test；S6最终复现与发布。S2验收不是持续目标完成。

任务接管以manifest PID/boot/start_ticks和GPU实际占用为准；reports/active-tasks.json只是快照。没有自动开机或agent唤醒。用户材料已生成，尚未实际复述/追问验证。

2026-10-15T12:05:58.083534+08:00 S3实测更新：CUDA公开入口20类非法输入全部拒绝且存储未改，负slot不写cache（115852-8c22e153b0）。Graph Target/原fixed/新fixed/新adaptive各137完成且与Target137/137文本token一致、业务均121/128；新adaptive实际K2/3/4、5次变更，见s3-graph-boundaries.json。GPU1独立domain128校准仍在run115848-1eee776d86，父115831-43c009e5ac，目标artifacts/models/awq-domain-g128-s3-repeat1；GPU0 Graph诊断已结束。下一步原生AWQ/Marlin Graph诊断、计划runner失败恢复检查，然后待校准结束开展独占计时及TP2质量诊断。

2026-10-15T12:12:57.272319+08:00 S3量化Graph诊断：general128/domain128/domain64/Marlin128均137完成，规则正确分别118/121/121/121。领域128原生与Marlin有long-1合成输出差异，业务正确数相同；GPU1同时校准，不能将本组时间用于正式性能。s3-quant-graph-diagnostic.json保留后端/显存/分组原始指标，selection pending只是诊断不重选配置。串行runner的真实失败→整单元重试→已完成跳过验证通过，见s3-plan-recovery.json；未部署自动重启。AWQ独立重复已完成28层，等待导出和逐文件比较，之后先跑TP2质量诊断，再执行configs/s3-timing-plan-r1.json等三轮，每轮18任务、无后台备份。
