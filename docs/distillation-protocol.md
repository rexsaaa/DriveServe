# S2 蒸馏、校准与冻结数据协议

这是下一实施单元的预先设计，训练与数据文件生成发生后才写实际run/产物。目标模型、任务schema和评分规则保持既有proxy-v1；不以教师正确性替代独立规则真值。

数据：新seed2026101501，固定train512、calibration256、dev128、final-test256，每场景组4变体；组、exact scene content跨split及对旧128fixture无重复。分别存文件和manifest，记录用途、来源、hash、group数、标签分布。规则/系统指令共享，所以不声称跨模板或真实道路泛化。final-test在S5之前不送模型、不参与训练/校准/调参。

教师：冻结7B target FP16，greedy、seed37、max128、自然EOS。只生成train/dev，逐条保存原prompt token、输出token/text、finish、独立oracle评分和过滤原因；训练仅采用JSON有效且规则全字段正确的train教师输出。dev仅计算验证损失/质量，不参与梯度。输出已固定后不会依赖再次生成。

训练：对已词表对齐1.5B加LoRA，拟采用rank8、alpha16、dropout0，Q/K/V/O与MLP线性层；仅答案token交叉熵，prompt labels=-100，包含assistant结束token。BF16、AdamW、seed固定、固定样本顺序，有限训练预算，记录batch/accumulation与实际有效token；不训练Target。新增peft/accelerate以附加依赖目录加载，不覆盖原锁定torch/vLLM环境。冻结依赖版本、wheel hash、recipe后运行。

恢复：checkpoint需同时保存adapter、optimizer、scheduler、步数/epoch/数据cursor、Python/Torch CPU/CUDA RNG、base/data/recipe hash。写新临时目录、完整校验、原子改名后才更新latest指针，不覆盖唯一有效副本。每8optimizer步保存，训练日志每步落盘；实测一次SIGTERM后从有效checkpoint继续。另用同recipe/seed的连续短基准对照续训到相同step，比较参数、loss与学习率，不能把重新加载权重当完整续训。

导出与比较：保留adapter和完整checkpoint并OSS读回，导出独立合并权重（约3GB）与provenance，不覆盖原Draft。实际vLLM加载训练前固定K、训练后固定K，以及固定训练后Draft的adaptiveK，使用同开发轨迹，记录Target greedy一致性/自然EOS、正确率、连续接受率与运行时间。若无收益也保留，不跳过真实训练。

AWQ将使用calibration256；通用语料另核许可、固定revision和同token预算。当前未安装autoawq，也未做校准，不把本训练设计算成M4完成。

实际冻结与教师记录：fb76fab、data/frozen-v1/manifest.json；教师run20261015T020536+0800-c8739002bc生成640条，训练472条合格/40条排除（独立规则不匹配），dev121/128正确。训练recipe固定128optimizer步、microbatch2×accum4、lr2e-4/warmup8/线性衰减、clip1、weight_decay0、seed3701、固定一次置乱循环；checkpoint每8步和SIGTERM后当前optimizer步完成时保存。对照采用同128步调度的前16步，SIGTERM在第8步checkpoint可见后发送；不是另建16步学习率调度。有效dev教师子集只做验证loss，完整dev业务质量另由vLLM评测。
