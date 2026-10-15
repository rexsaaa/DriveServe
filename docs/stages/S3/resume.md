# S3 六条事实版简历与证据映射

适用版本是S3验证范围；阶段是否验收见 [acceptance](acceptance.md)。这是结构化规则车载决策代理任务，没有实车安全结论。代码、原始run和复现入口均保留，原稿百分比不作为成绩。

| 主线 | 可使用的事实表述 | SHA、run与报告 | 条件与限制 |
|---|---|---|---|
| M1 源码与诊断 | 在固定vLLM V0加入可关闭的请求/调度/KV观察器，关联70,804个GPU kernel的Nsight时间线；用三轮开关对照和逐请求重聚合核验计时 | 3676c86/2779f66及88ed620/e3a133f/ab8f4ce；s2-nsight-engine.json、s3-stability.json；run清单见主表 | 开关总时间差0.259%/0.703%/0.729%包含运行波动，不预设KV主导 |
| M2 缓存与调度 | 接入零引用块冷热保留与长度老化admission，三轮四策略对照中热点保留992tokens复用，短组等待由533.33ms降至组合18.04ms，同时报告长组188.18→474.02ms退化 | 890bb0b/5bcc38d；s3-stability.json；两次Graph生命周期run132749-2d7509b3fc/132852-4c0d791494 | 合成128块池；每次792个不变量快照、32共享块、2取消和1次抢占；不推广整体吞吐/P99 |
| M3 推测与蒸馏 | 实现实际K宽度1–4滑窗控制，完成472条合格教师样本、128步LoRA序列蒸馏与全状态SIGTERM恢复；Graph固定K三次诊断接受率83.8617%→86.8834% | spec_control.py/train_draft.py；s2-training-recovery.json；s3-boundaries-fixed.json，原120019-1735067ddc/新120135-8f2c7fba2a等各3次 | 同137请求新fixed时间14.9691±0.1429s对Target17.1860±0.0277s，但业务TTFT增加；动态K无稳定增量优势；eager旧分歧保留 |
| M4 AWQ | 自行完成两类各16384tokens的AWQ校准、group64/128及21代表层误差分析；领域128独立重复校准13文件逐字节相同，三轮dev均121/128；逻辑权重15.231→5.571GB | s2-awq.json、s3-awq-reproducibility.json、s3-stability.json；重复校准115848-1eee776d86 | AutoAWQ/Marlin为上游；通用128正确118未过120门槛；权重约降63.43%不等于总GPU显存下降 |
| M5 CUDA | 自编FP16 NeoX RoPE+KV append融合算子，完成48数值、16 memcheck、24非法输入及别名修复前后检查；六shape CUDA Event各三独立进程对照 | 72cce3a；修补ba54e8d；s3-stability.json、s3-boundaries.json；133043-fa4030991a/133046-0aa1b3ebba/133051-4bf0dd851e | Q28/KV4/D128独立原型，未接服务；索引别名前探针拦截dispatch，没有实际危险kernel执行 |
| M6 部署分析 | 实测八形状FA2对照torch flash、真实Nsight，以及单卡/双副本/TP2两长度两并发三轮矩阵，2304/2304完成；按两卡预算、质量、波动给条件建议 | 1436607/3d055ae；s3-stability.json；TP2 123752-40b024fa79/125855-5f98fb2303/131900-9ec6aac84b | TP2首轮明显更快且原因未知；长填充dev-030每轮额外错误；每cell64 P99探索，无开环SLO |

完整run ID、源码SHA与artifact哈希见[覆盖](coverage.md)及相应report。各主线原理/实现、正确性/实验、限制/权衡追问见[累计讲解](README.md)，不得只背表格数字。用户尚未复述或接受追问验证，材料交付不等于已独立掌握。
