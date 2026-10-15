# S4 两项深化实施与验证协议

正式进入条件：S3 accepted且stage-3-validated可获取。两个专题为“精确淘汰顺序的堆索引”和“CUDA head tile/half2消融”。保留六线和默认FP16/原生profile；其余线沿用S3冻结实现，修改影响到的路径必须回归。最终test不进入S4。

## 选择依据和替代方向

S3 cache最终场景扫描累计12.73–12.82ms、both为15.32–16.27ms，128块池时不是总时间主导；当前min遍历全部空闲候选，先测规模曲线才能判断大池价值。选择改变数据结构保持策略规则，允许准确回答复杂度、内存、过期和旧条目成本。

原CUDA为一token一CTA；T1只有一个CTA，三轮Event约2.73μs。选择改变独立算子工作分配，分开研究head tiling与half2，减少串行线程工作并增加小T并行度。没有服务接入，不把算子收益写成服务收益。

其他候选：成本感知K需可靠在线成本估计，接受率控制在S3无稳定增量但原因不止阈值；TP2速度波动未知，需要另行通信诊断。当前先完成上述两个有独立可验证修改的专题；S5继续匹配部署复测，不把未知TP2原因虚构成已定位瓶颈。

## 专题A：堆索引

保留冷优先、最近访问、前缀长度降序和block_id顺序，冷热依旧有效复用≥2且30秒未过期；只索引零引用候选，活动块由上游refcount保护。两个victim heap、一个expiry heap、单调generation排除陈旧条目；超过max(64,4×free_count)重建。重新激活移除候选但保留reuse，物理块重用清旧hash。浮点deadline必须与旧now-last<ttl判定一致。

差分验证使用真实旧/新策略类而非替代模拟器，固定seed4401的20000步reactivate/release/touch/reuse/evict轨迹，每步metadata和victim一致；另检查TTL邻接浮点边界、完全清空、长期反复更新和内存界限。真实allocator4项分别scan/heap运行；引擎Graph生命周期比较共享、取消、抢占、重用和老化。

维护benchmark规模128/1024/8192/16384，固定每规模256轮；计量evict及add/reuse/update/remove/readd完整维护，保留每轮原始ns、初始化时间、Python allocation与重建计数，不只展示evict。三独立进程，轮换scan/heap先后。CPU曲线不是GPU吞吐。

服务四策略仍保留；最小新比较为native、scan cache/both、heap cache/both，在相同Graph/4、128块、36请求下3独立轮。对比输出、有效复用、总时间与长短等待；不强求堆改善该小池吞吐。源码选择用显式cache implementation开关，默认scan保持S3行为。

## 专题B：CUDA head tile及half2

保留v1源文件和入口。tiled scalar每token八个4-head tile，half2每线程同时两维，单独乘/加/减保持FP16中间舍入；Q/K及每个有效唯一slot有唯一写者，无跨CTA依赖。保持Q28/KV4、D128、NeoX完整旋转、FP16和既有cache布局。half2需要4字节地址对齐、偶数row stride；auto对小T的奇数stride/半字offset走scalar，T>32保留v1。

冻结候选auto cutoff32作为有限研究选择，不声称全局最佳。比较native separate、v1、tiled scalar、tiled half2、auto五组，T1/8/32/128/512/2048，100操作/Graph、20样本、同轮随机顺序、3独立进程。初始化、编译、索引检查和重置在外；公开入口包含CPU同步验证，不用raw kernel时间冒充公开API时间。

正确性覆盖12个T（含0/1/边界）、block16/32、padding0/1/128、半字offset及有限极值/次正规数；Q/K/cache和V/未写slot/padding均核对，上游逐元素相等与独立PyTorch张量参考容差分别保留。half2未对齐必须拒绝且不修改存储；auto回退必须与上游一致。独立compute-sanitizer子集，不与Event计时混合。检查入口原24类非法输入与只读alias正例按新入口回归。

## 运行、失败和验收

每单元正式clean SHA、模型/data/config/environment hash、run和assets；计划按30秒心跳落盘，失败停止且保留；继续前检查真实进程，整单元新run重测。性能实验两卡无其他任务且无OSS传输，保持源码干净直到当前计划结束。新增产物优先Git小证据；没有新权重则不无意义重复上传。

两专题分别给问题/实现/正确性/消融/维护和内存成本/负收益/适用范围，至少三独立重复；选定profile前以实际结果决定保留或默认关闭。任何失败不删原记录，不调整口径掩盖。无收益仍可在充分验证与解释后验收；只有真实证据可标完成。随后更新27项与六线累计讲解、资产审计和GitHub回放，才创建stage-4-depth。
