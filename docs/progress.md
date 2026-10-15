# DriveServe 当前进度

更新：2026-10-15T06:45:31.081978+00:00。**S1/S2/S3/S4 accepted；S5准备实施；S6未验收。** 最新完整版本为stage-4-depth，先前阶段tag继续保留。无预算、凭据或范围问题需用户选择。

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

更新：2026-10-15T14:37:59.730440+08:00。S4 accepted。11项边界已重聚合；三轮各8任务全完成，共24独立进程/20指标组，reports/s4-depth.json及docs/s4-depth-results.md为最终三轮表。各引擎36条输出/status一致、heap/scan逐请求cached tokens一致。cache heap总时间差异方向不稳定；both差异0.098–0.464%很小，保留scan默认。16384池CPU中位scan4.84–4.89ms对heap14.81–18.03μs，Python allocation3.46→8.54MB，heap最大操作5.64–11.33ms。CUDA T1 half2约1.434–1.448μs对v1约2.734–2.744μs；scalar T2048退化；auto cutoff32不变，不算服务TPOT收益。

独立维护诊断143023-7f85f5a6d8/包装2ce1325b16已完成，scripts/analyze_heap_diagnostic.py实际重聚合reports/s4-heap-maintenance.json。16384池首次8192 stale pops、0重建；强制TTL31秒后4352重分类；128池10次实际重建。GC及仪器自身分配影响单独记录，不把所有_compact耗时叫重建，也不能追溯旧run的GC。诊断不进正式速度表。

当前无活跃GPU/OSS任务。本地审计与独立GitHub checkout 730c5d5均实际通过；28 CPU测试、4份产物逐字节复算、483份run审计。reports/s4-github-readback保存原始输出，reports/s4-acceptance.json为验收。累计README/replay/resume/27项coverage和维护诊断已留存。验收提交创建并推送stage-4-depth后独立读回tag，随即继续S5。

后续S5实现quant×spec实际兼容/同Target比较，开环客户端与全程deadline、业务组合和final-test；S6最终发布。S5草稿在artifacts/preparation-s4-s5，未集成或验证，勿视为完成；/tmp/driveserve-s5-review-notes.md提示现CLI硬编码dev及quant target-only问题，必须实际解决，不能把它当上游不支持。

持续目标不因单阶段完成而结束。用户材料已提供，尚未复述/追问验证；没有自动开机或agent自动唤醒。GPU按量、OSS留存已授权，无需重复询问常规工作；新增其他付费资源才需要用户选择。

## S5开发接续

S4 tag stage-4-depth→21fbdf7已从GitHub独立读回，reports/s4-tag-readback.json留存。S5首次集成开环客户端和显式split/量化推测入口，开发计划configs/s5-development-plan.json。前两轮本地HTTP fixture失败：测试误将同时到达的ordinal视为固定入队顺序；实际检查显示一条已发送、一条未发送均超时，修正为不依赖ordinal的断言。另加出队deadline防御检查，失败日志保留在reports/s5-development-tests。实际GPU组合尚待执行，不预记成功；final-test仍未送模型。
