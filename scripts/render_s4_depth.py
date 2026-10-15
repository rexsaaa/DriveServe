"""Render S4 ablation and cost tables exclusively from the verified report."""
import argparse,json
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--report',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
r=json.load(open(a.report));g=r['run_level_statistics'];n=len(r['state_evidence'])
lines=['# S4 深化独立重复与消融','',f'来源 `{a.report}`，{n}轮、{r["independent_inner_runs"]}独立进程。'+('未满3轮，仅临时观察。' if n<3 else '表中均值±样本标准差以进程为独立单位；每run原值和范围在JSON。'),'','两个专题保持原默认scan与CUDA v1入口。策略使用Graph/4、128块池、36条合成barrier请求；CPU操作与CUDA Event是分别计量的专题，不相加为服务收益。','']
def val(k,m,scale=1):
 s=g[k]['metrics'][m];v=f'{s["mean"]*scale:.4f}'
 return v+(f' ± {s["sample_stdev"]*scale:.4f}' if s['sample_stdev'] is not None else '')
def table(headers,rows):
 lines.append('| '+' | '.join(headers)+' |');lines.append('|'+'|'.join(['---']*len(headers))+'|');lines.extend('| '+' | '.join(map(str,row))+' |' for row in rows);lines.append('')
lines+=['## 引擎：同策略扫描与堆索引','']
labels=['policy-native','policy-scheduler','policy-cache-scan','policy-cache-heap','policy-both-scan','policy-both-heap']
table(['配置','总时间s','输出token/s','短组等待ms','长组等待ms','热点复用tokens'],[[k]+[val(k,m) for m in ['elapsed_s','output_tokens_per_s','short_wait_ms_mean','long_wait_ms_mean','hot_probe_cached_tokens']] for k in labels])
table(['重复','候选/scan基线','总时间下降','吞吐变化','逐请求cached tokens一致'],[[x['repeat'],x['candidate'],f"{100*x['elapsed_reduction']:.3f}%",f"{100*x['throughput_gain']:.3f}%",x['same_cached_tokens_each_request']] for x in r['paired_policy_comparisons']])
lines+=['配对时间比仍包含独立run间的波动；短组改善须同时看长组代价。小池服务总时间不由淘汰扫描独占，CPU曲线改善不自动变为服务同幅收益。输出/状态核对完整保存在policy_output_comparisons。','', '## CPU策略：完整操作与索引成本','', '每规模每run256轮evict+add+两次有效reuse+touch+remove+readd，init与tracemalloc不在操作计时中。每run内中位数/P99是相关操作样本的描述；不是服务P99。Python allocation在初始化后计量，不是完整进程RSS。','']
labels=[f'heap-cpu-{c}-{v}' for c in [128,1024,8192,16384] for v in ['scan','heap']]
table(['规模/方案','完整操作中位μs','完整操作P99 μs','最大操作μs','256轮总ms','Python驻留KiB','初始化峰值KiB'],[[k,val(k,'median_all_ns',.001),val(k,'p99_all_ns',.001),val(k,'max_all_ns',.001),val(k,'sum_all_ns',1e-6),val(k,'resident_traced_bytes',1/1024),val(k,'initialization_peak_traced_bytes',1/1024)] for k in labels])
lines+=['最大操作时间可揭示被256样本P99略过的偶发重建停顿；不能只讲中位数。初始化耗时在JSON以initialization_ns_with_tracemalloc保留，包含allocation插桩成本，不能冒充无插桩初始化时间。','']
lines+=['堆将选择成本移到add/touch/reuse以及过期和重建；这里完整操作包含这些维护，不只测evict。bounded-index.json保留5000次小池更新的条目界限/重建轨迹，differential.json保存20000步逐次metadata与victim一致。额外索引内存必须与耗时一起看。','', '## CUDA：保留v1、tile、half2与固定分派消融','', '每run每shape每方案20个Event样本，每张Graph100操作；以下为run内中位数的跨run统计，单位μs。公开入口的CPU同步校验与host dispatch未计入。五种方案均完成等价RoPE+KV写入，支持范围仍FP16 NeoX Q28/KV4 D128。','']
labels=[f'rope-depth-tokens{t}' for t in [1,8,32,128,512,2048]]
table(['T','上游分步','v1一token一CTA','scalar tiles','half2 tiles','auto≤32 tiles'],[[k]+[val(k,m) for m in ['upstream_separate','project_v1','tiled_scalar','tiled_half2','dispatch']] for k in labels])
lines+=['auto阈值32在正式比较前冻结，未声称全局最优；小T若指针/stride不满足half2条件回退scalar，大T使用v1。保留全部分块/向量化结果，包括可能退化的形状；275项完整检查与99项memcheck含多种方案及边界，并非275个独立进程。','', '## 复算与结论边界','', '`python3 scripts/analyze_s4_replication.py --states <各轮state> --report <JSON>` 校验资产/source/config/environment并重算逐请求与Event/CPU统计；本脚本只从该JSON生成表。', '', 'S4接受仍需要累计讲解、覆盖矩阵、成本/负结果决策及独立读回；本表不自动表示验收。最终test未参与本阶段，已有M1/M3/M4/M6证据与限制保持。CUDA独立算子未接服务；不作生产SLO、物理24GB或实车结论。','']
a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text('\n'.join(lines))
