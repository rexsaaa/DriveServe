# S4 深化实施记录（尚未验收）

进入条件已满足：S3 tag stage-3-validated指向96bde7b，已从GitHub独立fetch核验，reports/s3-tag-readback.json保存对象与commit。S1–S3累计材料仍以[上阶段](../S3/README.md)为准；本页目前是增量记录，S4最终必须改写为从起点到S4的累计讲解。

两项实际代码变更已固定在8728669。`HeapColdHotEvictor`用cold/hot/expiry三堆及generation防旧条目，超过max(64,4×free)重建，保持旧冷热/LRU/tie-break语义；引擎通过显式scan/heap开关接入，默认scan。CUDA增加每token八个head tile，scalar与half2分开，half2用非FMA的独立round-to-nearest乘/加/减；auto阈值32、未对齐小T回退scalar，大T仍用v1。原v1源文件与入口保留，未接服务。

11项边界计划全部完成，reports/s4-boundaries-state.json及s4-boundaries.json实际重聚合通过：28CPU、20000步逐次victim/metadata差分、5000反复更新及排空、12浮点TTL边界，真实allocator scan/heap各4检查；275 CUDA变体/边界检查、三新入口各24非法输入与只读alias正例、99项sanitizer零错误；Graph生命周期scan/heap各792快照/32共享块/2取消/1抢占，16条输出及状态一致。

诊断CPU时间仅作早期观察，不纳入正式统计。三轮计划configs/s4-timing-plan-r1/r2/r3.json每轮8项：完整CPU操作规模曲线、CUDA五方案及native/scheduler/scan cache/both/heap cache/both。每配置三个独立进程，方案顺序轮换，完整请求与内存/维护成本保留。docs/s4-depth-protocol.md规定选择依据和边界；最终test未送模型。此时尚无S4正式性能结论。

聚合入口scripts/analyze_s4_boundaries.py已在11项结果实际执行；scripts/analyze_s4_replication.py已实际重聚合第一轮8进程/20组指标；三轮未齐，不先认定稳定收益。首次计划runner也实际发现了compute-sanitizer间接子run，完整原记录保持。

更新：2026-10-15T14:10:15.334197+08:00。S4首轮8/8完成、无失败，代码05bcac1；reports/s4-timing-r1-state.json与s4-r1-depth.json保留完整8内run及重聚合。六引擎配置每组36条输出/status均相同，heap对scan逐请求cached tokens相同。首轮cache heap总时间略增0.041%、both略降0.103%，不能写稳定服务收益；CPU大池维护更快但内存增加，128块heap操作P99比scan更高，最大操作停顿也保留（本计时没有逐次隔离重建/GC原因）。CUDA小T tile明显快于v1，scalar大T出现退化；half2/auto完整消融保留，先前cutoff32不因单轮结果重调。只有一轮，正式结论等待三轮。

下一步固定提交后运行 `python3 scripts/run_experiment_plan.py --plan configs/s4-timing-plan-r2.json --state artifacts/s4-timing-r2/state.json`，期间保持源码干净，无其他GPU/OSS任务；完成后提交证据再r3。累计讲解和S4验收尚未完成。

更新：2026-10-15T14:20:51.049641+08:00。S4第二轮8/8完成，源码d37aa46，与首轮联合重聚合16进程/20指标组，reports/s4-r12-depth.json。每组36条输出/status仍完全一致，heap对scan逐请求cached tokens相同。两轮cache heap总时间差分别-0.041%/+0.385%下降、both约+0.103%/+0.098%下降；差异很小，不作稳定服务加速。16384块heap单次最大操作11.326/5.643ms，原计时没有逐次标注重建/GC，不武断归因；后续可补独立维护诊断。

下一步固定提交后第三轮：`python3 scripts/run_experiment_plan.py --plan configs/s4-timing-plan-r3.json --state artifacts/s4-timing-r3/state.json`。计划内保持Git干净、两卡不并行其他实验、无OSS传输；三轮后再汇总和S4累计验收。

更新：2026-10-15T14:30:22.907590+08:00。S4三轮全部8/8完成，共24独立进程/20指标组，reports/s4-depth.json与docs/s4-depth-results.md实际重聚合。六引擎配置各轮36条输出/status相同，heap/scan逐请求cached tokens相同。cache heap总时间下降-0.041%/+0.385%/-0.024%，both下降0.103%/0.098%/0.464%；差异小且前者方向不稳定，不主张总体服务提速。16384候选CPU完整操作中位scan约4.84–4.89ms、heap14.81–18.03μs，Python allocation约3.46→8.54MB，最大操作5.64–11.33ms保留；大池重建次数为0，最大均为step0淘汰，不能归因重建。CUDA T1原v1约2.734–2.744μs、half2约1.434–1.448μs；T2048 scalar tiles比v1更慢，完整五组保留，auto阈值32不变。

下一步固定此单元后单独执行scripts/diagnose_heap_maintenance.py，记录_take/_expire/_compact及GC事件，定位陈旧候选清理/到期/重建的实际工作；该诊断时间不进入24进程正式表。随后完成S4累计材料、覆盖、审计与独立GitHub回放，尚未accepted。scripts/verify_s4_release.py目前仅语法检查，未执行，不代表远端验证已通过。
