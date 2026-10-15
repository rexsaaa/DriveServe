# S5 组合与部署结论

三轮正式比较在原生APC、CUDA Graph和FA2基线上运行，各轮轮换/反转执行顺序。数据、实际执行源码、配置和环境指纹经聚合器核对一致。六模型每进程137请求（128dev与9边界），四policy每进程128自然业务；两类工作量和KV/wave配置不同，不能横向计算策略对模型表的“加速”。

FP16 Target/fixed/adaptive总wave秒均值15.3711/13.3646/13.1051，三次样本标准差0.0978/0.5854/0.2269。两种推测在本负载均缩短总时间，平均首字由约30.82ms增加至45.10/44.30ms。adaptive比fixed的差值方向跨轮变化；不能只挑最快轮证明动态K更优。真正的蒸馏贡献仍以S3固定K前后对照为准，S5没有重训。

AWQ Target总wave9.7624±0.1480s，fixed16.3439±0.5716s、adaptive16.5718±1.0062s；三轮都更慢。量化缩短常规Target路径后，Draft与验证开销占比可以增大，但现有计时未将负收益精确归因到某一个kernel，不以推测代替剖析。按计划默认关闭AWQ×spec，保留兼容与正确性入口。量化Target的推测结果与同一AWQ Target比较，不声称其保持FP16概率分布。

四policy各轮121/128，cache/both/native/scheduler均复用21824prompt tokens，逐请求token/status相同；自然业务没有显示自研冷热的额外复用。S4合成压力中热点保留、长短等待取舍及heap成本仍成立，不能用这个自然负载否定或夸大另一个分布的机制结果。heap保留独立入口，小池默认scan。未验证自研冷热×spec/TP/beam/swap/chunked的统一进程组合；独立CUDA不计服务收益。

HTTP三部署各三进程、每进程四cell×256，共9216/9216完成；每cell自然242/256正确、填充204/256。不同部署存在少量JSON空白格式差异，但解析结果、逐字段评分及错误位置一致。每cell256×3仍为探索性P99，真实负载重复dev128，不能当768独立场景或万级生产统计。S3 TP2首轮更快原因未明的记录继续有效；S5换了APC与负载，不能说它修复了旧波动。

高rate自然负载下单卡/双副本/TP2质量goodput均值约1.6617/2.6898/3.5199req/s，用户E2E P99逐轮分别约5.98–6.47/4.87–5.13/3.21–3.76s。两卡TP2在这组请求上比轮询双副本更有利，但三者都不能持续满足事前自然SLO（用户E2E≤2s且首字≤0.5s）；全部完成不等于实时达标。低rate三部署皆满足本次SLO，一张卡已满足这一小样本负载，无据此额外购卡的必要。

填充在模板前添加可复用公共prefix至512/1536，APC实际生效，且任务正确数降至204/256。填充SLO是8s/4s，与自然2s/0.5s不同，不直接跨负载比较goodput，不把填充吞吐当车载业务收益。单卡是一卡效率参考；双副本与TP2同两卡、全局maxseq8，replica每卡4并按ordinal轮询；自动KV容量不同但均有真实记录。无NVLink、P2P失败、TP2自定义all-reduce关闭，建议仅适用于记录的拓扑。

实际header发送跨度与计划整体rate相符，maxinflight等于全部256请求，因此semaphore不可能限制该cell的到达数；但单请求事件循环与连接抖动确实存在。报告同时保存worker启动滞后、post→header、planned→finish用户E2E与header→finish服务侧E2E，不声称客户端零扰动。timeout从planned开始覆盖等待、连接、慢滴流；错误和未发送尝试留在分母，group goodput共享完整父cell的drain窗口。

最终质量按冻结十profile/test256单独报告，不用最终test选择最快速度、改变工程容差或回填开发成绩。质量通过也不能让速度负收益组合变成推荐。用户掌握仍需复述与追问核验；阶段资料齐全不等于用户已经掌握。

最终十profile已实际完成：各256完成/JSON有效、236正确。四spec与对应Target的256条token/结束一致；scheduler/both各有test-007/test-140两条JSON空白差异，解析、字段评分和错误ID集合一致。工程质量门槛全部通过，速度负收益组合仍默认关闭。完整记录见reports/s5-final-quality.json，未据test调参。最后十项CPU/allocator/CUDA/Graph回归通过，见reports/s5-final-gpu.json。
