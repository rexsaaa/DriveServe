# S2 运行时 K 与蒸馏实施记录

当前为实现/待验证，不是M3验收。固定vLLM0.8.5/ba41cc90、Qwen2.5-7B-Instruct Target和词表对齐的1.5B Draft；零行扩展不是训练，原始权重与来源保留。

`spec_control.py` 在每个decode批次、worker广播之前克隆ExecuteModelRequest并选择实际K。scheduler仍按最大4预留；KV不会随实际K变小而自动缩减。初始K=2，最近8个有提议批次的连续接受token/实际提议token比率低于0.45减1、高于0.8加1，范围1–4，至少保持8个观察批次；中间区间不变。非法计数回退最大固定K；Prefill与上游no-spec仍保留。当前仅单GPU V0、eager、n=1、非chunked、draft_model。

补丁只有两处调用：`SpecDecodeWorker.execute_model` 在读取/广播K之前决定本轮实际长度；`_run_speculative_decoding_step` 在原生_verify_tokens之后读取结果。提议和验证tensor宽度须分别等于K与K+1，trace记录实际shape。原生target scoring、rejection sampler、bonus同步、回滚、engine EOS/长度结束处理未替换。

连续接受统计依据原生输出 `[接受的Draft前缀, replacement或bonus, -1...]`，有效token数量减1；原生metrics的accepted.sum可能包含首个拒绝后的独立接受判定，不作项目接受率。统计位置在engine截断前，所以EOS位置、剩余长度和越界验证token数量分别记录，不能把所有verifier接受都称为用户最终输出。同步GPU计数与序列化成本计入adaptive耗时，不隐藏在性能对照外。

验证入口：`benchmark_speculation.py --mode target|fixed|adaptive [--trace]`，同开发32条+长输出4条+长度预算1/2/3/5+context临界1条。自然EOS与强制长度分开。Target/固定K/自适应K均关闭APC、同KV块数/eager；Draft增加自身权重/KV，总显存另报。greedy比较token；随机采样不要求逐token同seed一致，用独立已知分布的原生CUDA拒绝采样检查与实模型运行共同约束。`check_rejection_distribution.py` 各K用30000样本检验已知target categorical分布，判定阈值事前固定。

训练工作尚未发生：下一步冻结独立用途数据、教师输出与过滤、LoRA序列级蒸馏配方、完整优化器/调度器/RNG checkpoint恢复，然后将训练导出加载同一路径并分离训练与K控制贡献。不得以控制器通过替代蒸馏要求。
