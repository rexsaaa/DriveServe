"""Generate S5 tables from reaggregated raw evidence, no manually entered metrics."""
import argparse,json
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--composition',type=Path,required=True);p.add_argument('--openloop',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
c=json.load(open(a.composition));o=json.load(open(a.openloop));lines=['# S5 组合与开环重复实测','',
'本表由scripts/render_s5_results.py从原始记录重聚合报告生成。每列保留独立进程数；三次重复不足以给出生产P99保证。最终test质量另表，不进入开发调参或这些速度表。','',
'## 相同原生APC下的模型与策略','',
'| profile | 独立进程 | 总wave秒 mean±sd | 正确数逐轮 | 平均TTFT ms mean±sd | 平均TPOT ms mean±sd |','|---|---:|---:|---|---:|---:|']
def stat(metric,scale=1):
 mean=metric['mean'];sd=metric['sample_stdev'];return 'n/a' if mean is None else f'{mean*scale:.4f}'+(f' ± {sd*scale:.4f}' if sd is not None else ' (单次)')
for label,row in sorted(c['run_level_statistics'].items()):
 m=row['metrics'];lines.append(f"| {label} | {row['independent_processes']} | {stat(m['sum_wave_s'])} | {m['quality_correct']['values']} | {stat(m['ttft_mean_s'],1000)} | {stat(m['tpot_mean_s'],1000)} |")
lines+=['','总wave秒包括真实引擎提交/调度/生成，不含模型加载/Graph编译/热身。六模型各137请求含128业务与9边界；四policy各128业务、wave8/maxseq4/128KV块，不能直接混比两个工作量。缓存与调度不要求提高自然业务热点数；K控制器有实际维护成本。','',
'## 开环三部署','',
'| 部署 / 负载 / 标称rate | 进程 | req/s mean±sd | SLO goodput/s mean±sd | 质量goodput/s mean±sd | 用户E2E P99秒（各轮） | 正确数逐轮 |','|---|---:|---:|---:|---:|---|---|']
for label,row in sorted(o['run_level_statistics'].items()):
 m=row['metrics'];lines.append(f"| {label} | {row['independent_runs']} | {stat(m['request_per_s'])} | {stat(m['slo_goodput_per_s'])} | {stat(m['quality_goodput_per_s'])} | {[round(x,4) if x is not None else None for x in m['user_e2e_s_p99']['values']]} | {m['quality_correct']['values']} |")
lines+=['','每cell256条，失败/超时/取消留在分母；窗口包含drain。用户E2E及用户首字从计划到达算，发送侧E2E/TTFT与发送滞后另存在JSON报告。自然SLO≤2s/0.5s，填充≤8s/4s，阈值事前固定，不跨不同负载的SLO直接比较goodput。三种部署同到达轨迹、原生APC、Graph/FA2；双副本和TP2同两卡，全局maxseq8。单卡是一卡效率参考，自动KV容量不同。','',
'填充在聊天模板前增加共享background前缀到512/1536token，允许APC复用，且可能降低任务质量；禁止把该压力任务吞吐当真实车载效果。自然业务dev128重复两次，仍是性能开发集。P99逐轮报告，不能池化后假装独立万级请求或删掉慢轮。S3 TP2首轮波动原因仍未知。','']
a.output.write_text('\n'.join(lines))
