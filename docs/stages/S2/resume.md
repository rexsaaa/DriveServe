# S2 六条事实版简历与证据映射

以下只覆盖当前已实测范围；原稿15%/18%/68%/55%/20%占位不直接使用。项目是规则车载决策代理任务，不是实车系统。

| 主题 | 可使用的事实表述 | 实现/实验SHA与证据 | 不能推出 |
|---|---|---|---|
| 源码与诊断 | 在固定vLLM V0实现可关闭运行时观察器，关联请求调度、KV生命周期与Nsight的70,804个GPU kernel，分析排队、前缀复用与Prefill/Decode成本 | 3676c86/2779f66；s2-nsight-engine.json；234421-7a0f81e8d0/235030-0698208fe6 | 不预设KV主导，不把host时间当kernel时间 |
| 缓存与调度 | 接入零引用块冷热保留及长度老化admission，完成四策略B1对照、288条输出核对与两次各792个生命周期检查，报告短长请求取舍 | 890bb0b/5bcc38d；s2-policies-b1.json；012606-ce5b9d7e98等 | 未证明稳定整体吞吐或P99改善 |
| 推测与蒸馏 | 实现实际候选宽度1–4的滑窗控制，完成472条教师样本、128步LoRA序列蒸馏和全状态中断恢复，固定K初测接受率83.90%→86.92% | spec_control.py、train_draft.py；s2-spec-v3-validation.json、s2-training-recovery.json、s2-distillation.json；022049-74a7f6e583 | 初测未超过Target吞吐，动态仍有FP16序列分歧；非logit蒸馏 |
| AWQ | 以两类各16384tokens校准导出W4A16，比较group64/128和21个代表线性层失真；领域128在dev121/128保持基线正确数，权重逻辑字节减少63.43% | 022410-8f072791c4、111741-284a52ba00；b9085ab计量；s2-awq.json | 仍有高精度层；非总GPU占用减少63%；输出长度不同 |
| CUDA融合 | 自编RoPE+KV append单launch原型，完成48组数值、16组memcheck和6形状Event对照，保留上游能力核查与支持边界 | 72cce3a；s2-rope-cache.json；232203-63f35c079d | 独立FP16/Q28/KV4/D128，未接入服务，不宣称TPOT收益 |
| 部署分析 | 实测八形状FA2、真实Nsight及单卡/双副本/TP2的两长度两并发HTTP矩阵，768请求完成，按吞吐、延迟、质量与每卡效率给出条件建议 | 1436607/3d055ae；s2-fa2-prefill.json、s2-deployments.json；113913-03587d84d8等 | 单次64/cell P99仅探索；TP2长填充有一条质量差异 |

以上SHA可通过git log定位，完整run ID与路径见根reports及docs/coverage.md；叙事、原理/实现、实验/正确性、限制/权衡三类追问见本目录README.md。用户学习状态为材料已生成，尚未验证独立掌握。
