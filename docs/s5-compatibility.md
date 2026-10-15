# S5 实测兼容矩阵与最终配置

以下为已执行的有限范围，阶段验收另见[验收](stages/S5/acceptance.md)。固定vLLM0.8.5、V0非chunked、torch2.6.0+cu124、FA2、CUDA Graph；完整冻结配置在configs/s5-final-quality.json及三份v2正式计划，原始结果在reports/s5-composition.json、s5-final-quality.json、s5-final-gpu.json和s5-openloop.json。

| 组合或路径 | 实际证据 | 默认与适用边界 |
|---|---|---|
| FP16 Target + 原生 APC | 三轮137条及完整test256，test有效JSON256/正确236；单/双副本/TP2开环共9216请求另测 | 保守默认；不保证生产尾部或真实驾驶安全 |
| FP16 Target + FP16训练Draft + fixed/adaptive + APC | 四候选中的FP16两组各三轮137与Target token/结束相同；最终各256/256相同，正确236 | 独立单卡profile可回放；总时间缩短但TTFT增加，动态相对fixed增量不稳定；没有将其套用到HTTP TP2成绩 |
| 领域group128 AWQ Target + APC | 三轮业务121/128；最终test236/256；逻辑权重压缩沿用S2，校准复现沿用S3 | 通过质量的可选单卡推理profile；不自动推荐未测的量化HTTP/TP2组合 |
| AWQ Target + FP16训练Draft + fixed/adaptive + APC | 对同一量化Target三轮各137 token一致；最终各256一致、正确236 | 速度三轮均退化，默认关闭；量化推测不承诺保持FP16分布 |
| cache × scheduler | native/cache/scheduler/both各三轮128自然业务输出相同；最终cache256 token相同，scheduler/both254相同，另2条仅JSON格式变化，解析/评分/错误ID集合一致 | 自研规则用于独立单卡V0 profile；自然业务无额外复用收益，合成压力收益与长请求代价见S3/S4 |
| scan / heap实现 | S4三轮与S5两组Graph生命周期；每组792不变量快照、32共享块、2取消，16输出/status一致，实际发生抢占 | scan默认；heap大池CPU维护更快但额外内存与长尾，小池服务无明确总收益 |
| 自研缓存/调度 × spec 或 TP2/beam/swap/chunked | 没有已完成的统一进程验证 | 保留独立profile，不启用未经验证的组合 |
| 独立RoPE+KV CUDA v1/v2 | 三轮等价微基准沿用S4；S5重新执行275数值/边界、99 memcheck、三入口各24拒绝及只读alias正例 | 独立研究入口，不在任何服务执行路径中，不计服务TPOT收益 |
| FP16原生single / replica / TP2 HTTP | 各三进程，4/32标称到达率、自然/填充两类、每cell256；全部完成、自然242/256正确、填充204/256 | 两卡重负载此实验TP2更有利，但三种部署自然高点均有大量SLO未满足；低点单卡已满足此小样本SLO |

默认FP16 Target/native APC保留全部阶段的保守基线。fixed/adaptive、AWQ、冷热/长度策略、heap和CUDA各有独立入口，默认关闭不等于删除。配置推荐同时依赖质量、速度、资源和对应负载，不能将单项百分比相加或相乘。

冻结test门槛是完整256完成/JSON有效，FP16至少231正确，候选相对对应baseline最多少2条；spec推荐还要求有限greedy token/结束一致。实际十组均236正确。该工程容差不是统计非劣效证明；64隔离场景组仍共享规则/schema。测试只用于最终验收，没有据此改提示、训练、校准或阈值。

建议选择与复现：自然低到达率先用单卡FP16原生；需要压缩权重时使用已验证领域AWQ Target独立profile；长输出批处理可比较FP16 fixed与Target并接受首字代价；高到达率两卡需按原轨迹复测TP2与replica，不能拿本次探索P99承诺新环境。自研缓存针对热点混合压力，运行前评估长请求代价。迁移后重建overlay/扩展并重测受影响baseline，旧卡的速度不是新卡成绩。
