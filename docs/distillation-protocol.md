# S2 蒸馏、校准与冻结数据协议

> S3更新：训练数据隔离与固定K贡献分离已完成，见[独立重复](s3-stability.md)、[边界报告](../reports/s3-boundaries.json)和[S3累计讲解](stages/S3/README.md)。下文保留S2实现与初测来源，不把旧单次结果混成S3计时。

前半部分保留已冻结的事前设计，后半部分记录实际训练与产物。目标模型、任务schema和评分规则保持既有proxy-v1；不以教师正确性替代独立规则真值。

数据：新seed2026101501，固定train512、calibration256、dev128、final-test256，每场景组4变体；组、exact scene content跨split及对旧128fixture无重复。分别存文件和manifest，记录用途、来源、hash、group数、标签分布。规则/系统指令共享，所以不声称跨模板或真实道路泛化。final-test在S5之前不送模型、不参与训练/校准/调参。

教师：冻结7B target FP16，greedy、seed37、max128、自然EOS。只生成train/dev，逐条保存原prompt token、输出token/text、finish、独立oracle评分和过滤原因；训练仅采用JSON有效且规则全字段正确的train教师输出。dev仅计算验证损失/质量，不参与梯度。输出已固定后不会依赖再次生成。

训练：对已词表对齐1.5B加LoRA，拟采用rank8、alpha16、dropout0，Q/K/V/O与MLP线性层；仅答案token交叉熵，prompt labels=-100，包含assistant结束token。BF16、AdamW、seed固定、固定样本顺序，有限训练预算，记录batch/accumulation与实际有效token；不训练Target。新增peft/accelerate以附加依赖目录加载，不覆盖原锁定torch/vLLM环境。冻结依赖版本、wheel hash、recipe后运行。

恢复：checkpoint需同时保存adapter、optimizer、scheduler、步数/epoch/数据cursor、Python/Torch CPU/CUDA RNG、base/data/recipe hash。写新临时目录、完整校验、原子改名后才更新latest指针，不覆盖唯一有效副本。每8optimizer步保存，训练日志每步落盘；实测一次SIGTERM后从有效checkpoint继续。另用同recipe/seed的连续短基准对照续训到相同step，比较参数、loss与学习率，不能把重新加载权重当完整续训。

导出与比较：保留adapter和完整checkpoint并OSS读回，导出独立合并权重（约3GB）与provenance，不覆盖原Draft。实际vLLM加载训练前固定K、训练后固定K，以及固定训练后Draft的adaptiveK，使用同开发轨迹，记录Target greedy一致性/自然EOS、正确率、连续接受率与运行时间。若无收益也保留，不跳过真实训练。

AWQ将使用calibration256；通用语料另核许可、固定revision和同token预算。后续已按独立AWQ协议完成真实校准，实际证据见awq-results.md，本训练协议不充当M4证据。

实际冻结与教师记录：fb76fab、data/frozen-v1/manifest.json；教师run20261015T020536+0800-c8739002bc生成640条，训练472条合格/40条排除（独立规则不匹配），dev121/128正确。训练recipe固定128optimizer步、microbatch2×accum4、lr2e-4/warmup8/线性衰减、clip1、weight_decay0、seed3701、固定一次置乱循环；checkpoint每8步和SIGTERM后当前optimizer步完成时保存。对照采用同128步调度的前16步，SIGTERM在第8步checkpoint可见后发送；不是另建16步学习率调度。有效dev教师子集只做验证loss，完整dev业务质量另由vLLM评测。

## 实际训练与贡献结果

128optimizer步完成，消费1024条样本（472条固定置乱循环），472条合格教师构成训练集合。最终验证仅对121条合格dev教师计算答案损失0.00816725；此loss不能替代完整dev规则质量。训练峰值allocated4,473,867,264bytes，reserved5,607,784,448bytes，属于当前48GB物理卡上的配置实测，不是24GB机器实证。SIGTERM第8步checkpoint可见后发送，第9步保存退出，续至16步与连续参考的adapter/optimizer/scheduler/RNG/每步loss-LR-样本均bitwise相同。

训练后独立导出约3.1GB、tokenizer复制原验证文件，v2与v1合并权重hash完全相同；原Draft未覆盖。完整checkpoint、adapter、派生模型、教师与依赖都有OSS完整读回收据。恢复训练需base+teacher+layer+state.pt，非仅加载adapter。详见s2-training-recovery.json、s2-training-128.json、s2-trained-assets-oss.json。

同一frozen-dev128+9边界请求：Target与原Draft固定K、新Draft固定K均137/137输出相同，规则正确均121/128；新Draft动态K136/137相同，差异是long-2第124token（此前同前缀FP16近似/并列位置），新run未单独采集该位置logprob，不能声称本组严格一致。固定K连续接受率由2329/2776=83.8977%变为2326/2676=86.9208%，是+3.0231个百分点；新Draft动态K为88.6066%，其分母也变了，不能把全部变化归因于训练。所有接受计数在EOS/长度截断之前，bonus不计接受分子。

带trace的单次总吞吐Target168.88、原fixed157.10、新fixed163.88、新adaptive167.50输出token/s；阶段内有导出/依赖安装/OSS I/O活动，未做独立重复，所以只作初测，不宣称稳定加速或等预算最终性能。当前保留Target默认，trained Draft作为已验证实验产物。完整分组接受率、TTFT及观测TPOT见reports/s2-distillation.json；TPOT用引擎首次非空输出至完成的时间除后续token数，不是每个spec burst内的ITL。
