# DriveServe 当前进度

更新：2026-10-15T13:49:43.263330+08:00。**S1/S2/S3 accepted；S4 in_progress；S5/S6未验收。** 最新完整版本为stage-3-validated，S2 tag stage-2-minimum继续保留。无预算、凭据或范围问题需用户选择。

## 已完成与实际证据

S3三轮各18项，共54独立进程/39指标组；三份reports/s3-timing-r*-state.json封存。16项边界诊断也已完成并实际重聚合，reports/s3-boundaries-state.json及s3-boundaries.json记录：28 CPU、4 allocator、两次Graph生命周期各792不变量快照/32共享块/2取消/1抢占，维护trace、隔离审计、索引alias修复前后4类、24非法输入/只读alias正例、48正常数值/16 memcheck，随机Graph及四fixed trace。

414份终态run原始hash/Git包含审计通过，GitHub独立checkout bff5a6a执行28 CPU与四JSON/生成表精确复算通过；报告reports/s3-github-readback/readback.json。首次验证早于clone结束，HEAD缺失、未执行测试的失败已保留，完成克隆后验证通过。当前9个OSS小成员重新下载并核验归档/内容hash，完整权重/环境沿用144对象51,794,986,555bytes历史全量读回。S3验收reports/s3-acceptance.json；累计讲解、回放、六条简历和27项覆盖见docs/stages/S3。

## 结果与限制

Graph每配置137请求，三种推测每轮137/137与Target token相同、业务121/128。Target总时间17.1860±0.0277s，新fixed14.9691±0.1429s、adaptive15.1730±0.2435s；fixed TTFT增加、动态K无稳定增量优势。原/新fixed三次诊断接受率2328/2776与2325/2676。AWQ通用128质量118未过120门槛，领域128/64及Marlin121。默认仍FP16 Target及原生策略。

三部署2304/2304完成，但TP2首轮明显快于后两轮，原因未知；相同source/config/workload/硬件核验不能证明连续运行热状态相同。每轮长填充dev-030额外质量差异保留；每cell64 P99仅探索。自研CUDA仍是独立FP16 NeoX Q28/KV4 D128，没有服务接入。索引别名前探针在dispatch拦截，没有实际危险kernel/OOB证据。

train512/calibration256/dev128/final-test256；final-test未送模型。128步LoRA与SIGTERM全状态恢复已经完成，无需重训；AWQ独立重复13文件/21局部误差完全相同、复用原OSS对象。数据审计读896条/224组，教师640中472 eligible train，四段训练日志样本均来自eligible train；不证明跨模板泛化。

## 环境、资产与恢复

GPU Python `/hy-tmp/driveserve/venv-rebuilt/bin/python`；torch2.6.0+cu124/vLLM0.8.5/transformers4.51.3，153基础依赖，上游ba41cc90e8ef7f236347b2f1599eec2cbb9e1f0d。两RTX4090各49140MiB，driver550.163.01、无NVLink/P2P失败，TP2 custom allreduce关闭。policy overlay `/hy-tmp/driveserve/vllm-policies-v2`，spec overlay `/hy-tmp/driveserve/vllm-spec-v3`；训练Draft `/hy-tmp/driveserve/models/draft-distilled-v2`。

/hy-netdisk为overlay，GitHub+OSS承担留存；/hy-tmp临时盘约4.2GiB剩余、overlay约6.5GiB（使用前再检测）。OSS约51.795GB、0.49723元/天，30GB旧上限已取消。没有宿主迁移或物理24GB卡实证。GPU按量保持开机，没有确认截止日；新增其他付费资源需要用户决定。不改Codex认证、API隧道或tmux，不依赖Mac。

## 下一步与当前任务

更新：2026-10-15T14:00:10.116198+08:00。S4实现8728669已推送。11项边界计划全部完成并实际重聚合：reports/s4-boundaries-state.json/s4-boundaries.json。20k差分/5000反复更新与清空、两种allocator各4、275CUDA、三入口各24拒绝、99memcheck0错误、两Graph生命周期16条输出/状态相同。原CUDA源与S3一致。S3标签已从独立克隆fetch核验，reports/s3-tag-readback.json。

当前准备固定本单元后启动首轮正式计时：`python3 scripts/run_experiment_plan.py --plan configs/s4-timing-plan-r1.json --state artifacts/s4-timing-r1/state.json`。每轮8项，三轮合计24独立进程；CPU规模与CUDA五方案及6引擎配置分开。聚合scripts/analyze_s4_replication.py尚未实际跑结果，当前仅语法通过。没有S4性能完成结论；docs/stages/S4/README.md暂为增量，最终须累计改写。

计划内保持源码干净，勿另起GPU/OSS任务；按state与真实PID/boot/start_ticks接管，不重复活跃任务。日志/状态30秒保存；失败保留并整单元重测。S4其余四线沿用S3固定实现和必要回归，不重训/重复量化充进度。三轮后汇总消融/内存/维护成本/边界/负收益，更新27项与六线累计材料、独立读回后才验收。

S5组合、开环goodput与最终test；S6最终发布。持续目标不因单阶段完成而结束。用户学习材料已提供，尚未复述或追问验证；没有自动开机或agent自动唤醒。
