# S5 组合与最终场景实施协议

进入依据：S4验收21fbdf7，stage-4-depth已推送且独立读回。S5尚未验收；最终test256至本协议仍未送模型。沿用同一双卡与固定环境，不新增付费资源。

先做开发诊断，再冻结最终profile与正式负载。cache×scheduler保留S4六配置三轮和真实生命周期，补自然业务质量对照；量化×spec用领域group128 AWQ Target与FP16训练Draft，单独比较量化Target/固定K4/自适应K，以及已有FP16对应项。Draft的quantization显式None并保存实际解析配置；量化推测的采样参照必须是同一量化Target。当前允许组合的CLI修正不等于组合已验证。全部启动失败与输出差异保留，必要时独立profile回退，不强行全部开启。动态K与heap默认关闭，除非本阶段独立证据足以支持具体负载建议。

最终质量入口显式选择split及实际记录数，test仅允许S5完整256条、quality-only和已冻结协议，绑定数据hash及协议hash。最终协议将在开发兼容与质量诊断之后、首次test推理之前提交；不能根据test重选阈值、修改提示、校准或训练。数据仍是独立场景组的规则代理，共享schema，不是实车安全评测。

开环使用锁定aiohttp3.14.5与asyncio，每条计划到达独立于其他请求完成；记录planned/dispatch/实际HTTP headers-sent/首末内容/finish单调时间。全程deadline从planned开始，包含客户端排队、连接和慢滴流；semaphore出队再次检查deadline，避免同一事件循环轮次内的到期竞态。HTTP/SSE错误、未知finish、无usage、超时、取消都保留分母。实际chunk可能合并token，请求级TPOT不是逐token ITL。客户端协议fixture不计模型成绩。

正式负载将分自然业务和合成混合长度压力，各三独立进程/部署；单卡列效率，双副本与TP2同两卡预算、全局maxseq8、轮询、相同轨迹/生成参数。候选4/12req/s，需开发冒烟后固定。每cell256条的P99仍探索性，不能声称生产尾部SLO。goodput阈值与包含drain的统计窗口将在正式运行前冻结，报告全部尝试、完成率、发送滞后、用户侧延迟、发送侧E2E、质量及各endpoint分布。S3的TP2跨轮波动和长填充质量差异继续保留，不用单次最佳值代替baseline。

独立CUDA不计服务收益。S5最终GPU回归与资产清单、独立原始复算、27项coverage和累计讲解完成后才验收；S6负责最终发布。GitHub保存新代码/原始实验，既有144OSS对象与恢复收据保留，新增大资产才上传。用户掌握另行记录。

开发HTTP试跑固定32条/cell、自然与512/1536填充混合、4/12req/s指数间隔、seed5501、APC开启、Graph开启、全局maxseq8、maxinflight256、整体deadline30s。自然SLO用户E2E≤2s且用户TTFT≤0.5s；填充SLO≤8s/4s，均为工程指标，非车辆期限。每cell先4条热身并等待完成，调用原生reset API且核验成功日志后测量；APC允许重复padding复用，必须解释该影响。正式协议待本次开发检查后单独冻结，不改变SLO来迎合结果。业务policy四组使用APC/scan、128KV块、wave8/maxseq4，观察真实排队选择；合成压力机制仍由S4六配置三轮覆盖。
