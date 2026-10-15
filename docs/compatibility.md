# 固定版本与实际支持范围

上游为vLLM0.8.5 / ba41cc90e8ef7f236347b2f1599eec2cbb9e1f0d，torch2.6.0+cu124、transformers4.51.3，宿主driver550.163.01/nvcc12.1。153基础依赖按锁文件在独立环境重建过；训练/AWQ放独立附加层，没有覆盖原推理环境。两RTX4090各报告49140MiB、无NVLink、P2P失败，TP2 custom all-reduce关闭；未测物理24GB实例或实际宿主迁移。

| 路径 | 实际已验证能力 | 未声明支持 |
|---|---|---|
| 原生Target | Qwen2.5-7B-Instruct FP16，单卡/双副本/TP2，V0、FA2、CUDA Graph | 任意模型/后端或生产SLO |
| 冷热/长度策略 | V0非chunked、single-step FCFS、n=1，原生block refs/hash/table由上游保持；Graph/4 B1 | 自研策略与TP/beam/swap/chunked组合；CPU/GPU分层交换 |
| 推测控制 | 单卡FP16 Target+对齐1.5B Draft，PyTorch seeded sampler修复；实际K1–4接口，greedy轨迹K2/3/4；eager与Graph分别记录 | 通用逐token等同、任意采样器/TP/beam组合、未验证的其他模型/采样器组合（S5量化×spec范围见下文） |
| 实际蒸馏 | 472条合格教师train、128optimizer步LoRA序列蒸馏、完整训练恢复及独立合并Draft | logit蒸馏、大规模真实驾驶泛化 |
| 自主AWQ | domain/general128及domain64，实际原生awq/Graph；domain128还测awq_marlin；重校准逐字节相同 | BF16激活冒充此AWQ后端；量化严格保持原FP16分布 |
| 独立CUDA | FP16 NeoX完整D128/Q28/KV4，packed QKV，FA cache block16/32，唯一有效slot | 服务接入、端到端TPOT收益、其他dtype/头数/布局/所有特殊bit pattern |
| FA2 | 实际vLLM FA2 causal GQA与torch flash，8形状、FP32参考、kernel trace | 自研Attention或完整模型数值等价 |
| CUDA Graph | V0引擎/推测及独立算子Graph实跑，配置与日志保留 | 未验证torch.compile或所有动态形状 |

Target/Draft tokenizer文件与template、BOS/EOS相同，但原始配置词表151936/152064不匹配。先零填128行对齐且保留原权重，之后才有真正的LoRA蒸馏；零填对齐本身不算训练。Original/Aligned/Trained各有独立provenance与资产，不能混称。

M1调用链从OpenAI serving→MQ/异步分支→LLMEngine→Scheduler→SelfAttnBlockSpaceManager/PrefixCachingBlockAllocator→ModelRunner→Qwen2Attention→RoPE/FA2→output；直接同步实验不经过HTTP/MQ。完整文件函数与真实事件见[引擎诊断](engine-diagnostics.md)，不以预检替代运行证据。

Stage tag与原始报告是时间截面。S2 eager adaptive存在136/137序列一致的边界，S3 Graph新样本的137/137不删旧差异。TP2长填充dev-030有同前缀近似/并列诊断，依旧保留规则错误，不能称质量等价替换。量化通用128低于dev门槛，且AWQ与FP16输出长度不同。

默认保留FP16 Target/原生策略；已验证优化作为独立profile。范围以[进度](progress.md)、[覆盖矩阵](coverage.md)及各阶段验收为准；不得把仍在计划中的组合或深化标成支持。迁移后先核对驱动/拓扑/依赖、重建overlay/CUDA扩展，再重测受影响路径；旧性能不能直接作为新卡的baseline。

S5已完成原生APC下FP16/AWQ×fixed/adaptive、cache×scheduler、最终test与GPU回归；具体组合、默认开关和禁止外推范围见[最终兼容矩阵](s5-compatibility.md)。最终test十组各236/256，AWQ×spec速度负收益，独立CUDA仍未接服务。
