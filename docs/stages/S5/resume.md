# S5 六条累计事实版简历与证据映射

这六条覆盖S1–S5实际完成的工程工作；S5整体是否通过以[验收](acceptance.md)为准。业务为结构化规则车载决策代理，测试集按场景组隔离但共享schema；不宣称实车效果、生产稳定P99或用户已经独立掌握。以下数字均可回溯报告中的run ID、源码SHA与原始记录。

| 主线 | 可使用的事实表述 | 证据与必须保留的条件 |
|---|---|---|
| M1 源码诊断 | 在固定vLLM0.8.5 V0加入可关闭的调度/KV/输出观察器，关联70,804个GPU kernel的Nsight时间线；建立包含真实发送时刻、排队、超时和完整drain窗口的HTTP开环评估与逐请求复算 | [调用链](../../engine-diagnostics.md)、[Nsight](../../../reports/s2-nsight-engine.json)、[三轮开关](../../../reports/s3-stability.json)、[S5开环](../../../reports/s5-openloop.json)；trace与正式计时分离，未证明所有Decode受KV带宽限制 |
| M2 缓存调度 | 将零引用块冷热保留、长度老化admission及可选三堆索引接入真实引擎，完成四策略对照及共享/取消/抢占/重用验证；16k候选CPU维护中位由约4.84–4.89ms降至14.81–18.03μs | [S4消融](../../../reports/s4-depth.json)、[维护原因](../../../reports/s4-heap-maintenance.json)、[S5生命周期](../../../reports/s5-final-gpu.json)；heap额外内存和偶发长停顿，小池服务无明确总收益，scan默认；自然业务无额外缓存复用，最终调度2条JSON格式差异不隐去 |
| M3 推测蒸馏 | 实现滑窗接受率驱动的运行时K控制，完成472条合格教师样本、128步LoRA序列蒸馏及SIGTERM全状态恢复；原生APC下三轮FP16 fixed总wave13.3646±0.5854s，对Target15.3711±0.0978s；最终256条与Target token/结束一致 | [蒸馏/恢复](../../../reports/s2-training-recovery.json)、[贡献分离](../../../reports/s3-boundaries-fixed.json)、[S5组合](../../../reports/s5-composition.json)、[最终质量](../../../reports/s5-final-quality.json)；相同137请求，平均TTFT约30.82→45.10ms，动态K无稳定额外收益；序列级而非logit蒸馏 |
| M4 AWQ | 自行完成通用/领域各16384tokens的AWQ校准、group64/128及21代表层局部误差分析；领域128独立重校准13文件逐字节相同，逻辑权重15.231→5.571GB；最终领域128与FP16均236/256正确 | [AWQ](../../../reports/s2-awq.json)、[独立校准](../../../reports/s3-awq-reproducibility.json)、[最终质量](../../../reports/s5-final-quality.json)；复用AutoAWQ，保留高精度层；权重减少不等于总显存同幅下降；AWQ×spec三轮更慢并默认关闭 |
| M5 CUDA | 自编独立FP16 NeoX RoPE+KV append融合算子，并实现head tile/half2消融；三轮T1 half2约1.434–1.448μs对v1约2.734–2.744μs，最终执行275正确性/边界、99 memcheck及三入口各24非法输入检查 | [CUDA源码与范围](../../rope-cache.md)、[S4三轮](../../../reports/s4-depth.json)、[最终回归](../../../reports/s5-final-gpu.json)；Q28/KV4/D128有限布局，T2048 scalar退化；独立原型未接服务，不声称TPOT改善 |
| M6 部署评测 | 实测FA2 Prefill对照、Nsight及单卡/双副本/TP2；完成三轮开环9216/9216请求，分别报告延迟、发送滞后、SLO和质量goodput；两卡高rate自然负载TP2用户E2E P99约3.21–3.76s，双副本约4.87–5.13s | [FA2](../../../reports/s2-fa2-prefill.json)、[S5主表](../../s5-results.md)、[开环原始复算](../../../reports/s5-openloop.json)；每cell256×3仍探索性，三部署自然高点均未充分满足预设SLO；无NVLink/P2P失败，轮询副本、两卡公平口径；填充降质与S3波动保留 |

最终十profile各256请求均完成、JSON有效且236正确；四spec与各自Target的256条token/结束一致，scheduler/both各254条token一致，另两条只改变空白/换行。质量阈值在最终测试前冻结，未据test调参；通过质量不代表速度、尾部SLO或真实驾驶安全达标。

六线原理、源码入口、被否决方案、成本和追问在[累计讲解](README.md)，执行入口在[回放](replay.md)，27项映射见[覆盖](coverage.md)。原稿的占位百分比不是成果。学习材料已交付，用户是否能够独立复述和追问作答仍待核验。
