# S3 工程验证进行中

当前可面试完整版本仍为stage-2-minimum（5dc0a8e），S3尚未验收。本阶段保留全部六线基础，以S2累计讲解为基础完成独立重复、边界与可靠性；接受后再固化完整S3累计材料。

- CUDA公开入口20类非法dtype/layout/indices/alias全部拒绝且未改存储；负slot不写cache，run115852-8c22e153b0。不是新kernel性能优化。
- Graph Target/原fixed/新fixed/新adaptive各137完成，三种推测与Target均137/137 token相同，全部dev121/128；实际K2/3/4、5次切换，见s3-graph-boundaries.json。S2 eager的近似/并列分歧保留，不能用Graph新样本删除历史限制。诊断时另一卡AWQ校准，不进入计时主表。
- domain128重新完整校准（115848-1eee776d86）与S2的13导出文件及21项局部误差全部精确相同。相同权重复用已经完整回读的OSS对象，新的provenance和原始层记录进Git，不上传重复收费副本；见s3-awq-reproducibility.json。
- 三组原生AWQ及Marlin128真实Graph推理各137完成。通用118/128低于预定质量门槛120；领域64/128、Marlin128均121。原生128与Marlin在long-1合成输出有差异，不宣称严格全序列等同，后台校准下时间不作正式性能。
- TP2的dev-030长填充质量退化已定位到同前缀第4个输出token：单卡stop(9495)比pro(776) logprob高0.03125；TP2二者并列，选择776。另一个共同前缀Prefill探针中单卡差0.015625、TP2仍并列。不能将全部原因单独归给NCCL，也不能因此忽略真实规则错误；见s3-tp2-quality-diagnostic.json。
- 真实HTTP未知model=404、负max_tokens=400、超过context=400均记录失败，随后有效请求成功。计划runner真实失败/整单元重试/再次跳过已完成的CPU演练通过；不是自动开机或训练续训证明。

事前协议为docs/s3-validation-protocol.md，三轮各18个独立任务，source在每轮冻结；GPU无其他实验/备份后串行运行。第一轮18任务已完成并从实际原始数据聚合39指标组，报告s3-r1-stability.json，表格见../../s3-stability.md。聚合器两处API接入问题已修复并通过真实数据回放；28项CPU检查通过。第二轮也18/18完成，两轮36进程在s3-r12-stability.json重聚合，三部署累计1536/1536。动态K相对trained fixed方向发生变化，不能宣称稳定增量加速。第三轮及Graph生命周期、memcheck、数据隔离等尚待完成；新发现索引/可写存储alias边界拟先用截获dispatch探针复现，未发危险kernel。最终test未送模型。
