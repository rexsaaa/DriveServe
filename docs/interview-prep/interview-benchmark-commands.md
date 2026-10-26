# DriveServe 面试最低准备：第一轮运行清单

资料导航与新 session 接续说明：[README](README.md)。

更新：2026-10-19。对应[最低准备指南](DriveServe-v1.0-面试最低准备指南.md)。命令按源码 `c166c93e1f16262f6f64f5eae31c81494c5a2d1f` 核对；本次整理未执行 GPU 实验。

**第一轮按下面 8 个任务包推进：7 组操作，最后做一次面试整理。** 每包包含几条命令，可以拆开完成。先建立操作经验，再补概念和解释；不要求重跑历史全部实验或复现原来的提升百分比。

- [ ] **R1 服务小流程（M6）**：启动→普通/流式请求→小压测→改一个参数→停止。
- [ ] **R2 性能观察（M1）**：亲手采集并打开一次 Nsight，解释一个现象。
- [ ] **R3 缓存与调度（M2）**：四策略对照，加一次生命周期检查。
- [ ] **R4 推测与蒸馏（M3）**：同一已训练 Draft 的 Target/fixed/adaptive 对照，另采一次 K 轨迹；蒸馏过程先读证据。
- [ ] **R5 AWQ（M4）**：已有 FP16/领域 AWQ 产物的速度、显存、质量对照；校准和选型先读证据。
- [ ] **R6 CUDA（M5）**：编译并运行 v1 正确性、微基准和小规模 memcheck。
- [ ] **R7 性能部署（M6）**：FA2 对照，以及小负载单卡/双副本/TP2 体验。
- [ ] **R8 面试整理**：六线讲解、四组数字复算、基础和小型编码练习。

按 **0 → R1 → R2 → … → R8** 顺序，每次只看当前一节。运行后能解释输入、输出和限制再勾选；缺少 GPU/GUI 等条件的项目保持待完成，不能用阅读旧报告代替本人操作。

训练恢复、重新校准、heap、CUDA v2、更多消融与完整复现，已移到[进阶附录](interview-benchmark-advanced.md)，**不作为第一轮全部必跑项目**。若简历主动强调这些亮点，面试前仍须补足对应实现与证据理解；个人实操经历如实描述。

## 0. 开始前：只准备本轮需要的环境

沿用项目固定 Python 3.11 / vLLM 0.8.5 / torch 2.6.0。此前核对为两张各 49140 MiB RTX 4090，执行前以本次 `nvidia-smi` 为准。暂无 GPU 时，先做 R8 中的阅读与 CPU 练习，其他操作保留待办。

在新机器已克隆的 **DriveServe 项目根目录**操作。学习分支为 `interview-practice`，`DS_LEARN="$DS_REPO"`。先按[迁移核查](portability-audit-2026-10-26.md)准备源码参考；要执行 GPU 实验，还需恢复模型和运行环境。

停止本仓库运行中的服务、训练和实验后，检查并保留现有修改，再切换分支；获取分支的命令见 [README](README.md)。已经位于学习分支时不必重新创建。

```bash
DS_REPO="$(git rev-parse --show-toplevel)"
DS_LEARN="$DS_REPO"
cd "$DS_REPO"
git status --short --branch
git switch interview-practice
```

本清单和其他学习文档现在保存在受 Git 跟踪的 `docs/interview-prep/`。新笔记若仍写入 `artifacts/learning/`，不会自动被提交；希望下次迁移时保留的笔记应写入 `docs/interview-prep/notes/` 并提交。实际操作完成状态须由用户确认，本次迁移没有替用户完成 R1–R8。

然后设置运行环境。下列 `/hy-tmp/driveserve/` 是原实例路径示例，Git 不提供这些环境、模型或 overlay；按[复现说明](../reproduce.md)恢复，并把变量改成新机器的真实路径。新终端需重新设置：

```bash
DS_REPO="$(git rev-parse --show-toplevel)"
DS_LEARN="$DS_REPO"
cd "$DS_REPO"

DS_PY=/hy-tmp/driveserve/venv-rebuilt/bin/python
DS_MODELS=/hy-tmp/driveserve/models
DS_POLICY=/hy-tmp/driveserve/vllm-policies-v2
DS_SPEC=/hy-tmp/driveserve/vllm-spec-v3
DS_OBSERVERS=/hy-tmp/driveserve/vllm-observers-v1
export DS_REPO DS_LEARN DS_MODELS
export PATH=/hy-tmp/driveserve/venv-rebuilt/bin:/usr/local/cuda/bin:$PATH
export CUDA_HOME=/usr/local/cuda
export CUDA_VISIBLE_DEVICES=0 VLLM_USE_V1=0 VLLM_FLASH_ATTN_VERSION=2
export DRIVESERVE_CUDA_BUILD="$DS_LEARN/artifacts/build/rope-cache-v1"
unset PYTHONPATH
mkdir -p artifacts/learning

git branch --show-current
git rev-parse HEAD
git status --short
nvidia-smi
"$DS_PY" -m driveserve doctor
"$DS_PY" -m driveserve status

DS_COMMON=(
  --stage S5 --graph --prefix-cache --overlay "$DS_SPEC"
  --dataset data/frozen-v1/dev.jsonl --split dev --limit 32
  --wave-size 4 --kv-blocks 512 --max-k 4
)
```

运行实验前，分支应为 `interview-practice`，`git status --short` 应为空；若还有源码改动，逐项检查并在学习分支提交后再跑，其他未跟踪文件也需按用途妥善保存。记录本次实际 SHA；提交源码后不能继续把旧 SHA 当成本次运行版本。`DS_COMMON` 是 Bash 数组。

以后在同一目录切换代码，按需要执行其中一条：

```bash
git switch main
git switch interview-practice
```

切换前停止运行中的任务并保存改动；同一目录的所有终端共享当前分支，不能一边运行一个版本一边切换另一个版本。新增且被忽略的 `artifacts/learning`、编译目录和 `experiments/runs` 产物共用，靠 run ID / SHA 区分，不随分支自动隔离。Python、模型和 overlay 也不随分支切换；若修改 vLLM patch，需按项目流程重新生成匹配的 overlay。

第一轮只需 Target、蒸馏 Draft、领域128 AWQ 三个模型，无须先准备训练、校准依赖或其他量化模型。下面只检查文件存在，完整哈希由运行脚本校验：

```bash
"$DS_PY" - <<'PYCODE'
import os
from pathlib import Path
for name in ['target', 'draft-distilled-v2', 'awq-domain-g128-v1']:
    p = Path(os.environ['DS_MODELS']) / name / 'driveserve-provenance.json'
    print(p.is_file(), p)
    assert p.is_file(), '先按 docs/reproduce.md 恢复缺失模型'
PYCODE
```

共用规则：同一时间只运行一项 GPU 实验，开始前停止自己的服务；推测/开环计时会检查两张卡是否空闲。命令失败先排错，不接着汇总。使用 dev，小样本与历史正式结果分开；最终 test 不用于调参。`--stage S5` 只是记录标签。命令中的 `替换为…运行ID` 必须换成真实目录。

## 1. R1：服务启动、请求与小压测（M6）

终端A启动服务。第一次 `DS_FRACTION=0.40`；完成请求/测量、正常停止后，第二次仅改成 `0.45`，同样执行。两轮都是当前48GB卡的学习配置，不能直接照搬到24GB卡。

```bash
DS_FRACTION=0.40
VLLM_SERVER_DEV_MODE=1 "$DS_PY" scripts/serve_smoke.py \
  --python "$DS_PY" --model-dir "$DS_MODELS/target" \
  --devices 0 --port 8000 --memory-fraction "$DS_FRACTION" --graph
```

终端B回到本次 `DS_LEARN`，设置同一 `DS_PY`。将启动命令打印的实际目录赋给 `DS_SERVICE`；查看日志，等 `Application startup complete` 后发请求。`VLLM_SERVER_DEV_MODE` 仅用于本机练习的缓存重置接口。

```bash
DS_SERVICE=experiments/runs/替换为当前服务运行ID
tail -n 40 "$DS_SERVICE/service.log"
curl -fS http://127.0.0.1:8000/v1/models
"$DS_PY" - <<'PY'
import json
from pathlib import Path
from driveserve.task import messages
row=json.loads(Path('data/frozen-v1/dev.jsonl').read_text().splitlines()[0])
body={'model':'driveserve-target','messages':messages(row['scene']),
      'temperature':0,'seed':0,'max_tokens':128,'stream':False}
Path('artifacts/learning/chat.json').write_text(json.dumps(body,ensure_ascii=False))
body.update(stream=True,stream_options={'include_usage':True})
Path('artifacts/learning/chat-stream.json').write_text(json.dumps(body,ensure_ascii=False))
PY
curl -fS http://127.0.0.1:8000/v1/chat/completions \
  -H 'Content-Type: application/json' --data-binary @artifacts/learning/chat.json
curl -fSN http://127.0.0.1:8000/v1/chat/completions \
  -H 'Content-Type: application/json' --data-binary @artifacts/learning/chat-stream.json
```

解释 API 外层JSON与生成的业务JSON、SSE、生成参数。手动改变一次输出长度上限，再发请求并核对结束原因；随后恢复相同参数用于比较。

资源对照每轮同样先暖机，再重置前缀缓存，再用同输入测量：

```bash
"$DS_PY" -m driveserve bench --dataset data/frozen-v1/dev.jsonl \
  --model driveserve-target --endpoint http://127.0.0.1:8000/v1 \
  --concurrency 4 --limit 4 --split dev --max-tokens 128 \
  --service-manifest "$DS_SERVICE/manifest.json"
curl -fS -X POST http://127.0.0.1:8000/reset_prefix_cache
"$DS_PY" -m driveserve bench --dataset data/frozen-v1/dev.jsonl \
  --model driveserve-target --endpoint http://127.0.0.1:8000/v1 \
  --concurrency 4 --limit 32 --split dev --max-tokens 128 \
  --service-manifest "$DS_SERVICE/manifest.json"
nvidia-smi --query-gpu=index,memory.used --format=csv
```

检查缓存重置的成功响应及服务日志。比较两轮启动日志中的实际KV块、显存与客户端 `summary.json/requests.jsonl`；此处是闭环探索性资源练习，不是S5正式开环。唯一变化是显存比例，KV容量随之变化是实验结果，不能写成固定KV优化收益。

终端A按 Ctrl+C，核对 `manifest.json` 子进程退出、端口不可访问与显存释放，再切换比例重启；不先结束服务就开启下一组benchmark。能解释 `max_model_len`、`max_num_seqs`、`gpu_memory_utilization` 的区别，本次只选最后一项修改。

**完成标准**：能找到请求输出、日志、token 数和结束原因；说清显存比例这个变量及结果，并确认服务已停止。这一项也完成最低指南要求的一次参数修改体验。

## 2. R2：采集并读懂一次 Nsight（M1）

第一轮只采下面一次；观察器开/关的独立开销实验放在进阶附录第 1 节。

```bash
DS_NSYS=/hy-tmp/driveserve/tools/nsight-systems-2024.5/opt/nvidia/nsight-systems-cli/2024.5.1/target-linux-x64/nsys
DS_PROFILE=$(mktemp -d "$DS_LEARN/artifacts/learning/nsys.XXXXXX")
"$DS_NSYS" profile --trace=cuda,nvtx,osrt --sample=none --cpuctxsw=none \
  --capture-range=cudaProfilerApi --capture-range-end=stop \
  --output="$DS_PROFILE/engine" \
  "$DS_PY" scripts/diagnose_engine.py --stage S5 \
  --overlay "$DS_OBSERVERS" --trace --profile
"$DS_NSYS" export --type sqlite \
  --output "$DS_PROFILE/engine.sqlite" "$DS_PROFILE/engine.nsys-rep"
"$DS_PY" scripts/analyze_nsys.py \
  --sqlite "$DS_PROFILE/engine.sqlite" --nsys-rep "$DS_PROFILE/engine.nsys-rep" \
  --report "$DS_PROFILE/analysis.json"
```

**完成标准**：用 Nsight Systems GUI 打开 `.nsys-rep`，辨认 NVTX、CPU CUDA API、GPU kernel，说明 Prefill/Decode 的一项差异、一项有证据的观测及下一步验证。GUI 不在当前环境时保留待办，把报告带到可用 GUI 打开，不能仅凭导出成功勾选 R2。

源码/历史证据：[调用链与诊断](../../docs/engine-diagnostics.md)、`driveserve/engine_trace.py`、`patches/vllm-v0.8.5-observers.patch`、`reports/s2-nsight-engine.json`。

再沿[调用链](../../docs/engine-diagnostics.md)画出“请求进入→排队/调度→KV分配→模型执行→输出/释放”，定位一个插桩点；读 `reports/s3-stability.json` 中已有观察器开销结论。知道 CPU API 与 GPU 时间可重叠，kernel 间隙不能直接证明整卡空闲或带宽瓶颈。

## 3. R3：缓存四策略与生命周期（M2）

```bash
for DS_VARIANT in native cache scheduler both; do
  "$DS_PY" scripts/benchmark_policies.py --stage S5 \
    --variant "$DS_VARIANT" --overlay "$DS_POLICY" --graph --max-seqs 4 || break
done
```

同模型、36 条请求、128 个 KV 块、最大并发 4、Graph。native 是保留共同正确性修复的基线；cache/scheduler/both 分别开启冷热淘汰、长度老化调度及组合。

```bash
DS_NATIVE=experiments/runs/替换为native运行ID
DS_CACHE=experiments/runs/替换为cache运行ID
DS_SCHEDULER=experiments/runs/替换为scheduler运行ID
DS_BOTH=experiments/runs/替换为both运行ID
"$DS_PY" scripts/analyze_policies.py \
  --runs "$DS_NATIVE" "$DS_CACHE" "$DS_SCHEDULER" "$DS_BOTH" \
  --report artifacts/learning/policies.json
```

检查 `output_comparisons`、`groups.all`、`groups.short.wait_ms`、`groups.long.wait_ms`、`groups.hot_probe`。原始文件为 `phases.json/results.json/snapshots.json`。

再做一次带 trace 的生命周期检查：

```bash
"$DS_PY" scripts/benchmark_policies.py --stage S5 --variant both \
  --overlay "$DS_POLICY" --graph --max-seqs 4 --suite lifecycle --trace
```

**完成标准**：从 `engine-trace`、`snapshots.json`、取消/完成状态解释共享、取消、释放与重用；能说清只有零引用块可淘汰、冷热与 TTL、长度老化为何可能增加长请求等待。生命周期诊断的耗时不进入四组速度表。

读[缓存调度](../../docs/cache-scheduler.md)和[自然业务结论](../../docs/s5-discussion.md)，定位 `driveserve/engine_policies.py`。第一轮自然业务只读已有证据：合成热点收益不能推广到自然业务，后者没有额外缓存复用。自然业务重跑、allocator、scan/heap 见进阶附录第 2 节。

## 4. R4：推测解码对照，蒸馏先读证据（M3）

三组使用**同一个蒸馏 Draft**：Target 不启用推测，fixed 固定 K，adaptive 动态 K。`DS_COMMON` 固定原生 APC、Graph、512 KV块、wave4、K上限4、dev32+9边界，共41请求。

```bash
for DS_MODE in target fixed adaptive; do
  "$DS_PY" scripts/benchmark_speculation.py "${DS_COMMON[@]}" --purpose timing \
    --mode "$DS_MODE" --target "$DS_MODELS/target" \
    --draft "$DS_MODELS/draft-distilled-v2" || break
done

DS_TARGET=experiments/runs/替换为Target运行ID
DS_FIXED=experiments/runs/替换为fixed运行ID
DS_ADAPTIVE=experiments/runs/替换为adaptive运行ID
"$DS_PY" scripts/analyze_speculation.py \
  --runs "$DS_TARGET" "$DS_FIXED" "$DS_ADAPTIVE" \
  --contributions --report artifacts/learning/speculation.json
```

保留 `DS_TARGET`，R5 复用这个 FP16 基线。检查 `greedy_comparisons` 和原始结束原因；速度看 `runs[].elapsed_s`、`groups.quality.mean_ttft_ms`、`contribution_groups.quality.mean_observed_tpot_ms`。业务32条与全41条的平均值不能混用；同KV预算不等于同总显存，Draft本身也占资源。

另采**一次 adaptive 诊断**看接受率和 K，不把 trace 成绩放进速度表：

```bash
"$DS_PY" scripts/benchmark_speculation.py "${DS_COMMON[@]}" --purpose diagnostic \
  --mode adaptive --trace --target "$DS_MODELS/target" \
  --draft "$DS_MODELS/draft-distilled-v2"
DS_SPEC_TRACE=experiments/runs/替换为adaptive诊断运行ID
"$DS_PY" scripts/analyze_speculation.py --runs "$DS_SPEC_TRACE" \
  --contributions --report artifacts/learning/spec-trace.json
```

**完成标准**：读 `spec-trace` / `controller-summary.json`，解释提议、验证、接受/拒绝、bonus及EOS/长度裁剪；手算一次接受前缀/提议数，bonus不进接受分子。定位 `driveserve/spec_control.py` 与 `patches/vllm-v0.8.5-spec.patch` 中滑窗、持有期、K上下限及实际提议/验证长度变化；K未变化也如实记录。

蒸馏先读[训练协议](../../docs/distillation-protocol.md)、`scripts/train_draft.py`、`reports/s2-training-128.json`、`reports/s2-training-recovery.json` 和 `reports/s3-boundaries-fixed.json`：说明472条合格样本、128步LoRA、答案labels/交叉熵、梯度累积和全状态恢复。**原Draft fixed→新Draft fixed才是蒸馏贡献对照，新fixed→adaptive看控制器增量**；本节本人三组运行不能单独证明蒸馏增量。原/新Draft重跑及训练恢复见进阶附录第3节。

## 5. R5：FP16 / 已有 AWQ 产物对照（M4）

复用 R4 的 `DS_TARGET`，同样条件只增加一组领域128 AWQ Target：

```bash
"$DS_PY" scripts/benchmark_speculation.py "${DS_COMMON[@]}" --purpose timing \
  --mode target --target "$DS_MODELS/awq-domain-g128-v1" \
  --draft "$DS_MODELS/draft-distilled-v2" --quantization awq
DS_AWQ=experiments/runs/替换为AWQ运行ID
"$DS_PY" scripts/analyze_speculation.py --runs "$DS_TARGET" "$DS_AWQ" \
  --contributions --report artifacts/learning/awq-inference.json
"$DS_PY" -m json.tool "$DS_TARGET/memory-final.json"
"$DS_PY" -m json.tool "$DS_AWQ/memory-final.json"
```

**完成标准**：比较速度、输出长度、规则质量和 `gpu_processes` 进程显存，检查实际量化后端；解释量化允许与FP16有token差异，输出更长造成token/s增加不能单独证明等工作量加速。区分逻辑权重、结束时进程显存、Torch allocated/reserved/peak 与固定KV预算。

结合[AWQ协议](../../docs/awq-protocol.md)、[量化结果](../../docs/awq-results.md)、`scripts/quantize_awq.py`、`reports/s2-awq.json`，串起“校准→导出→加载→评测”；解释W4A16、scale/zero point、group size、通用/领域校准、21代表层局部误差、领域128选型及高精度层保留。明确AutoAWQ提供的能力，记住AWQ×推测历史组合更慢。本轮完成的是加载与对照；重新校准、三产物选型与组合重跑在进阶附录第4节。

## 6. R6：CUDA v1 正确性与性能（M5）

```bash
"$DS_PY" scripts/check_rope_cache.py --stage S5 --benchmark
"$DS_PY" scripts/check_rope_contract.py --stage S5 --variant baseline
compute-sanitizer --tool memcheck --error-exitcode 99 \
  "$DS_PY" scripts/check_rope_cache.py --stage S5 --quick --sanitizer
```

逐条独立运行。`correctness.json`、`invalid-inputs.json`、`rejected.json` 看数值与边界；`timings.json` 包含两方微秒中位数、原始样本和下降比例。编译、检查、warmup、sanitizer 不进入计时。微基准调用已经验证输入的底层入口；不能将公开包装层的同步检查成本当作已计入。

**完成标准**：读 [v1 kernel](../../csrc/rope_cache.cu)与[算子范围](../../docs/rope-cache.md)，手推一个token/head/thread的读写地址，解释NeoX成对旋转、Q/K/V布局、slot互异、stride和FP16舍入；说明独立数值参考、未写槽、非法输入及memcheck分别验证什么。它是独立原型，未接服务，不能把微基准下降比例说成TPOT收益。v2 tile/half2移到进阶附录第5节。

## 7. R7：FA2 与小规模部署对照（M6）

```bash
"$DS_PY" scripts/benchmark_fa2.py --stage S5
```

八形状、独立FP32数值参考、实际kernel和Event计时在同一入口，结果在 `results.json` 的 `median_us`。性能双方是 vLLM FA2 与 PyTorch **flash** SDPA，均为上游能力；FP32数学仅用于正确性，不用于制造速度优势。结合[FA2说明](../../docs/fa2-prefill.md)，解释减少显存读写和中间结果物化的原理，以及短序列固定开销可能掩盖收益。

```bash
cp configs/s5-openloop-smoke-v2.json artifacts/learning/openloop-32.json
for DS_DEPLOY in single replica tp2; do
  "$DS_PY" scripts/benchmark_openloop.py --deployment "$DS_DEPLOY" \
    --protocol artifacts/learning/openloop-32.json --python "$DS_PY" --repeat 1 || break
done
```

脚本自动启动/压测/清理服务；不先启动 `serve_smoke.py`。占用8081/8082端口；每种部署是自然/填充×4/32 req/s四个cell，每cell32条，共128条，热身单列。小样本P99只作练习。

比较 `*-summary.json`，保留 `*-requests.jsonl`、`*-measurement.json`、`trajectories.json`、`ready-gpu.json`和服务日志。同cell输入与到达轨迹一致；双副本和TP2同为两卡、全局maxseq8，单卡只是一卡参考。自动KV容量未强制相同。32 req/s是到达率，不是完成吞吐。

**完成标准**：能解释开环与闭环、到达率与并发/吞吐的区别，找到TTFT/TPOT/E2E/P99、失败与SLO goodput；从 `*-requests.jsonl` 手算一条TPOT，再核对一个cell的P99排序位置与分母。TTFT从实际发送起算，用户E2E与用户首字SLO从计划到达起算；失败/超时和完整结束窗口都要保留。需要脚本辅助复算时用进阶附录第6.1节，不会重新发请求。

读[S5结果](../../docs/s5-results.md)理解两卡比较条件、高负载SLO不满足、填充降质和通信成本。第一轮每cell32条即可，不要求每cell256条×三轮。缺第二张卡时先完成FA2与single，双卡操作记录待完成，不能用历史阅读勾掉。

## 8. R8：把操作整理成面试回答

下面是收尾核验，穿插在前七项中完成即可。**第一轮减少的是重跑量，六条主线的原理、核心实现和结果限制仍需理解。**

| 要做什么 | 最低完成标准 |
|---|---|
| 介绍项目与六线 | 脱稿2–3分钟讲清结构化输入/输出、规则评分、Qwen/vLLM分工和本人参与；每线一张“问题→原理→具体改动→对照→结果→限制”卡，附一个源码入口、一份证据，能回答两个追问 |
| 四组简历数字 | 按下表找到原报告和run来源，自己计算下降比例，说清输入、单位、分母和聚合顺序；无需把所有历史聚合器都重跑 |
| 小型编码 | 本人在 `artifacts/learning/exercises/` 写PyTorch causal attention，比较KV逐步与完整前向；再写简化冷热淘汰或滑窗K控制器，检查正常/边界和复杂度。R6完成CUDA地址手推，R1完成一次参数修改与验证 |
| 基础与广度 | 按最低指南第3节补生成/KV/量化/GPU/指标/训练基础，第6节补量化方法、稀疏、蒸馏/NAS、框架和多卡概念；算法题另练数组/哈希/链表/栈队列/二分/堆/树/排序。这里只要求相应原理广度，不新增一组GPU实验 |

小练习要亲手写，不能用已有benchmark代替；若另改项目源码，先在学习分支提交，再运行要求干净源码的脚本，不绕过检查。

| 简历数字 | 去哪里核对 | 口头必须带的条件 |
|---|---|---|
| TPOT约降18% | [S5结果](../../docs/s5-results.md)、`reports/s5-composition.json`：16.6617→13.6884ms | FP16 Target对蒸馏Draft固定K、同原生APC、三轮；TTFT增加，不归因动态K |
| 进程显存约降56% | [AWQ结果](../../docs/awq-results.md)、`reports/s2-awq.json`：15900→6988MiB | 固定512 KV块、结束时进程采样；不是峰值或权重大小 |
| CUDA约降18%–31% | [S3结果](../../docs/s3-stability.md)、`reports/s3-stability.json`中的六形状数据 | 上游分步对v1、限定FP16布局、Graph/Event；未接服务 |
| TP2 P99约降27%–34% | [S5结果](../../docs/s5-results.md)、`reports/s5-openloop.json`各轮副本/TP2数据 | 同两卡、自然32 req/s、每cell256；计划到达起算，有限样本尾部，SLO仍大量不满足 |

下降比例统一 `(基线－候选)/基线`，不同实验数字不能相加。结合 R7 的逐请求复算，能区分“计算报告中的百分比”和“从原始请求重算指标”；完整历史重聚合命令保留在进阶附录第6.2节，按需使用。

同时读[最终质量](../../reports/s5-final-quality.json)：十种配置各256条、236正确，只说明固定代理任务；模型输出差异和失败不隐去，不证明实车效果或生产稳定P99。若简历保留heap/v2亮点，先读[实现与结果](../../docs/s4-depth-results.md)，不能因其重跑后置而跳过面试解释。

## 每做完一项，留一份短记录

保存到 `artifacts/learning/notes/R编号.md`，不需要复制全部日志：

```text
任务 / 日期 / 本人状态：仅阅读、提示下完成、查文档独立完成、条件缺失
目的与输入：代码SHA、模型、数据、环境、对照条件
实际命令与产物：run目录、报告、trace、关键输出
结果与问题：正确性、指标、实际报错和处理；没有报错就写无
解释与限制：为什么这样比较、源码入口、观察与推测的区别
待补：尚未做过的环节、仍答不清的问题
```

亲手训练/校准尚未完成时，说明“读过历史证据、操作过已有产物”。不将读文档算作亲手开发或复现。新日志和产物在释放机器前按[资产留存](../../docs/storage.md)备份并读回核对。

## 第一轮之后再看什么

[进阶附录](interview-benchmark-advanced.md)保留观察器开销、纯原版vLLM参考、自然业务/heap、原新Draft与训练恢复、三组AWQ/重校准/自动KV/组合、CUDA v2、完整历史复算与多轮复现命令。按薄弱项选择，当前只需从第0节和R1开始。
