# S2 运行时 K 与蒸馏实施记录

> S3更新：Graph编译模式、固定K和随机边界已完成，见[独立重复](s3-stability.md)、[边界报告](../reports/s3-boundaries.json)和[S3累计讲解](stages/S3/README.md)。下文保留S2实现与初测来源，不把旧单次结果混成S3计时。

当前为实现/待验证，不是M3验收。固定vLLM0.8.5/ba41cc90、Qwen2.5-7B-Instruct Target和词表对齐的1.5B Draft；零行扩展不是训练，原始权重与来源保留。

`spec_control.py` 在每个decode批次、worker广播之前克隆ExecuteModelRequest并选择实际K。scheduler仍按最大4预留；KV不会随实际K变小而自动缩减。初始K=2，最近8个有提议批次的连续接受token/实际提议token比率低于0.45减1、高于0.8加1，范围1–4，至少保持8个观察批次；中间区间不变。非法计数回退最大固定K；Prefill与上游no-spec仍保留。当前仅单GPU V0、eager、n=1、非chunked、draft_model。

补丁只有两处调用：`SpecDecodeWorker.execute_model` 在读取/广播K之前决定本轮实际长度；`_run_speculative_decoding_step` 在原生_verify_tokens之后读取结果。提议和验证tensor宽度须分别等于K与K+1，trace记录实际shape。原生target scoring、rejection sampler、bonus同步、回滚、engine EOS/长度结束处理未替换。

连续接受统计依据原生输出 `[接受的Draft前缀, replacement或bonus, -1...]`，有效token数量减1；原生metrics的accepted.sum可能包含首个拒绝后的独立接受判定，不作项目接受率。统计位置在engine截断前，所以EOS位置、剩余长度和越界验证token数量分别记录，不能把所有verifier接受都称为用户最终输出。同步GPU计数与序列化成本计入adaptive耗时，不隐藏在性能对照外。

验证入口：`benchmark_speculation.py --mode target|fixed|adaptive [--trace]`，同开发32条+长输出4条+长度预算1/2/3/5+context临界1条。自然EOS与强制长度分开。Target/固定K/自适应K均关闭APC、同KV块数/eager；Draft增加自身权重/KV，总显存另报。greedy比较token；随机采样不要求逐token同seed一致，用独立已知分布的原生CUDA拒绝采样检查与实模型运行共同约束。`check_rejection_distribution.py` 各K用30000样本检验已知target categorical分布，判定阈值事前固定。

训练工作尚未发生：下一步冻结独立用途数据、教师输出与过滤、LoRA序列级蒸馏配方、完整优化器/调度器/RNG checkpoint恢复，然后将训练导出加载同一路径并分离训练与K控制贡献。不得以控制器通过替代蒸馏要求。


## 首次真实运行与动态分母修复

代码9f6a7df：Target run `20261015T014027+0800-14964e2ce4`、固定K=4 run `20261015T014122+0800-c9a9cd6328` 各41条成功，全部输出token一致；32条业务fixture均31条规则正确。固定trace实际提议/验证宽度4/5，记录了拒绝、EOS及context无提议回退。原生CUDA已知分布run `20261015T014009+0800-69d19c30ee` 4种K×30000样本频率误差均<0.015；K4的原生非因果接受54094、连续接受23807，不能混用。

自适应首次run `20261015T014225+0800-a8ce952cbd` 在长输出波失败。实际K已从2增至4，step65从4降至3；原生AsyncMetricsCollector假设整个历史只有当前K，执行 `draft_tokens % k == 0` 断言。完整失败轨迹和外层log保留，这不是目标验证器失败，但该run不能计为成功成绩。

spec-v2只在adaptive模式关闭不适用的原生固定K指标采集器，并由已有真实proposal/verification输出计算项目指标：分母为累计实际提议token，系统最大可能输出为“提议token+有提议的sequence次数”，而非累计提议数/当前K。固定模式仍走原采集器；没有伪造Prometheus固定K计数。trace与controller-summary保存K直方图、接受/提议/实际验证输出和分母，EOS后裁剪范围仍单列。回归需重放同一41条、再做无trace计时与随机采样。


## 修复后的实机差异（尚未通过M3正确性）

f821577的adaptive回归 `20261015T014532+0800-d17b7f037a` 完成41条，真实K为2→3→4→3，提议/验证宽度同步改变。累计连续接受823/实际提议1144=71.9406%，不含replacement/bonus，仍是engine截断前口径。Trace开/关两组均只有39/41条与普通greedy相同；long-0在第92个token开始分歧，long-2在第125个token开始分歧。32业务、4长度预算和1context边界输出相同。不得删除这两条或仅用业务一致冒称全部greedy等价。

temperature0.7的17条输入（8业务+其余边界/长输出）三模式均完成，但Target业务8/8正确，固定K为0/8，自适应为2/8，多条无效JSON。run为20261015T014937+0800-0662dd71e8、20261015T015030+0800-8e9c7891e1、20261015T015141+0800-5b6518d751。不能将这一大幅退化仅解释为不同随机种子序列，原生采样器12万已知分布样本通过也不能替代实际模型集成正确性。

新增诊断：`--logprobs 5` 保存target top5，用于解释首次greedy分歧；`--upstream` 跑未改wheel固定K；`--unseeded`保留engine种子但不设逐请求generator；`--batch-expansion`启用上游替代scorer；`--quality-only --limit 8`只作定位子集，不替代完整41条验收。先固定此诊断代码后运行，不先把假设写成原因。初步原始报告 reports/s2-spec-initial.json，M3仍未通过。

## 随机采样定位与FP16分歧（2026-10-15）

原wheel固定K在8条业务温度0.7中0正确，与项目固定K输出token完全相同；unseeded 8/8，原生batch-expansion 8/8。根因候选是sampler._multinomial把每请求随机行数写成len(seq_ids)，而MQA每请求实际有K+1个sample_indices，torch.empty_like后面的行未初始化。v3将stride改为len(sample_indices)*num_samples，并检查总行数；只针对已选择的PyTorch sampler，FlashInfer明确关闭。另按过滤后的spec_indices映射拒绝采样generator，避免非spec行混入时错位。最小CUDA哨兵/已知分布与真实模型复测完成后才能记为修复验证。

对greedy 41条，同前缀top5见s2-spec-top5.json：fixedK3是40/41，adaptive39/41；long-0位置91，单步token198与320完全并列，K3/动态验证320领先0.015625；long-2位置124，单步151644领先106439 0.03125，动态验证两者并列，argmax按更小token ID选择106439。rank字段用topk排序并列，不能用rank=2否定其同为最大logprob。两处有计算形状下近似/并列logits的直接证据；第一处固定K3也重现，第二处来自ignore_eos后的特殊token延续。保留全部样本，不删除分歧，不把小浮点差异夸大为严格相同序列。
