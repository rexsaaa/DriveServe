# DriveServe 面试准备：进阶命令附录

资料导航与新 session 接续说明：[README](README.md)。

更新：2026-10-19。返回[第一轮最低准备清单](interview-benchmark-commands.md)。

**本页供第一轮之后按需选做，不要求全部跑完才开始面试准备。** 训练、重校准和正式复现的工作量明显大于加载现成模型。先根据真实简历亮点、理解缺口和可用资源选一项，再做记录；所有个人完成状态均待核验。

| 需要深入什么 | 对应章节 |
|---|---|
| 插桩开销、纯原版vLLM参考 | 1 |
| 自然业务缓存收益、allocator、scan/heap | 2 |
| 蒸馏贡献、采样边界、训练恢复与导出 | 3 |
| 三组AWQ选型、自动KV、重新校准、AWQ×推测 | 4 |
| CUDA tile/half2 | 5 |
| 原始指标复算、历史重聚合、正式多轮复现 | 6 |

## 0. 沿用主清单环境，按任务补资产

先完成主清单第0节，在当前项目的 `interview-practice` 分支操作；`DS_LEARN="$DS_REPO"`，不另建目录。设置同一 `DS_PY/DS_MODELS/DS_POLICY/DS_SPEC/DS_OBSERVERS/DS_COMMON`。运行前确认改动已提交、工作目录干净；任务运行期间不切换分支。本页有些比较复用主清单R4的 `DS_TARGET/DS_FIXED/DS_ADAPTIVE`，变量遗失时从自己的记录恢复真实run目录；若代码或参数已改变，需重新配对比较。

以下是原机器的教师、校准和额外 AWQ 资产路径；新 clone 不包含这些大资产。先按[资产说明](../assets.md)和[复现说明](../reproduce.md)从固定收据恢复，再设置实际路径。它们由分支共用，切换分支不会自动切换其版本：

```bash
DS_TEACHER="$DS_REPO/artifacts/teacher/proxy-v1-frozen/state.json"
DS_CALIB="$DS_REPO/artifacts/data/awq-calibration-v1"
DS_GENERAL128="$DS_REPO/artifacts/models/awq-general-g128-v1"
DS_DOMAIN64="$DS_REPO/artifacts/models/awq-domain-g64-v1"
export DS_TEACHER DS_CALIB
```

只核对所选任务需要的资产：训练需 `draft-aligned-v1`、教师文件和 `/hy-tmp/driveserve/training-deps-v1`；量化需校准文件、Target、training层和 `/hy-tmp/driveserve/awq-deps-v2`；三组对比需对应模型provenance。缺项按[复现说明](../../docs/reproduce.md)恢复，不覆盖现有资产。新训练/量化输出必须使用新目录。

仍然逐项执行、失败先停下；trace与计时分开，旧证据和自己的新结果分开。后置实操不代表可以省略简历中已写内容的原理、代码和证据理解。

## 1. 观察器开销与纯原版参考

### 1.1 观察器关闭/开启

```bash
"$DS_PY" scripts/diagnose_engine.py --stage S5 --overlay "$DS_OBSERVERS"
"$DS_PY" scripts/diagnose_engine.py --stage S5 --overlay "$DS_OBSERVERS" --trace

DS_TRACE_OFF=experiments/runs/替换为关闭观察器运行ID
DS_TRACE_ON=experiments/runs/替换为开启观察器运行ID
"$DS_PY" scripts/analyze_engine_trace.py \
  --trace-off "$DS_TRACE_OFF" --trace-on "$DS_TRACE_ON" \
  --output artifacts/learning/engine-observers.json
```

结果：`results.json`、`steps.json`、`engine-trace/*.jsonl` 与聚合报告。观察器开关之外保持一致；这是插桩成本诊断，不把开启 trace 的成绩混进其他优化的速度表。

### 1.2 原版 vLLM 0.8.5 参考

```bash
"$DS_PY" scripts/benchmark_policies.py --stage S5 \
  --variant native --upstream --graph --max-seqs 4
```

这是原始wheel参考；主清单R3中的native基线保留共同WAITING-prefix正确性修复。两者用途不同，四策略增量主要看共同修复基线与候选。比较时双方Graph、模型、负载、KV和并发一致，不能用eager原版对Graph候选归因自研收益；正确性差异单独报告。

## 2. 自然业务、allocator 与 heap

### 2.1 自然业务四策略

这是另一组工作量，不能与主清单R3的合成压力直接横比时间。固定 dev32、wave8、128 块、仅业务输出，不加入推测边界题。

```bash
for DS_VARIANT in native cache scheduler both; do
  "$DS_PY" scripts/benchmark_speculation.py --stage S5 \
    --graph --prefix-cache --purpose timing --mode target --policy "$DS_VARIANT" \
    --target "$DS_MODELS/target" --draft "$DS_MODELS/draft-distilled-v2" \
    --dataset data/frozen-v1/dev.jsonl --split dev --limit 32 \
    --wave-size 8 --kv-blocks 128 --quality-only || break
done
```

记录四个目录，核对 `workload.json` 一致，对比 `waves.json` 总时间、`results.json` 中 `num_cached_tokens`、输出和规则质量。可用 `analyze_speculation.py --runs 四个实际目录 --contributions --report artifacts/learning/natural-policies.json` 聚合输出/时延；聚合器本身不会自动判定所有对照条件。先列 native，保留格式差异和错误。

**完成标准**：用本次结果说明缓存是否额外复用，不强求小样本复现旧数字；再读 S5 完整 dev128 的自然业务结论。

### 2.2 allocator 专项

主清单已有一组真实引擎生命周期检查；这里补独立allocator检查：

```bash
PYTHONPATH="$DS_POLICY:$DS_LEARN" DRIVESERVE_CACHE_IMPL=scan \
  "$DS_PY" scripts/check_policy_allocator.py
```

### 2.3 scan / heap

```bash
for DS_IMPL in scan heap; do
  "$DS_PY" scripts/benchmark_policies.py --stage S5 --variant both \
    --cache-implementation "$DS_IMPL" --graph --max-seqs 4 || break
done
"$DS_PY" scripts/check_heap_policy.py --repeat 1
"$DS_PY" scripts/diagnose_heap_maintenance.py
PYTHONPATH="$DS_POLICY:$DS_LEARN" DRIVESERVE_CACHE_IMPL=heap \
  "$DS_PY" scripts/check_policy_allocator.py
"$DS_PY" scripts/benchmark_policies.py --stage S5 --variant both \
  --cache-implementation heap --graph --max-seqs 4 --suite lifecycle --trace
```

scan/heap 只改变数据结构实现，策略保持 both。CPU `maintenance.json` 包含完整操作及内存，`differential.json/bounded-index.json/float-ttl-boundary.json` 检查等价与边界；诊断 `operations.json` 用于解释 stale pop、expiry、重建与 GC，嵌套时间不可相加。对照 CPU 中位数/P99/最大值和服务总时间，解释为何大池维护更快未必让小池推理更快。

源码/历史证据：`driveserve/engine_policies.py`、`driveserve/heap_policy.py`、`patches/vllm-v0.8.5-policies.patch`、[缓存调度](../../docs/cache-scheduler.md)、[S4 结果](../../docs/s4-depth-results.md)、[S5 自然业务](../../docs/s5-discussion.md)。

## 3. 蒸馏贡献、采样与训练恢复

### 3.1 补上原 Draft fixed 对照

若主清单R4的三组计时已完成，且代码、环境和共用参数未变，补下面一组即可；条件变化则重新配对运行。原Draft资产为 `draft-aligned-v1`。

```bash
"$DS_PY" scripts/benchmark_speculation.py "${DS_COMMON[@]}" --purpose timing \
  --mode fixed --target "$DS_MODELS/target" --draft "$DS_MODELS/draft-aligned-v1"
DS_OLD_FIXED=experiments/runs/替换为原Draft固定K运行ID
"$DS_PY" scripts/analyze_speculation.py \
  --runs "$DS_TARGET" "$DS_OLD_FIXED" "$DS_FIXED" "$DS_ADAPTIVE" \
  --contributions --report artifacts/learning/speculation-four-way.json
```

原fixed→新fixed看蒸馏增量，新fixed→adaptive看控制器增量；同一负载下比较业务子集TTFT/TPOT和总wave时间，分别核对token与结束原因，不把接受率增幅等同于加速。

### 3.2 接受率与采样边界

```bash
"$DS_PY" scripts/benchmark_speculation.py "${DS_COMMON[@]}" --purpose diagnostic \
  --mode fixed --trace --target "$DS_MODELS/target" --draft "$DS_MODELS/draft-aligned-v1"
"$DS_PY" scripts/benchmark_speculation.py "${DS_COMMON[@]}" --purpose diagnostic \
  --mode fixed --trace --target "$DS_MODELS/target" --draft "$DS_MODELS/draft-distilled-v2"
"$DS_PY" scripts/benchmark_speculation.py "${DS_COMMON[@]}" --purpose diagnostic \
  --mode adaptive --trace --target "$DS_MODELS/target" --draft "$DS_MODELS/draft-distilled-v2"
```

用 `analyze_speculation.py --runs 三个实际诊断目录 --contributions --report artifacts/learning/spec-traces.json` 聚合。读取 `spec-trace` 和 `controller-summary.json`，手算接受前缀/提议数；bonus 不进接受分子，统计在 EOS/长度截断之前。无 trace 的计时 run 没有接受率时保留 null。K 未改变也如实记录，不能修改结果制造轨迹。

已知分布与采样边界可运行以下诊断，必须与正式计时分开：

```bash
"$DS_PY" scripts/check_rejection_distribution.py
"$DS_PY" scripts/check_seeded_sampler.py --overlay "$DS_SPEC"
```

**完成标准**：原 fixed→新 fixed 解释蒸馏增量；新 fixed→新 adaptive 解释控制器增量，不能将接受率提高直接等同加速。参考[推测记录](../../docs/speculation.md)、`driveserve/spec_control.py`、`patches/vllm-v0.8.5-spec.patch`、`reports/s3-boundaries-fixed.json`。

### 3.3 教师与训练记录

```bash
"$DS_PY" - <<'PY'
import json, os
from pathlib import Path
from driveserve.task import digest
state = json.loads(Path(os.environ['DS_TEACHER']).read_text())
assert digest(state['records']) == state['records_sha256']
rows = state['records']
print('records', len(rows), 'eligible_train', sum(r['train_eligible'] for r in rows))
print('filtered_train', sum(r['split']=='train' and not r['train_eligible'] for r in rows))
print('example_eligible', next(r for r in rows if r['train_eligible']))
print('example_filtered', next(r for r in rows if r['split']=='train' and not r['train_eligible']))
PY
"$DS_PY" -m json.tool reports/s2-training-128.json
"$DS_PY" -m json.tool reports/s2-training-recovery.json
```

按 [训练协议](../../docs/distillation-protocol.md)和 `scripts/train_draft.py` 解释 prompt labels=-100、答案交叉熵、反向传播与优化器更新、LoRA rank/alpha、梯度累积、128 步调度。手动区分 train/calibration/dev/test；教师生成只读取 train/dev，dev 不回传梯度。已有最终测试只读保存的报告，不能重新拿它选择参数。

### 3.4 短训练、SIGTERM恢复与导出

这项会真正训练。先停掉其他 GPU 任务，检查磁盘；保留原资产，输出必须是新目录。演练固定 **128 步 scheduler，实际仅训练至16步**，包含连续参考、SIGTERM 中断和恢复，不是把 scheduler 改成16步。

```bash
DS_TRAIN_PARENT=$(mktemp -d "$DS_LEARN/artifacts/learning/training.XXXXXX")
"$DS_PY" scripts/drill_training_recovery.py \
  --teacher "$DS_TEACHER" --output "$DS_TRAIN_PARENT/recovery" --gpu 0
```

脚本固定使用当前 `/hy-tmp/driveserve/models/draft-aligned-v1` 和 `training-deps-v1`；它没有 `--layer` 参数。检查运行目录的 `signal.json`、`state-comparison.json`、三阶段日志和训练 `latest.json/checkpoint.json`。应核对 adapter、optimizer、scheduler、RNG、cursor、loss/LR/样本顺序；失败就保留差异。不要把只加载 adapter 称为完整恢复。

导出并加载本次16步模型：

```bash
"$DS_PY" scripts/export_draft.py \
  --training "$DS_TRAIN_PARENT/recovery/resumed" \
  --destination "$DS_TRAIN_PARENT/draft16"
"$DS_PY" scripts/benchmark_speculation.py "${DS_COMMON[@]}" --purpose timing \
  --mode fixed --target "$DS_MODELS/target" --draft "$DS_TRAIN_PARENT/draft16"
```

当前导出脚本已复制字节一致的基础 tokenizer；无需为了流程再复制一份模型。检查 provenance 的训练 step=16，不能将本次模型说成历史128步模型，也不预设质量或性能一定改善。

扩展复现（不必第一轮执行）：重新生成教师、完整128步训练分别是：

```bash
"$DS_PY" scripts/generate_teacher.py --data data/frozen-v1 \
  --state "$DS_TRAIN_PARENT/new-teacher" --gpu 0
"$DS_PY" scripts/train_draft.py --teacher "$DS_TEACHER" \
  --output "$DS_TRAIN_PARENT/full128" --steps 128 --gpu 0
```

第二条沿用已冻结教师，保留原 recipe；新教师是独立产物，若要改用它，明确记录数据变化。训练中断要沿用同一 output 与完全相同 recipe 才能恢复；输出目录存在不代表可任意改步数续训。

## 4. AWQ选型、校准与组合

### 4.1 FP16与三组量化产物

先运行主清单R4的 FP16 Target 基线，保留 `DS_TARGET`。下面三组只更换量化产物；均为固定512 KV块、同 `DS_COMMON`、不启用推测。

```bash
for DS_QUANT_MODEL in "$DS_GENERAL128" "$DS_MODELS/awq-domain-g128-v1" "$DS_DOMAIN64"; do
  "$DS_PY" scripts/benchmark_speculation.py "${DS_COMMON[@]}" --purpose timing \
    --mode target --target "$DS_QUANT_MODEL" \
    --draft "$DS_MODELS/draft-distilled-v2" --quantization awq || break
done
```

记录 general128/domain128/domain64 各目录。可将 FP16 Target 与三个 AWQ Target 一起传给 `analyze_speculation.py --runs … --contributions --report artifacts/learning/awq-inference.json` 看时延、质量与 token 差异；量化不要求与 FP16 逐 token 一致，不能用输出更长带来的 token/s 增加单独证明等工作量加速。

```bash
DS_AWQ=experiments/runs/替换为领域128运行ID
"$DS_PY" -m json.tool "$DS_TARGET/memory-final.json"
"$DS_PY" -m json.tool "$DS_AWQ/memory-final.json"
"$DS_PY" -m json.tool reports/s2-awq.json
```

`live-model-tensors.json` 中看高精度权重；`memory-final.json` 的 `gpu_processes` 是采样时进程显存，不是峰值或权重大小。训练/推理使用的容器 PID 与 nvidia-smi 宿主 PID 可能不同。

**选择依据**：阅读 `reports/s2-awq.json` 的 `calibration/selection`，复核领域64对128局部 MSE 下降约23.67%、未到25%阈值，及质量与速度取舍。当前32条练习不能重写历史完整dev128的选择。通用/领域使用不同输入分布，不能仅按它们局部 MSE 的大小作公平因果结论。

### 4.2 自动KV容量

```bash
"$DS_PY" scripts/benchmark_speculation.py "${DS_COMMON[@]}" \
  --purpose capacity --automatic-kv --mode target \
  --target "$DS_MODELS/target" --draft "$DS_MODELS/draft-distilled-v2"
"$DS_PY" scripts/benchmark_speculation.py "${DS_COMMON[@]}" \
  --purpose capacity --automatic-kv --mode target \
  --target "$DS_MODELS/awq-domain-g128-v1" --draft "$DS_MODELS/draft-distilled-v2" \
  --quantization awq
```

`--automatic-kv` 覆盖固定块预算，由相同0.5显存比例计算 KV。对比 `actual_gpu_blocks`，手算每token `2×28×4×128×2=57344 bytes`。它是分配容量体验，不是把全部槽位装满后的并发承载验收；不与固定512块计时混比。

### 4.3 重新校准、导出与加载

使用现有冻结校准数据；分别核对 `calibration-manifest.json`、通用语料许可/版本、领域 calibration split 与32×512等 token 预算。不会重新下载语料或改最终测试集。

```bash
"$DS_PY" -m json.tool "$DS_CALIB/calibration-manifest.json"
DS_QUANT_PARENT=$(mktemp -d "$DS_LEARN/artifacts/learning/calibration.XXXXXX")
"$DS_PY" scripts/quantize_awq.py --stage S5 \
  --data "$DS_CALIB" --source domain --group 128 \
  --destination "$DS_QUANT_PARENT/domain128" --gpu 0
"$DS_PY" scripts/benchmark_speculation.py "${DS_COMMON[@]}" --purpose timing \
  --mode target --target "$DS_QUANT_PARENT/domain128" \
  --draft "$DS_MODELS/draft-distilled-v2" --quantization awq
```

先等校准完全完成，再运行加载。脚本固定 Target、训练依赖路径，AWQ层默认为 `awq-deps-v2`；不是可以任意减成几步的玩具脚本。检查28个 `layer-*.json`、21个代表线性层、`tensor-inventory.json`、`export.json` 与导出 provenance。中断后整组换新目标目录重做，不能把层进度视为续量化 checkpoint。

对照历史 `reports/s3-awq-reproducibility.json`，解释13个导出文件逐字节一致的验证条件。自己的新导出可逐文件计算哈希与旧 manifest 比较，若不一致如实记录；新目录的 data manifest 路径或环境不同不能被说成严格原条件复现。

扩展：完整重做选型时，再以同校准数据、预算和新目录运行 `--source general --group 128` 与 `--source domain --group 64`，并对四组全部用 dev128+9边界进行推理。`scripts/analyze_awq.py` 硬性要求每个推理run为137请求，不能把本清单41请求直接传给它；首轮用现有推理聚合器和保存的校准报告。

### 4.4 AWQ×推测

```bash
for DS_MODE in target fixed adaptive; do
  "$DS_PY" scripts/benchmark_speculation.py "${DS_COMMON[@]}" --purpose timing \
    --mode "$DS_MODE" --target "$DS_MODELS/awq-domain-g128-v1" \
    --draft "$DS_MODELS/draft-distilled-v2" --quantization awq || break
done
```

这三组单独聚合，先列 AWQ Target，不能拿 FP16 Target 检查“保持量化Target输出”。成本包括 Draft 和验证，接受率高不保证端到端快。自己的短测可能波动，历史“三轮更慢”看[组合讨论](../../docs/s5-discussion.md)，不因一轮反向结果抹掉旧证据。

源码/历史证据：`scripts/quantize_awq.py`、`scripts/analyze_awq.py`、[AWQ协议](../../docs/awq-protocol.md)、[量化结果](../../docs/awq-results.md)。需定位保留高精度的 embedding/lm_head/norm/bias，明确复用 AutoAWQ。

## 5. CUDA v2 tile/half2

先完成主清单R6的v1，再运行：

```bash
export DRIVESERVE_CUDA_BUILD_V2="$DS_LEARN/artifacts/build/rope-cache-v2"
```

```bash
"$DS_PY" scripts/check_rope_depth.py --stage S5 --repeat 1 --benchmark
compute-sanitizer --tool memcheck --error-exitcode 99 \
  "$DS_PY" scripts/check_rope_depth.py --stage S5 --quick --sanitizer
for DS_VARIANT in auto half2; do
  "$DS_PY" scripts/check_rope_contract.py --stage S5 --variant "$DS_VARIANT" || break
done
```

看各形状的 v1/scalar/half2/auto 和显式拒绝边界。解释小T提高并行度、half2/FMA舍入、地址对齐与奇数stride、auto小/大T分派，以及 scalar 大T退化。每run里的20个Event样本不是20次独立进程重复。

源码/历史证据：`csrc/rope_cache.cu`、`csrc/rope_cache_tiled.cu`、`driveserve/rope_cache.py`、[算子范围](../../docs/rope-cache.md)、[S4消融](../../docs/s4-depth-results.md)。先读透 v1，再读 v2，不以记住加速百分比代替线程与地址分析。

## 6. 原始复算与完整复现

### 6.1 复算自己的一个HTTP cell（CPU辅助）

主清单R7要求手算一条TPOT并核对P99；需要自动核对完整summary时用下面的短脚本。

把 `DS_HTTP_RUN` 换成一个实际开环目录。该段仅CPU读取自己的原始记录，并与脚本保存的summary核对；不会重新发请求。

```bash
DS_HTTP_RUN=experiments/runs/替换为本次HTTP运行ID
export DS_HTTP_RUN
"$DS_PY" - <<'PY'
import json, os
from pathlib import Path
from driveserve.openloop_stats import summarize
root=Path(os.environ['DS_HTTP_RUN']);label='natural-r32'
m=json.loads((root/'manifest.json').read_text());p=m['config']['protocol']
rows=[json.loads(x) for x in (root/(label+'-requests.jsonl')).read_text().splitlines()]
v=json.loads((root/(label+'-measurement.json')).read_text())
a=summarize(rows,v['epoch_ns'],v['arrival_window_s'],p['slo']['natural'])
a.update(workload='natural',nominal_rate=32,repeat=m['config']['repeat'],deployment=m['config']['deployment'])
assert a==json.loads((root/(label+'-summary.json')).read_text())
print(json.dumps(a,ensure_ascii=False,indent=2))
r=next(x for x in rows if x['status']=='completed')
print('request',r['request_id'],'TTFT_s',(r['first_content_ns']-r['sent_ns'])/1e9,
      'user_E2E_s',(r['finished_ns']-r['planned_ns'])/1e9)
PY
```

再手算一条TPOT、P99排序位置、发送滞后和一个SLO判定；失败/超时不能删出分母，分组goodput共用父cell完整结束窗口。参考 `driveserve/openloop.py`、`driveserve/openloop_stats.py`、`driveserve/benchmark.py`、[S5结果](../../docs/s5-results.md)。

### 6.2 历史报告完整重聚合（CPU，按需）

第一轮只需定位并复算四组数字。需要深入核验原始run、三轮、额外heap/v2亮点或最终质量时，选择相关命令；这些命令不会训练或发起推理。

这些命令读取Git保存的原run，不做GPU推理。新报告只写入 `artifacts/learning`；核对数值与run集合，输出路径变化可能使整个JSON哈希不同，不声称字节完全相同。

```bash
"$DS_PY" scripts/analyze_s5_composition.py \
  --states reports/s5-timing-v2-r1-state.json reports/s5-timing-v2-r2-state.json reports/s5-timing-v2-r3-state.json \
  --report artifacts/learning/history-s5-composition.json
"$DS_PY" scripts/analyze_s5_openloop.py \
  --states reports/s5-timing-v2-r1-state.json reports/s5-timing-v2-r2-state.json reports/s5-timing-v2-r3-state.json \
  --report artifacts/learning/history-s5-openloop.json
"$DS_PY" scripts/analyze_replication.py \
  --states reports/s3-timing-r1-state.json reports/s3-timing-r2-state.json reports/s3-timing-r3-state.json \
  --report artifacts/learning/history-s3.json
"$DS_PY" scripts/analyze_s4_replication.py \
  --states reports/s4-timing-r1-state.json reports/s4-timing-r2-state.json reports/s4-timing-r3-state.json \
  --report artifacts/learning/history-s4.json
"$DS_PY" scripts/analyze_s5_final.py --state reports/s5-final-quality-state.json \
  --protocol configs/s5-final-quality.json --report artifacts/learning/history-final-quality.json
```

AWQ按保存报告中的run ID取原始输入，精确复算原三组校准和六组推理；不将新41请求传给要求137请求的聚合器。

```bash
"$DS_PY" - <<'PY'
import json, subprocess, sys
from pathlib import Path
r=json.loads(Path('reports/s2-awq.json').read_text())
argv=[sys.executable,'scripts/analyze_awq.py','--calibration-runs']
argv += ['experiments/runs/'+x['run_id'] for x in r['calibration']]
argv += ['--inference-runs']+['experiments/runs/'+x['run_id'] for x in r['inference']]
argv += ['--timing-eligible']+[x['run_id'] for x in r['inference'] if x['timing_eligible']]
argv += ['--report','artifacts/learning/history-awq.json']
subprocess.run(argv,check=True)
PY
```

深入核验时，用上面的原始记录复算后再对照下表；主清单的第一轮不要求重跑本节全部聚合器。

| 简历表述 | 需要定位的对照 | 必须说出的边界 |
|---|---|---|
| TPOT约降18% | S5 FP16 Target 16.6617→新Draft fixed 13.6884 ms | 同原生APC、三轮；非动态K贡献；TTFT增加 |
| 进程显存约降56% | AWQ固定KV的15900→6988 MiB | 结束时进程采样，非峰值、非权重大小 |
| v1 CUDA约降18%–31% | S3六形状上游分步→v1 | Graph/Event独立微基准，未接服务 |
| TP2 P99约降27%–34% | S5各轮双副本→TP2，同两卡自然r32 | 每cell256条，计划到达起算，小样本尾部观察；SLO仍大量不满足 |
| heap与v2额外亮点 | S4 16k候选scan/heap；T1 v1/half2 | CPU完整维护有额外内存/长尾；GPU独立算子，不能混成服务收益 |
| 蒸馏与AWQ工程事实 | 472样本/128步、恢复全状态；三组等token校准、21代表层、13导出文件 | 序列蒸馏非logit；局部误差非最终质量；AutoAWQ是上游能力 |

下降比例统一 `(基线－候选)/基线`。查看 `reports/s3-awq-reproducibility.json` 与 `reports/s2-training-recovery.json` 解释哈希相等/状态相等究竟验证了什么。最终测试成绩只能说明该固定代理任务，不证明跨模板泛化或真实驾驶安全。

### 6.3 正式多轮复现（后续选做）

新目录复制 `configs/s5-openloop-formal.json`，保持每cell256/原轨迹/原SLO，按三轮轮换部署顺序，各配置设置对应 `--repeat 1/2/3`。也可选择已冻结的 `configs/s5-timing-plan-v2-r*.json` 全计划，每轮用新的 `--state artifacts/learning/.../state.json`。这是大于首轮的正式复现工作量，不通过篡改旧plan/state充当旧实验；旧P99证据的复算见本附录6.2节。

执行入口与具体计划参数见[S5回放](../../docs/stages/S5/replay.md)。双方独立重复须匹配并轮换顺序；三轮也不构成生产稳定P99保证。不要修改旧plan/state或封存报告来容纳新结果。

每项仍用主清单的短记录模板，标明“仅阅读 / 提示下完成 / 查文档独立完成 / 条件缺失”。16步恢复演练不等于亲手重做128步正式训练，一组重校准不等于完整三组选型；所有个人履历描述按真实经历填写。新产物释放机器前备份并读回核对。
