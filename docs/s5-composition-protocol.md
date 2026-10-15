# S5 组合与最终场景实施协议

进入依据：S4验收21fbdf7，stage-4-depth已推送且独立读回。S5尚未验收；最终test256至本协议仍未送模型。沿用同一双卡与固定环境，不新增付费资源。

先做开发诊断，再冻结最终profile与正式负载。cache×scheduler保留S4六配置三轮和真实生命周期，补自然业务质量对照；量化×spec用领域group128 AWQ Target与FP16训练Draft，单独比较量化Target/固定K4/自适应K，以及已有FP16对应项。Draft的quantization显式None并保存实际解析配置；量化推测的采样参照必须是同一量化Target。当前允许组合的CLI修正不等于组合已验证。全部启动失败与输出差异保留，必要时独立profile回退，不强行全部开启。动态K与heap默认关闭，除非本阶段独立证据足以支持具体负载建议。

最终质量入口显式选择split及实际记录数，test仅允许S5完整256条、quality-only和已冻结协议，绑定数据hash及协议hash。最终协议将在开发兼容与质量诊断之后、首次test推理之前提交；不能根据test重选阈值、修改提示、校准或训练。数据仍是独立场景组的规则代理，共享schema，不是实车安全评测。

开环使用锁定aiohttp3.14.5与asyncio，每条计划到达独立于其他请求完成；记录planned/dispatch/实际HTTP headers-sent/首末内容/finish单调时间。全程deadline从planned开始，包含客户端排队、连接和慢滴流；semaphore出队再次检查deadline，避免同一事件循环轮次内的到期竞态。HTTP/SSE错误、未知finish、无usage、超时、取消都保留分母。实际chunk可能合并token，请求级TPOT不是逐token ITL。客户端协议fixture不计模型成绩。

正式负载将分自然业务和合成混合长度压力，各三独立进程/部署；单卡列效率，双副本与TP2同两卡预算、全局maxseq8、轮询、相同轨迹/生成参数。候选4/12req/s，需开发冒烟后固定。每cell256条的P99仍探索性，不能声称生产尾部SLO。goodput阈值与包含drain的统计窗口将在正式运行前冻结，报告全部尝试、完成率、发送滞后、用户侧延迟、发送侧E2E、质量及各endpoint分布。S3的TP2跨轮波动和长填充质量差异继续保留，不用单次最佳值代替baseline。

独立CUDA不计服务收益。S5最终GPU回归与资产清单、独立原始复算、27项coverage和累计讲解完成后才验收；S6负责最终发布。GitHub保存新代码/原始实验，既有144OSS对象与恢复收据保留，新增大资产才上传。用户掌握另行记录。

开发HTTP试跑固定32条/cell、自然与512/1536填充混合、4/12req/s指数间隔、seed5501、APC开启、Graph开启、全局maxseq8、maxinflight256、整体deadline30s。自然SLO用户E2E≤2s且用户TTFT≤0.5s；填充SLO≤8s/4s，均为工程指标，非车辆期限。每cell先4条热身并等待完成，调用原生reset API且核验成功日志后测量；APC允许重复padding复用，必须解释该影响。正式协议待本次开发检查后单独冻结，不改变SLO来迎合结果。业务policy四组使用APC/scan、128KV块、wave8/maxseq4，观察真实排队选择；合成压力机制仍由S4六配置三轮覆盖。

## 正式开发负载重复冻结

完成开发三部署12cell和自然业务四策略后，固定configs/s5-openloop-formal.json：256请求/cell，4/32req/s，自然/512与1536混合，seed5501指数间隔、APC/Graph、冷起点经成功日志确认。SLO仍自然2s/0.5s、填充8s/4s。不能将APC共享填充收益泛化到唯一前缀负载，S3 APC关闭对照继续保留。256条中重复dev128，记录重复结构；P99为探索性，不换成万级稳定尾部措辞。正式三轮共9服务进程，每次1024请求、总9216；全部错误保留。

configs/s5-timing-plan-r1/r2/r3.json每轮还包含FP16与AWQ各Target/fixed/adaptive六进程，以及native/cache/scheduler/both四业务进程。每轮13任务，合计39独立进程；轮2反序、轮3轮换顺序。引擎规范同开发，计时关闭trace/logprobs，137条六模型及128条四策略。比较同量化Target，单项与组合不相乘；源码、模型/数据/环境、配置、工作负载指纹必须一致才能聚合三轮。正式重复之后只允许证据/文档改动；执行路径变动需保留旧run并重新匹配。

附加APC×spec的真实兼容probe以及AWQ随机采样trace为独立诊断，不进入性能表。无法组合时保留实际报错和独立profile，不能只用CLI限制冒充上游不支持。最终test协议另行冻结；本正式性能负载仅使用dev，尚不代表S5验收。

## 正式运行前的兼容性修订记录

初版三轮计划尚未执行。原生APC＋FP16 fixed的实际137条probe通过、21888缓存tokens、121/128业务且token一致；AWQ无APC随机adaptive实际K2/3/4、拒绝161行/bonus733/EOS128/长度截断5/无提议3，验证器宽度及计数审计通过。这些是兼容与路径证据，不是所有概率分布的证明。为使正式M3/M4基线也使用可组合的原生APC，先执行configs/s5-apc-full-plan.json：其余四个greedy组合及AWQ随机APC诊断。通过后创建三轮计划v2（保留从未运行的v1），仅修改模型组合的APC配置；正式结果必须匹配新基线，不能拿旧APC关闭数值计算新版收益。最终test仍未使用。

## APC正式协议v2与最终质量冻结

完整APC兼容检查已通过：FP16和AWQ各自Target/fixed/adaptive，四候选均137/137 token/status与同Target一致、业务121/128。AWQ随机APC trace另存s5-apc-awq-random.json，不进入性能表。三轮正式以configs/s5-timing-plan-v2-r1/r2/r3.json为准，模型六配置全部开启原生APC；波次/模型/数据/K/生成参数等不变。三份旧计划保留为未执行历史，不合并结果。开环仍为已冻结4/32、256/cell、自然/混合两类，三轮共9216请求。

configs/s5-final-quality.json现事前冻结完整test256与十个profile（六模型/四policy），逐profile最多一次最终质量运行；脚本要求显式final-profile且配置完全匹配，否则在GPU初始化前拒绝。默认FP16 Target+原生APC；baseline正确数至少231/256、256完成且JSON有效。候选正确数不低于对应baseline减2，spec还要求相同Target的有限greedy输出一致才能推荐。两个数字是工程容差，不是统计非劣效或车辆安全门槛。policy比较对应wave8/128KV的native，模型比较同wave4/512KV；AWQ的采样参照是AWQ Target。

未通过的candidate保留错误与独立profile，默认回退FP16，不能根据test重训/校准、改提示、阈值或反复选择最好结果。通过质量也不自动启用性能负收益组合。最终test尚未送模型；正式dev性能重复先运行，之后执行已冻结最终质量与GPU回归/资产核验。

分组goodput使用父cell完整统计窗口，包含其他组造成的drain；开发聚合初版误用各组自己的最后完成时间，现通过显式parent end修正并保存s5-openloop-development-v2，原报告保留。整体cell的raw统计不变，已有本地fixture验证快组也承担同一分母。nominal_rate为指数到达率参数；summary中的nominal_offered_requests_per_s为实际固定轨迹条数/计划窗口，有限样本可能偏离参数。

最终GPU回归采用configs/s5-final-gpu-plan.json：39 CPU、scan/heap各4真实allocator、275 CUDA全检查、scalar/half2/auto各24拒绝、99 memcheck、两组Graph生命周期。主推理路径同时由正式三轮及冻结test十profile覆盖。资产探针scripts/probe_s5_assets.py仅在GPU计时结束后运行：列出并核对144既有对象名、下载9小成员并比对归档/内容hash，不上传重复权重，不将存在性列表或小成员读回称全量权重重验。脚本已准备，实际执行结果另归档。
