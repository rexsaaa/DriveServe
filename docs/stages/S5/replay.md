# S5 累计六条主线回放入口

先按 [环境与模型恢复](../../reproduce.md) 重建固定环境并恢复资产；不要在新机器只复制带绝对软链接的 overlay。以下使用本实例实际路径，迁移时选择新目录并调整模型参数。所有正式实验须 clean Git 工作树；同一时间只启动一项 GPU 性能任务。旧 run 保留，新执行产生新 run ID，不能把旧数值当新环境结果。

```bash
/hy-tmp/driveserve/venv-rebuilt/bin/python scripts/build_vllm_overlay.py --destination /hy-tmp/driveserve/vllm-observers-new --patch-lock patches/vllm-v0.8.5-observers.json
/hy-tmp/driveserve/venv-rebuilt/bin/python scripts/build_vllm_overlay.py --destination /hy-tmp/driveserve/vllm-policies-new --patch-lock patches/vllm-v0.8.5-policies.json
/hy-tmp/driveserve/venv-rebuilt/bin/python scripts/build_vllm_overlay.py --destination /hy-tmp/driveserve/vllm-spec-new --patch-lock patches/vllm-v0.8.5-spec.json
```

M1：用新 observers overlay 依次执行 `scripts/diagnose_engine.py --overlay ...` 和 `--trace`，重聚合用 `scripts/analyze_engine_trace.py`；Nsight 独立采集命令见 engine-diagnostics.md，不与无profile正式计时混合。

M2：用新 policies overlay，分别执行以下命令的 native/cache/scheduler/both。B1为Graph/4，`--trace` 和生命周期另跑，不纳入正式速度表。

```bash
/hy-tmp/driveserve/venv-rebuilt/bin/python scripts/benchmark_policies.py --stage S3 --overlay /hy-tmp/driveserve/vllm-policies-new --variant native --graph --max-seqs 4
/hy-tmp/driveserve/venv-rebuilt/bin/python scripts/benchmark_policies.py --stage S3 --overlay /hy-tmp/driveserve/vllm-policies-new --variant both --graph --max-seqs 4 --suite lifecycle --trace
```

M3：恢复训练后的模型和原对齐Draft，分别用 target、fixed原Draft、fixed新Draft、adaptive新Draft运行。示例的新Draft路径须指向完整带provenance的恢复模型；默认target为已固定7B目录。

```bash
/hy-tmp/driveserve/venv-rebuilt/bin/python scripts/benchmark_speculation.py --stage S3 --graph --overlay /hy-tmp/driveserve/vllm-spec-new --mode adaptive --draft /hy-tmp/driveserve/models/draft-distilled-v2 --dataset data/frozen-v1/dev.jsonl --limit 128 --trace
```

不需要为回放推理重新训练。要重做训练，先恢复教师和训练wheel，按 `bootstrap_training.py --destination 新依赖目录 --wheels 恢复wheel目录` 创建附加层；`train_draft.py --teacher 教师目录 --output 新训练目录 --layer 新依赖目录 --steps 128` 实际训练。同一输出目录自动从已验证checkpoint恢复，recipe/base/data必须一致。`drill_training_recovery.py --teacher 教师目录 --output 新演练目录` 重做SIGTERM和连续参考。仅加载合并模型不能替代全状态恢复。最终导出需 `export_draft.py` 后用 `canonicalize_draft_export.py` 保持tokenizer字节一致，旧目录不可覆盖。

M4：恢复三组完整量化模型即可重跑推理；重做校准先用已备份wheel建AWQ附加层，恢复冻结校准token及manifest。真实命令如下，source取domain/general，group取64/128，分别写入新目标目录。

```bash
/hy-tmp/driveserve/venv-rebuilt/bin/python scripts/quantize_awq.py --data artifacts/data/awq-calibration-v1 --source domain --group 128 --destination artifacts/models/awq-new-domain128 --gpu 0
/hy-tmp/driveserve/venv-rebuilt/bin/python scripts/benchmark_speculation.py --stage S3 --graph --mode target --target artifacts/models/awq-new-domain128 --quantization awq --purpose timing --dataset data/frozen-v1/dev.jsonl --limit 128
```

校准脚本支持--layer调整AWQ层，但Target和training-deps-v1路径在当前脚本中固定为/hy-tmp/driveserve下相应目录；迁移须恢复该布局或先修改配置并重新验证，不能声称任意路径即用；不要覆盖基础推理依赖。容量测量另用 `--purpose capacity --automatic-kv`。详细原始run与六组重聚合见 [AWQ结果](../../awq-results.md)。AWQ中断是整组重做，不是从layer JSON续训。

M5：先确认GPU0空闲，用相同GPU Python和环境bin在PATH前部运行 `scripts/check_rope_cache.py --stage S3 --benchmark`。单独用compute-sanitizer运行 `--quick --sanitizer`；编译和memcheck不能计入性能。具体完整命令、支持形状和上游来源见 rope-cache.md。

M6：`scripts/benchmark_fa2.py --stage S3` 运行八形状；部署矩阵用 `scripts/benchmark_deployments.py --stage S3 --deployment single|replica|tp2`（各值分别运行）。端口8081/8082只监听本机，脚本拥有并清理自己的服务进程组。两卡必须空闲，生成的逐请求SSE由 `scripts/analyze_deployments.py --runs 三个run目录 --report 新报告路径` 重新聚合。

小型原始记录和Nsight报告在Git，模型/环境/教师/完整训练状态在OSS。收据的相对成员名决定恢复目录；`scripts/restore_models_oss.py --receipt 对应收据 --destination 新目录 --include 成员路径 --report 新报告` 可先探测小文件，省略include恢复全部。S2已经执行小文件恢复入口检查，完整权重则由上传后的全量读回覆盖；没有把小探测当成第二次全量恢复。

首次运行前检查 `python3 -m driveserve status` 与 `nvidia-smi`；失败或中断使用新run，不拼接计时。`scripts/audit_evidence.py` 仅检查本地hash/Git索引和保存收据，不自动等价于阶段验收或再次云端下载。

蒸馏完整报告的重聚合需要 `analyze_speculation.py --runs 四个原run目录 --contributions --context configs/s2-distillation-analysis.json --report 新报告`。context严格核对run集合，追加当时的实验限制；分组数值从原始trace/输出重算。首次独立checkout发现历史报告的分组指标未进入聚合脚本，现已补齐且与历史全部JSON精确一致；失败记录保留，不改旧指标。

## S3独立重复与边界诊断

正式主表使用三份configs/s3-timing-plan-r1/r2/r3.json。先核验两GPU空闲与没有活着的旧runner，然后每轮使用独立state路径运行 `scripts/run_experiment_plan.py --plan 对应plan --state 新state`。不要覆盖reports中已封存state；重测产生新run。保持源码干净直到本轮结束，轮间再做报告提交。GPU环境、模型与overlay路径必须实际可用；本机路径不是跨机器自动发现功能。

报告重算：

```bash
python3 scripts/analyze_replication.py --states reports/s3-timing-r1-state.json reports/s3-timing-r2-state.json reports/s3-timing-r3-state.json --report artifacts/reports/s3-check.json
python3 scripts/render_stability.py --report artifacts/reports/s3-check.json --output artifacts/reports/s3-check.md
```

源码/比较配置/输入和环境不同会拒绝合并。run级均值/标准差不能把内部Event样本视作独立进程。wrapper新增前后温度/功耗快照仅自第二轮起；第一轮未采集，重算不能制造它。

`configs/s3-boundary-plan.json` 为诊断序列，包含真实allocator、Graph lifecycle/maintenance、memcheck、随机Graph和数据隔离。fixed-K正式计时不做接受率的CPU张量复制；它的接受率来自另跑的trace诊断。三份fixed trace已实际运行并汇总接受分母，不拿计时run缺省日志填0。CUDA索引别名探针拦截extension调度，避免真的启动危险kernel；修复后的24类拒绝及正常数值另跑。

冻结最终test不在这些入口里。训练无需重做；重放已训练Draft和量化模型通过OSS收据恢复，S2完整checkpoint恢复证据继续有效。S3累计验收还要求GitHub独立checkout重聚合和资产读回；它们的报告以实际完成记录为准。

边界重聚合（不使用GPU）及资产审计：

```bash
python3 scripts/analyze_s3_boundaries.py --state reports/s3-boundaries-state.json --report artifacts/reports/s3-boundaries.json
python3 scripts/audit_evidence.py --through-stage S3 --require-tracked --report artifacts/reports/s3-audit.json
```

边界报告中内嵌的输出路径/hash随报告目标路径变化；比较数值及run集合时应保持相同相对输出路径，或显式说明路径规范化。GitHub独立checkout回放实际使用原reports路径并验证字节一致。审计不下载模型；小资产恢复探针与历史全量OSS读回各自记录，不能混称再次全量恢复。

## S4 新实现回放与受影响路径

S1–S3环境、模型、训练/量化产物恢复及六线流程在上面的累计入口保留；要逐字节重聚合旧结果使用对应tag和保存的state，不把新机器性能套到旧baseline。当前S4新增核心不要求重训/重复校准；原scan和CUDA fused(v1)入口继续保留。

先确认两卡空闲、没有活着的旧runner，用本次独立GPU Python与固定policy overlay。实际命令：

```bash
python3 scripts/check_heap_policy.py --repeat 1
PYTHONPATH=/hy-tmp/driveserve/vllm-policies-v2:/hy-netdisk/jq/project/DriveServe VLLM_USE_V1=0 DRIVESERVE_CACHE_IMPL=heap /hy-tmp/driveserve/venv-rebuilt/bin/python scripts/check_policy_allocator.py
/hy-tmp/driveserve/venv-rebuilt/bin/python scripts/benchmark_policies.py --stage S4 --variant both --cache-implementation heap --graph --max-seqs 4 --suite lifecycle --trace
/hy-tmp/driveserve/venv-rebuilt/bin/python scripts/benchmark_policies.py --stage S4 --variant both --cache-implementation heap --graph --max-seqs 4
```

scan/heap是实现开关；cache/both是功能组合，native/scheduler只能scan参数，因为没有冷热候选算法可切换。上游refcount/hash/page table并未由heap替代。CPU规模脚本产生真实类的差分、维护和内存观察，不是GPU吞吐；正式独立重复用三份计划中不同repeat。

CUDA新实现由extension_v2编译独立module，保留原.cu/.cpp。需让固定环境的ninja在PATH前部；编译产物在/hy-tmp，可重新生成，迁移需重新验证driver/CUDA/arch及正确性。

```bash
PATH=/hy-tmp/driveserve/venv-rebuilt/bin:$PATH /hy-tmp/driveserve/venv-rebuilt/bin/python scripts/check_rope_depth.py --stage S4 --repeat 1 --benchmark
PATH=/hy-tmp/driveserve/venv-rebuilt/bin:$PATH /usr/local/cuda/bin/compute-sanitizer --tool memcheck --error-exitcode 99 /hy-tmp/driveserve/venv-rebuilt/bin/python scripts/check_rope_depth.py --stage S4 --quick --sanitizer
/hy-tmp/driveserve/venv-rebuilt/bin/python scripts/check_rope_contract.py --stage S4 --variant half2
```

`fused_v2(...,variant='auto'|'scalar'|'half2'|'v1')`是检查入口；`fused(...)`仍是原v1。半字offset/奇数row stride时auto小T走scalar，显式half2报错；largeT auto回v1。不能在Graph捕获内调用包含CPU索引检查的公开入口；计时脚本在外校验后调用raw extension，这一差异须保留。memcheck与性能不能混合。

新正式三轮每轮8任务，按configs/s4-timing-plan-r1/r2/r3.json依次执行，每轮用新state目录；不能覆盖已有reports封存state。30秒心跳和PID/boot/start_ticks用于接管；失败整单元重测，训练恢复协议与benchmark重复不是同一件事。runner的inner_kind可从sanitizer中间进程的已校验wrapper日志找真实子run，不把没有manifest的任务冒充已验证。

```bash
python3 scripts/run_experiment_plan.py --plan configs/s4-timing-plan-r1.json --state artifacts/my-s4-r1/state.json
python3 scripts/analyze_s4_boundaries.py --state reports/s4-boundaries-state.json --report artifacts/reports/s4-boundaries-recheck.json
python3 scripts/analyze_s4_replication.py --states reports/s4-timing-r1-state.json reports/s4-timing-r2-state.json reports/s4-timing-r3-state.json --report artifacts/reports/s4-depth-recheck.json
python3 scripts/render_s4_depth.py --report artifacts/reports/s4-depth-recheck.json --output artifacts/reports/s4-depth-recheck.md
```

三轮原始结果均已完成，封存state可直接用于离线复算；重新测量使用新state。模型/权重没有新增，沿用先前144对象的完整OSS收据；新增代码、CPU/GPU原始记录和阶段讲解由GitHub留存并独立读回。S4不包含final-test，不使用旧S3的TP2最快轮来证明新阶段服务性能。

## S5当前组合与开环

先完成以上环境和两个overlay的恢复。S5计划内路径对应本机；迁移时创建新计划记录新路径，不修改已有正式计划来伪造相同hash。所有CLI子进程使用固定venv，不允许无aiohttp跳过HTTP fixture却声称全通过。

```bash
/hy-tmp/driveserve/venv-rebuilt/bin/python -m unittest discover -s tests -v
python3 scripts/run_experiment_plan.py --plan configs/s5-timing-plan-v2-r1.json --state artifacts/my-s5-r1/state.json
python3 scripts/analyze_s5_composition.py --states reports/s5-timing-v2-r1-state.json --report artifacts/recomputed-s5-composition.json
python3 scripts/analyze_s5_openloop.py --states reports/s5-timing-v2-r1-state.json --report artifacts/recomputed-s5-openloop.json
```

三轮已全部完成并封存reports/s5-timing-v2-r*-state.json；重测仍按各自v2计划执行并选择新state。旧v1从未运行，不把它当正式结果。最终质量按configs/s5-final-quality-plan.json调用十个冻结profile，必须在开发性能选择完成后执行，不能拿test调参。已发布结果在新环境的独立复现必须产生新run ID和环境记录，不能覆盖原成绩或重选原质量门槛。

S5尚未验收；累计数字以最终三轮报告和final质量报告为准，正式三轮见s5-results。独立CUDA继续使用原入口，不宣称开环服务已接入。
