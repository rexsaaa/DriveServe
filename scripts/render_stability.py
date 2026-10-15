"""Render descriptive S3 tables from the verified replication report."""
import argparse,json
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--report',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
r=json.load(open(a.report));groups=r['run_level_statistics'];n=len(r['rounds'])
lines=['# S3 独立重复结果', '',f'来源：`{a.report}`；{n}轮、{r["independent_inner_runs"]}个独立引擎/算子进程、{len(groups)}组指标。'+('目前为单轮临时结果，不构成稳定收益结论。' if n<3 else '表内均为run级均值±样本标准差，原始逐run值与范围保存在JSON。'),'',
'每轮先初始化、Graph捕获和热身，再开始计时；无其他训练、校准或OSS传输。相同硬件、执行源码指纹、比较配置和输入hash由聚合器核验。输出token数变化时同时看请求吞吐、总时间和质量。', '',
'第一轮未记录各任务的温度/功耗快照；第二轮起补任务前后状态，仍不构成连续遥测。没有改变功耗上限或锁频。该限制与三轮运行波动一起保留。', '']
def value(label,key,scale=1):
 s=groups[label]['metrics'][key];v=f'{s["mean"]*scale:.4f}'
 if s['sample_stdev'] is not None:v+=f' ± {s["sample_stdev"]*scale:.4f}'
 return v
def table(headers,rows):
 lines.append('| '+' | '.join(headers)+' |');lines.append('|'+'|'.join(['---']*len(headers))+'|')
 lines.extend('| '+' | '.join(map(str,row))+' |' for row in rows);lines.append('')
lines+=['## M1/M2：Graph/4 原生 B1 与策略','', '36条合成请求/配置/轮。短长分组以prompt512为界；热点复用为两条probe的实际cached token之和。trace是诊断，不能当无观察器默认。','']
labels=[k for k in groups if k.startswith('policy-')]
table(['配置','总时间s','输出token/s','短组等待ms','长组等待ms','热点cached tokens'],[[k]+[value(k,x) for x in ['elapsed_s','output_tokens_per_s','short_wait_ms_mean','long_wait_ms_mean','hot_probe_cached_tokens']] for k in labels])
lines+=['观察器开关的配对总时间差（包含运行波动，不是严格因果开销）：'+', '.join(f'r{x["repeat"]}={100*x["relative_observed_difference"]:.3f}%' for x in r['observer_overhead'])+'。','',
'冷热缓存保留热点不等于整体吞吐必然增加；长度admission使短组更早，但长组退化。维护成本的final-scenario计数与trace诊断应分开看。','',
'## M3/M4：推测、训练与量化','', '每配置每轮137请求=128开发业务+9边界；固定512 KV块（8192token槽）。接受率在EOS/长度截断前计连续接受且排除bonus。TPOT是引擎输出观测平均间隔，不是逐token ITL。','']
labels=[k for k in groups if k.startswith(('spec-','awq-'))]
table(['配置','总时间s','请求/s','输出token数','业务正确/128','业务TTFT ms','业务观测TPOT ms'],[[k]+[value(k,x) for x in ['elapsed_s','request_per_s','output_tokens','quality_correct','quality_mean_ttft_ms','quality_mean_observed_tpot_ms']] for k in labels])
lines+=['质量门槛是完整dev128完成且JSON有效，正确数至少同模式FP16少1条；本组最低120。通用128为118，不通过。领域128/64与Marlin达到121；不代表统计非劣效或驾驶安全。领域128仍按事前校准选择规则保留，FP16仍是发布默认。','',
'原/新fixed、新adaptive均应逐轮核对137条token；量化与FP16的输出差异保留在inference_comparisons，不称量化严格等价。Marlin是上游后端，不是个人CUDA贡献。','',
'## M5：独立CUDA算子','', '每轮48正确性用例，6计时形状；每个shape/方案20个Event样本，每张Graph100次操作。以下是各进程中位数的跨run统计；编译/分配/重置在计时外。','']
labels=[k for k in groups if k.startswith('rope-')]
table(['形状','上游分步μs','项目融合μs'],[[k,value(k,'upstream_separate'),value(k,'project_fused')] for k in labels])
lines+=['仅FP16 NeoX Q28/KV4 D128，仍为独立算子；没有服务接入或端到端TPOT收益。','', '## M6：FA2与部署','', 'FA2实际路径对照torch原生flash，均做FP32数值参考。8形状/轮；μs同样以run内中位数为独立统计单位。','']
labels=[k for k in groups if k.startswith('fa2-')]
table(['形状','vLLM FA2 μs','Torch flash μs'],[[k,value(k,'vllm_fa2'),value(k,'torch_flash_sdpa')] for k in labels])
lines+=['HTTP为FP16/Graph/V0，APC与chunked关闭，prompt512/1536×并发1/8，每cell64请求。双副本和TP2均两张卡，每卡0.45总显存预算、全局maxseq8；副本固定轮询。单卡是单GPU效率参考。','']
labels=[k for k in groups if k.startswith('deployment-')]
table(['配置','请求/s','每GPU输出token/s','TTFT P99 ms','E2E P99 ms','成功/64','正确/64'],[[k,value(k,'request_per_s'),value(k,'per_gpu_output_token_per_s'),value(k,'ttft_s_p99',1000),value(k,'e2e_s_p99',1000),value(k,'success'),value(k,'quality_correct')] for k in labels])
lines+=['以上P99来自每run每cell64个成功请求的nearest-rank，是探索性尾部观察；没有开环到达率，不能当排队SLO或生产P99。失败/超时在JSON保留为全部尝试的分母。合成长填充显著降质，TP2的dev-030额外差异有同前缀logprob诊断，不能因数值并列而删除错误。', '',
'## 复算与限制','', '先运行 `scripts/analyze_replication.py --states <各轮保存state.json> --report <结果.json>`，再用本脚本从该JSON生成表格。聚合器校验run资产hash、重新评分、重新计算逐请求摘要和Event中位数。', '',
'三个进程重复不代表三个独立硬件环境。业务为自建规则代理任务，模板跨split共享，最终test尚未用于本报告。S3验收还需独立边界检查、累计材料、留存与读回；本表不自动代表阶段完成。','']
a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text('\n'.join(lines))
