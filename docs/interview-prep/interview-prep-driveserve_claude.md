---
name: interview-prep-driveserve
description: DriveServe 项目秋招面试准备：六条主线的叙事框架、代码位置、面试问答、关键数字
metadata:
  node_type: memory
  type: project
  originSessionId: 504f36fb-0abf-4abc-97be-c745a74d0639
  modified: 2026-10-25T00:00:00+08:00
---

# DriveServe 面试准备文档

## 🎯 学习策略（重要！新 session 必读）

**目标定位**：快速理解 DriveServe，能在面试中用自己的话准确讲清楚“问题是什么、我改了什么、为什么可能有效、实测怎样、有什么代价”。先完成六条主线的最低准备，再按追问深入。

**2026-10-25 回答约定**：结合两种讲解的优点，采用“背景→问题→改动”的连贯顺序，配合具体例子、经过核对的实验结果和必要边界。完整性体现在因果链齐全，精要体现在只展开当前需要的内容，易懂体现在用户能用例子解释并自己复述。

本节用于指导后续学习回答。下方六条主线正文保留历史提纲，不能直接当作已核实的标准答案；历史说法与源码、实际实验配置或留档冲突时，应先纠正再讲解。文档勾选完成仅代表对应资料整理完成，不代表用户已经掌握。

### 1. 知识分层：先建立主线，再处理追问

| 档次 | 第一轮需要做到 | 回答方式 |
|---|---|---|
| ✅ **必须懂** | 讲清问题、改动、基本机制、关键结果和代价 | 直白解释 + 一个具体例子 + 必要证据 |
| 📌 **知道就行** | 知道概念用途，能接住基础追问 | 术语配一句话解释，按需展开 |
| ⏸️ **第一轮先不深挖** | 知道实现边界，明确哪些部分尚未深入 | 暂缓底层细节；追问涉及简历主张或正确性时再补 |

不预设“面试一定不会问”的内容，也不使用无依据的面试概率或学习时间比例。没有读懂某一行实现，不等于整条主线没有掌握。

### 2. 新主线的默认讲解顺序

1. **一句话做了什么**：先指出改动对象和目的，让用户知道这一条主线解决什么。
2. **原生机制→遇到的问题**：用两三句话交代原来怎样工作，以及什么场景会暴露问题；已确认理解的背景不重复展开。
3. **改动→具体例子**：先讲两三条核心规则，再用一个最小例子走完规则。缓存用两个块，调度用三条请求，张量并行用具体矩阵形状。例子中的数字明确属于演示，不冒充实测结果。
4. **实测结果→代价与适用范围**：优先给一至三个关键数字，紧跟指标含义、比较对象和必要负载条件；同时说明一个关键代价或负结果。
5. **面试复述→一个理解题**：给一段能在 30–60 秒内复述的答案，再问一道检验核心因果关系的小题，等待用户回答。

需要整条主线讲解时，沿用“必须懂 / 知道就行 / 第一轮先不深挖”的分层。机制不清楚时，先解决当前卡点，再继续结果和面试表达，不一次塞进全部源码与实验条件。

### 3. 如何兼顾精要和易懂

- **先用日常语言说明作用，再给术语**：例如先说“决定淘汰哪个 KV 块”和“决定先接纳哪个请求”，再介绍 evictor 和 admission。
- **先理解规则，再看必要代码**：只有短代码能直接解释关键判断时才展示；参数传递、日志字段、索引维护等细节放到追问层。
- **比较用小表格，流程用短例子**：让用户能手推“为什么选 A 而不是 B”。不为一个简单概念额外加入大图或长表。
- **正文解释，复述压缩，笔记只留关键词**：默认给一段整合后的面试回答；需要练习时再拆成两三个问答。平板笔记按需提供，不把正文、问答和笔记完整重复三遍。
- **追问只答当前问题**：通常先给结论，再解释原因，必要时加一个例子；不重新输出整条主线，不顺带扩展下一条主线。
- **有错误就明确纠正**：说明原说法错在哪里，并给可以直接替换的说法；正确部分不反复审查，不把细枝末节挤进第一轮讲解。

### 4. 简化必须保留哪些条件

- **机制以源码为准，结果以实验留档为准**：沿用已经核对的证据；新数字、新因果判断或发生冲突时再定点检查。代码默认值与实验实际值分开说明。
- **影响结论的条件不能省略**：例如 M2 只淘汰零引用候选；只有冷热、访问时间都相同时，才按更大的 `num_hashed_tokens` 优先淘汰。不能压缩成“小块先淘汰”。
- **参数不能升级成保证**：例如等待达到老化阈值只提高排序优先级，不能说“长请求最多等 0.5 秒”；TTL 根据最近有效复用时间判断，不能等同于严格的 30 秒滑动窗口计数。
- **实测与解释分开**：先说观测到什么，再说可能原因；未隔离验证的原因要标明推测。没有证据时，不补写“算力翻倍所以一定更快”等因果结论。
- **指标和范围保持一致**：平均等待、TTFT、TPOT、吞吐、P99 分别表述；合成压力、自然业务、算子微基准和服务端到端结果分别表述。局部收益不能扩大成所有负载的收益。
- **负结果也是答案的一部分**：如 M2 短请求等待改善伴随长请求代价，S5 自然业务没有额外缓存复用；不能因此总结为“both 综合最优”。
- **证据放在对应结论旁边**：提供少量可定位的源码或报告链接；首轮无需铺满 run ID、SHA、完整配置，追问或复现时再展开。

### 5. 可复用的面试表达与学习节奏

> “原来在【场景】下存在【问题】。我在【组件】改了【关键机制】，它通过【原因】影响【指标】。在【实验条件】下，相比【基线】测得【结果】；代价是【取舍】，目前证据支持到【范围】。”

这段模板用于组织表达，不要求逐字背诵。不能确认的数字先核对，不为填满模板而编造。问题较简单时直接回答，不强行套完整模板。

每次只检验一个核心点。用户回答后，先指出理解正确的部分，再纠正一个关键偏差；能用自己的话解释后继续。用户明确要求推进下一项时，不强制完成问答。需要动手时，由用户执行，助手解释命令、观察结果并协助排错；助手代跑与用户独立完成分别记录。

---

## 项目背景一句话

> 面向车载规划场景，基于 vLLM + Qwen2.5，做推理优化与压缩。实现了缓存调度改进、推测解码动态控制、AWQ 量化、CUDA Kernel 融合，并对比了三种部署方式的延迟和显存。

环境：2× RTX 4090，vLLM 0.8.5，torch 2.6.0+cu124，Qwen2.5-7B（Target）+ 1.5B（Draft）

---

## 学习前提（按实际掌握程度确认）

以下是相关基础，不因出现在清单中就认定已经掌握；讲解时只补当前需要的部分。

- vLLM Scheduler、Block Manager、Model Runner 三大组件结构
- Paged Attention 如何提高 KV Cache 利用率
- Continuous Batching prefill 与 decode 调度
- Prefix Cache content_hash 机制
- FlashAttention 分块 m/l/A 避免中间矩阵读写

---

## 六条主线难度分层

| 主线 | 简历标题 | 难度 | 建议顺序 |
|---|---|---|---|
| M1 | 源码分析与性能诊断 | ⭐ | 第1个 |
| M5 | CUDA Kernel 融合 | ⭐⭐ | 第2个 |
| M6 | 性能分析与部署 | ⭐⭐ | 第3个 |
| M2 | 缓存与调度 | ⭐⭐⭐ | 第4个 |
| M4 | 模型量化 | ⭐⭐⭐ | 第5个 |
| M3 | 自适应推测解码 | ⭐⭐⭐⭐ | 第6个 |

---

## M1 — 源码分析与性能诊断

### ✅ 必须懂（面试版）

**做了什么（一句话）**：在 vLLM 的 Scheduler / Block Manager / Model Runner / LLMEngine 四个关键类上加观测钩子，记录调度状态、KV 分配、执行耗时，用来诊断 prefix cache 命中率、调度队列积压、decode 占比。

**怎么做的（核心机制）**：
- Python monkey-patch（运行时替换函数），把原方法包一层
- 调用前后记录状态（队列长度、空闲 block 数、token 数）+ host 耗时
- 写到本地 JSONL 文件（每个进程一个 events-<pid>.jsonl）

**关键设计（为什么不影响性能）**：
- **opt-in 开关**：靠环境变量 `DRIVESERVE_TRACE_DIR` 控制
- 不设置 → emit() 第一行直接 return，零开销
- 设置了 → 实测影响 +0.3%-0.7%（可接受的诊断噪声）

**记录了什么数据**：
- Scheduler：waiting/running/swapped 队列长度 + 每个请求命中的 prefix block 数
- BlockManager：空闲 GPU block 数变化
- ModelRunner：prefill/decode token 数 + host 调用耗时
- LLMEngine：请求完成状态

**能诊断什么**：
- Prefix cache 命中率（哪些请求跳过了多少 block）
- 调度积压（waiting 队列长度随时间变化）
- Decode 占比（decode tokens vs prefill tokens）

### 📌 知道就行

- **monkey-patch**：运行时替换函数的 Python 技术，不改源码
- **emit() 函数**：写 JSON 日志到文件的函数
- **instrument_* 函数**：决定钩哪个类的哪个方法
- **NVTX range**：Nsight 可视化标记（可选，不影响主逻辑）

### ⏸️ 第一轮先不深挖

- `_observe` 函数的 wraps 装饰器实现
- threading.Lock 的线程安全细节
- JSONL 格式的 separators 参数
- `before` / `after` 回调函数的参数传递

### 面试问答（复述练习，答案使用前按上方约定核对）

**Q：你怎么对 vLLM 做插桩的，会影响推理延迟吗？**

A：我用 Python monkey-patch 的方式，在 vLLM 的 Scheduler、Block Manager、Model Runner 关键函数前后插入 emit() 调用，记录事件到本地 JSONL 文件。为了不影响正式计时，插桩通过环境变量 `DRIVESERVE_TRACE_DIR` 控制，不设置则完全不执行任何插桩代码。实测开启 trace 的时间开销在 +0.3% 到 +0.7% 之间，属于可接受的诊断噪声。

**Q：你从 Prefix Cache 诊断中发现了什么？**

A：在 `record_prefix_reuse` 里记录了每个请求实际跳过的 block 数量（`full_reused_blocks`）和跳过的 token 数量（`skipped_tokens`）。诊断发现在短请求场景下 prefix cache 命中率高，但长请求由于 block 不对齐（最后一个 partial block 无法复用）存在浪费，这是后来缓存策略改进的依据。

**Q：你看了哪些 vLLM 源码？**

A：主要看了三个类：Scheduler（调度决策，waiting/running/swapped 三队列，`_schedule_prefills` 和 `_schedule_running` 的优先级逻辑）、SelfAttnBlockSpaceManager（KV block 分配回收，`allocate`/`free`/`can_allocate` 的引用计数和 evictor 接口）、ModelRunner（`execute_model` 的 attention backend 调用路径）。

---

## M5 — CUDA Kernel 融合

### 做了什么

自编 CUDA kernel，把 vLLM 执行路径中两步分开的操作合并：
- 原来：① RoPE 旋转 Q/K → ② KV 写入 Cache（reshape_and_cache）
- 改后：一个 kernel 内完成 Q/K 的 RoPE + K/V 写 Cache

### 代码位置

- `csrc/rope_cache.cu` — 主 kernel，87 行，每个 token 一个 CUDA block，256 线程
- `csrc/rope_cache_tiled.cu` — S4 深化版，支持 scalar/half2/auto 三种 tile 策略
- `csrc/rope_cache_v2.cpp` — pybind11 binding v2，独立入口
- `driveserve/rope_cache.py` — Python 封装接口
- `scripts/check_rope_cache.py` — 数值一致性验证 + memcheck

### 关键设计点

**为什么可以融合？**
每个 token 的 RoPE 旋转和 KV Cache 写入是完全独立的（不同 token 互不依赖，不同 slot 不冲突），所以可以在同一个 kernel 里串行完成，省去一次全局内存往返（RoPE 结果不需要写回再读）。

**kernel 结构（rope_cache.cu）：**
```
每个 token → 一个 CUDA block (blockIdx.x = token)
线程数 = 256
步骤：
1. 读 position → 查 cos/sin 表
2. 对所有 Q heads (28个) 做 RoPE 旋转，写回 projection
3. 对所有 KV heads (4个) 做 RoPE 旋转
4. 把旋转后的 K/V 写入 paged cache（按 slot 寻址）
```

固定参数：Qwen2.5 架构 Q=28 heads，KV=4 heads（GQA），head_dim=128，FP16。

### 关键数字

- 形状覆盖：六种 FP16 形状（不同 token 数量）
- 数值一致性：48 组测试全通过（vs vLLM 分步执行）
- memcheck：16 组零错误
- 算子耗时降低：**18%–31%**（相对分步执行基线，CUDA Event 微基准）
- S4 tiled 版本：275 组正确性 + 99 组 memcheck

### 面试问答

**Q：你为什么可以把 RoPE 和 KV Cache Write 融合？有什么前提条件？**

A：前提是 token 之间独立，且每个 token 的 KV slot 是唯一的（vLLM 的 paged attention 保证不同 token 写不同 slot）。融合的收益来自：分步执行时 RoPE 结果要写回 HBM 再被 cache_write kernel 读一遍，融合后 RoPE 结果留在寄存器里直接写 cache，省了一次 HBM 读写往返。

**Q：你的 kernel 是怎么处理 GQA 的？**

A：Qwen2.5 是 GQA（Grouped Query Attention），Q 有 28 个 head，KV 只有 4 个 head，都是 head_dim=128。我在 kernel 里先处理 28 个 Q head 的 RoPE（只旋转不写 cache），再处理 4 个 KV head 的 RoPE + 写 cache。cos/sin 是按 position 索引的，Q 和 K 用同一套旋转角，这和 vLLM 上游行为一致。

**Q：18%-31% 的收益怎么测的，你怎么保证公平？**

A：用 CUDA Event 在 kernel 前后打时间戳，跑 100 次 warm-up 后取中位数，六种形状各跑三个独立进程各 20 个 Event 样本。对比基线是 vLLM 分步执行（先 apply_rotary_pos_emb 再 reshape_and_cache_flash），同一 CUDA stream，同一输入。局限是微基准，不包含 host dispatch 和同步开销，不能直接推导端到端收益。

---

## M6 — 性能分析与部署

### 做了什么

对比三种部署方式的端到端 P99 延迟、显存和任务质量：
1. **单卡**（single，一张 RTX 4090，全部请求串行）
2. **双副本**（dual replica，两个独立 vLLM 进程，round-robin 负载均衡）
3. **TP2**（Tensor Parallel 2，一个 vLLM 进程跨两张卡做张量并行）

同时用 Nsight Systems 采集了 GPU kernel 执行时间线。

### 代码位置

- `scripts/benchmark_deployments.py` — 三部署对比基准测试
- `scripts/benchmark_openloop.py` — 开环 HTTP 9216 请求测试（S5）
- `scripts/analyze_nsys.py` — Nsight Systems profile 分析（70,804 kernel）
- `driveserve/openloop.py` — 异步 HTTP 客户端，记录 TTFT/TPOT/E2E/P99
- `scripts/analyze_deployments.py` — 部署指标聚合

### 关键数字

- 测试负载：自然负载 **32 req/s** 到达率，两种请求长度（short/long），两种并发
- 三轮测试：每轮各完成 2304 请求（S3），S5 开环 9216/9216 完成
- **TP2 vs 双副本 P99 降低约 27%–34%**（三轮测试范围）
- Nsight：70,804 kernel，分析 kernel launch overhead 和 execution gap
- FlashAttention-2 prefill benchmark：8 种形状，对比 torch flash 路径和 FP32 参考

### 三种部署的本质区别

| | 单卡 | 双副本 | TP2 |
|---|---|---|---|
| 显存 | 受限（一卡） | 两倍（各一份权重） | 共享（权重分片） |
| 通信开销 | 无 | 无（各自独立） | AllReduce（每层）|
| 并发上限 | 低 | 高（两个 engine） | 高（一个 engine 更大 batch） |
| 适用场景 | 低负载 | 中负载 | 高负载长序列 |

### 面试问答

**Q：TP2 为什么比双副本 P99 更低？你预期是这个结果吗？**

A：TP2 把每个 attention/MLP 的计算分到两张卡上，单次 forward 延迟更低（算力翻倍），但引入了每层的 AllReduce 通信。双副本虽然没有通信开销，但每个进程只有一张卡的算力，在高并发下（32 req/s）大 batch 的 decode 延迟更高。在这个负载下 TP2 的 compute benefit 超过了 AllReduce overhead，所以 P99 更低。首轮 TP2 比预期快，原因我没有完全定位，可能是 batch 利用率差异。

**Q：Nsight Systems 你看了什么，发现了什么？**

A：分析了 70,804 个 kernel 的执行时间线，主要看两件事：① kernel 之间的 gap（launch overhead 和 CPU-GPU 同步点）；② prefill vs decode 的 kernel 占比。发现 decode 阶段 kernel 执行时间占比小但 launch 频率高，gap 比 prefill 大，说明 decode 更受 dispatch overhead 影响而不是纯 compute bound。局限是这是 profile 开销下的测量，正式延迟测试不开 Nsight。

**Q：TTFT 和 TPOT 分别是什么，你测的是哪个？**

A：TTFT（Time To First Token）是从发送请求到收到第一个 token 的时间，主要反映 prefill 延迟和排队时间。TPOT（Time Per Output Token）是后续 token 的平均间隔，反映 decode 吞吐。我在 `openloop.py` 里两个都测了，用 aiohttp 的 hook 精确记录 headers_sent 时间戳，TTFT = first_content_ns - sent_ns，TPOT = (last_content_ns - first_content_ns) / (n-1)。

---

## M2 — 缓存与调度（冷热驱逐 + 长度老化）

### 做了什么

在 vLLM 的 Block Allocator 驱逐策略上做了两个改动：

**改动1：Prefix-aware 冷热缓存**

vLLM 默认驱逐策略是 LRU（最久未访问先淘汰），不区分 block 是否经常被复用。改动：按 block 的 content_hash 统计复用次数，复用次数 ≥ 阈值（默认2次）且在 TTL 内（默认30s）的 block 算"热"，驱逐时优先淘汰"冷"的 block。

**改动2：长度感知调度（带老化）**

vLLM 默认 FCFS（先来先服务）。对短请求更友好，但长请求一来就占满 KV 预算。改动：在 Scheduler 的 waiting 队列排序时，按请求长度升序（短请求优先），但等待超过老化阈值（默认0.5s）的请求无论长短都优先（防止饥饿）。

### 代码位置

- `driveserve/engine_policies.py` — 核心实现
  - `ColdHotEvictor` 类：冷热驱逐逻辑（L20-L78）
  - `order_waiting()` 函数：长度老化调度（L129-L152）
  - `record_prefix_reuse()` 函数：在 prefill 时记录哪些 block 被复用（L99-L121）
- `driveserve/heap_policy.py` — S4 深化：三堆实现（冷/热/到期）
- `patches/vllm-v0.8.5-policies.patch` — 接入 vLLM 的两个调用点：
  - `add_seq_group()` 里记录 arrival time
  - `_schedule_prefills()` 里调用 `order_waiting()`
  - prefix cache 命中后调用 `record_prefix_reuse()`

### 关键代码逻辑

`ColdHotEvictor.evict()` 的排序 key（优先淘汰谁）：

```python
key = (is_hot, last_accessed, -num_hashed_tokens, block_id)
# is_hot=False (冷) → 排前面（先淘汰）
# is_hot 相同时，最久未访问的先淘汰
# last_accessed 相同时，hash token 少的先淘汰（内容少的不值得保留）
```

`order_waiting()` 的排序 key：

```python
if 等待时间 >= age_s:  # 老化请求，最高优先级
    key = (0, arrived, 0)
else:  # 正常请求，按长度升序
    key = (1, prompt_len, arrived)
```

### 四策略对照实验

| 策略 | 含义 |
|---|---|
| native | vLLM 默认，LRU + FCFS |
| cache | 仅冷热驱逐，FCFS |
| scheduler | 仅长度老化，LRU |
| both | 冷热驱逐 + 长度老化 |

结论：cache/both 策略在热点前缀场景下，复用 token 数（992 tokens）比 native 明显更多；scheduler 改善短请求等待，但长请求退化；both 策略是综合最优。

### 面试问答

**Q：你的冷热缓存和 vLLM 默认 LRU 有什么区别，为什么要这样改？**

A：vLLM 默认 LRU 只看最后访问时间，不管这个 block 是否经常被复用。在车载场景下，系统提示词（system prompt）这类前缀 block 每个请求都会用，用 LRU 会导致它在低负载时被淘汰，下一个请求又要重新 prefill。我加了复用次数统计（`reuse` 表，按 content_hash），热 block 在驱逐时优先保留，有 TTL 机制（30s 内无复用才清冷热状态）防止热度状态无限累积。

**Q：你怎么知道哪个 block 被复用了？**

A：在 vLLM 的 prefix cache 流程里，`_schedule_prefills` 会计算 `common_computed_block_nums`（已在 cache 里的前缀 block）。我在 patch 里加了一个调用，在第一次 prefill 时（非 chunked）把这些 block 的 content_hash 记录到 `ColdHotEvictor.reuse` 表，复用次数 +1。

**Q：长度感知调度的老化机制是怎么实现的？老化阈值怎么定的？**

A：`add_seq_group()` 里记录请求到达的单调时钟时间（`_driveserve_enqueued_at`）。每次 `_schedule_prefills()` 调用前，对 waiting 队列按 key 重排：等待超过 `age_s=0.5s` 的请求 key 最小（优先被调度），其余按 prompt_len 升序。0.5s 是实验参数，确保长请求不会无限等待。

**Q：共享块、取消、抢占的正确性怎么验证的？**

A：在 `check_policy_allocator.py` 里，直接操作真实 vLLM allocator（不 mock），模拟了：① 多请求共享同一前缀 block（ref count > 1 时不能驱逐）；② 请求取消后 block 引用计数正确归零；③ 抢占（swap out）后 block 状态正确。这些是 `assert_allocator_invariants()` 验证的四个不变量。

---

## M4 — 模型量化（AWQ W4A16）

### 做了什么

对 Qwen2.5-7B 做 AWQ（Activation-aware Weight Quantization）W4A16 量化：权重 4bit，激活 16bit（FP16 计算）。对比了三个维度：
1. **校准数据来源**：通用数据（wikitext/c4类）vs 车载 domain 数据
2. **Group Size**：g64 vs g128（量化粒度）
3. **层敏感性分析**：记录 0/13/27 三个代表层各线性模块的量化误差

### 代码位置

- `scripts/quantize_awq.py` — AWQ 校准与导出，继承 `AwqQuantizer` 加 sensitivity 记录
- `scripts/freeze_awq_data.py` — 冻结校准数据（32个block × 512 tokens）
- `scripts/analyze_awq.py` — 层误差分析
- `driveserve/engine_policies.py` → 和 AWQ 部署结合的 benchmark 在 `scripts/benchmark_speculation.py`

### AWQ 基本原理

AWQ 的核心洞察：不是所有权重都同等重要，重要权重（对应激活值大的 channel）量化误差对输出影响更大。AWQ 对每个 group 的权重乘以一个 per-channel scale，让重要 channel 的权重落在量化表示的"精度集中区"，从而减少误差。W4A16 意味着权重存 4bit，推理时解量化成 FP16 做矩阵乘法。

### 校准数据来源

- **通用数据**：32 block × 512 tokens，wikitext/c4 类文本
- **Domain 数据**：从 DriveServe 任务（结构化驾驶决策 prompt）采样的 32 block × 512 tokens

层敏感性分析用的是局部线性输出误差（`relative_mse = sum((XW-XQW)^2) / sum((XW)^2)`），在 0/13/27 三层的所有 attention/MLP 线性模块上计算。

### 关键数字

- **FP16 权重**：15.231 GB
- **AWQ 量化后**：5.571 GB
- **固定 KV 预算（8192 tokens）下显存占用降低约 56%**
- **任务质量**（128 请求）：通用校准 118/128，domain 校准 128/128，domain g64 121/128
- group64 层误差比 group128 改善 **23.6%**（未达 25% 切换线，最终用 g128）
- 三组 AWQ variant 各跑三轮，结果可重现

### 面试问答

**Q：AWQ 和 GPTQ 有什么区别？你为什么用 AWQ？**

A：GPTQ 是逐层 Hessian 二阶优化，量化误差更小但校准慢、对校准数据敏感；AWQ 是基于激活感知的 per-channel scale，校准快，对数据依赖更小，在部署框架（vLLM）里有原生支持（AutoAWQ + Marlin kernel）。我用 AWQ 是因为 vLLM 0.8.5 对 AWQ-GEMM 有良好支持，部署链路更短。

**Q：domain 校准数据比通用数据好在哪里，差多少？**

A：domain 数据用的是和推理任务相同分布的车载决策 prompt，通用数据是 wikitext/c4 类文本。在任务质量上：domain g128 达到 128/128，通用 g128 只有 118/128，差了 10 个请求（约 8%）。直觉上 AWQ 的 scale 搜索是基于校准集的激活分布，domain 数据让 scale 对任务输入更友好。

**Q：56% 显存降低是怎么算的？**

A：两个组成部分：① 模型权重从 15.231 GB 降到 5.571 GB，节省约 9.66 GB；② 固定 KV cache 预算 8192 tokens，这部分不变。在固定 KV 预算下，FP16 总显存 = 权重 + KV = X，AWQ 总显存 = 5.571 + KV = Y，(X-Y)/X ≈ 56%。具体数字在 `reports/s2-awq.json`。

**Q：Group Size 怎么选的，g64 和 g128 各有什么权衡？**

A：g64 的量化粒度更细（每64个权重共享一套 scale），误差更小（层误差改善23.6%），但显存和计算开销略大（更多 scale 参数）；g128 误差稍大但更紧凑。我测了 g64 vs g128 的层误差、任务质量和显存，g64 误差改善未达预设 25% 切换阈值，最终选 g128。

---

## M3 — 自适应推测解码

### 做了什么

三件事：
1. **蒸馏 Draft 模型**：用 Qwen2.5-7B（Target）生成标签，训练 Qwen2.5-1.5B（Draft）的 LoRA，128步序列级蒸馏
2. **动态 K 控制器**：按滑动窗口接受率实时调整 Draft 生成长度 K（1-4）
3. **贡献分离**：对比 FP16 无推测基线、FP16+fixed-K、FP16+adaptive-K、AWQ+fixed-K 四种组合

### 代码位置

- `driveserve/spec_control.py` — `DraftLengthController` 类（动态K）+ `prepare_step`/`observe_verification`（接入vLLM）
- `scripts/train_draft.py` — LoRA 序列蒸馏，128步，完整 SIGTERM 恢复
- `patches/vllm-v0.8.5-spec.patch` — 接入 vLLM speculative decoding worker
- `scripts/benchmark_speculation.py` — 贡献分离 benchmark
- `scripts/analyze_speculation.py` — 接受率和 TPOT 分析

### 推测解码基本流程

```
每个 decode step：
1. Draft 模型（1.5B）生成 K 个 candidate token（快）
2. Target 模型（7B）一次性验证 K+1 个 token（并行）
3. 按接受/拒绝规则：接受 r 个 draft token + 1 个 bonus token
4. 实际 emit r+1 个 token（比正常 decode 多 r 个，但只多了一次 7B forward）
```

关键：K 越大，单次 forward 产出越多，但如果接受率低，浪费 draft 计算。

### DraftLengthController 逻辑

```python
# 滑动窗口大小 = 8 batch
# hold period = 8 batch（防抖动）
# low = 0.45, high = 0.80

若 window_ratio < 0.45:  K = max(1, K-1)   # 接受率低，减小K
若 window_ratio > 0.80:  K = min(max, K+1)  # 接受率高，增大K
否则:                    K 不变              # hysteresis band
```

adjust 后有 hold period（8个batch 内不再调整），防止来回抖动。

### 关键数字

- Draft 模型：Qwen2.5-1.5B，LoRA rank=8，alpha=16，128步，batch_size=2，accumulation=4
- 蒸馏数据：7B 生成的 640 条车载场景 teacher data（472 train + dev），序列级（不用 logits）
- **蒸馏 Draft fixed-K vs FP16 无推测基线：TPOT 降低约 18%**
- AWQ + 推测解码：16.34s（比 FP16 baseline 15.37s 更慢，负收益）
- 动态 K 无稳定增量优势（接受率已经高时，adaptive 和 fixed 差不多）

### 面试问答

**Q：推测解码的接受率是什么意思，你怎么计算的？**

A：接受率 = 实际被 Target 接受的 draft token 数 / 总提议 draft token 数。在 `observe_verification()` 里，我解析 vLLM verifier 的输出 token_ids（格式是 [接受的draft prefix... , bonus/recovery token, -1...]），统计 causal prefix 长度作为 accepted，对应 proposed=K。批次累计后算 `accepted_total / proposed_total`，窗口内的比值控制下次 K 的选择。

**Q：你为什么选序列级蒸馏而不用 logits 蒸馏？**

A：logits 蒸馏效果理论上更好（KL 散度对齐分布），但需要 teacher 在推理时输出完整 logits，显存和计算成本高（7B 每次 forward 的 logits）。序列级蒸馏只需要 teacher 的 token id 序列（answer-only），cost 低，数据生成也更简单。局限是对分布对齐不如 logits 精确。

**Q：AWQ + 推测解码为什么反而变慢了？**

A：两个因素：① AWQ Draft 虽然权重小，但 verifier（Target AWQ）的量化/反量化开销加上 AllReduce（如果 TP）抵消了 draft 推理收益；② AWQ 量化会轻微改变 Target 分布，导致接受率下降，K 的有效利用率低。最终 AWQ+spec = 16.34s > FP16 baseline 15.37s，是负收益。这也是为什么简历里"蒸馏 Draft 固定 K 较 FP16 无推测基线降低 18%"特指 FP16 组合，不是 AWQ 组合。

**Q：128步蒸馏够吗？你怎么知道模型收敛了？**

A：这是个务实选择，不是理论最优。128步（batch_size=2, accumulation=4，实际每步8条数据）主要目的是让 1.5B 的 LoRA 在 7B 的答案分布上有适度偏移，提升接受率。我记录了每步的 loss 曲线（`steps.jsonl`），loss 稳定下降后趋于平稳。没有主张"模型充分收敛"，简历里也说了"序列级蒸馏，训练 loss 不等于任务质量或推测接受率证据"。

---

## 快速面试叙事模板（60秒版本）

> "DriveServe 是我独立开发的 vLLM 推理优化项目，面向车载决策代理场景。整体做了六个方向：
> 
> 第一，**插桩诊断**，对 vLLM 的 Scheduler、Block Manager、Model Runner 加了 opt-in 观测器，诊断 prefix cache 复用率和调度热点。
> 
> 第二，**缓存调度**，在 vLLM 默认 LRU 上加了冷热驱逐（按复用次数区分 hot/cold block），加了长度感知调度（短请求优先、老化保底），四策略对照验证了热点保留效果。
> 
> 第三，**推测解码**，用 7B 蒸馏了 1.5B 的 Draft LoRA，动态 K 控制器按滑动窗口接受率调整草稿长度，蒸馏 Draft 固定 K 下 TPOT 降低约 18%。
> 
> 第四，**AWQ 量化**，完成 W4A16 校准，对比通用/车载校准数据和 group size，显存占用降低约 56%。
> 
> 第五，**CUDA Kernel 融合**，自编 RoPE + KV Cache Write 融合 kernel，六种 FP16 形状下算子耗时降低 18%-31%。
> 
> 第六，**部署对比**，用 Nsight Systems 分析执行时间线，对比单卡/双副本/TP2，自然负载 32 req/s 下 TP2 的 P99 比双副本低 27%-34%。"

---

## 进度记录

- [x] 扫描代码库（S1-S6）
- [x] 六条主线难度分层评估
- [x] M1 源码诊断 — 叙事框架完成
- [x] M5 CUDA 融合 — 叙事框架完成
- [x] M6 部署对比 — 叙事框架完成
- [x] M2 缓存调度 — 叙事框架完成
- [x] M4 AWQ 量化 — 叙事框架完成
- [x] M3 推测解码 — 叙事框架完成
- [ ] 逐条精读代码，补充细节问答
- [ ] 模拟面试演练（追问层）

## 待深入的问题

- [ ] `engine_trace.py` 的 `instrument_scheduler` 具体 hook 了哪些函数
- [ ] `heap_policy.py` 的三堆实现（S4）
- [ ] `patches/vllm-v0.8.5-spec.patch` 推测解码接入的具体调用位置
- [ ] `openloop.py` 的 semaphore + deadline 双控机制
- [ ] 各实验的完整数字（需要读 reports/ 下的 JSON）
