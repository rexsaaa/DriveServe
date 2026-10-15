# 独立 RoPE 与 KV 写入融合原型

这是 S1 留存期间的 S2 实施准备。源码固定于 `72cce3a`，累计阶段状态见stages/S2/acceptance.md。实现、失败重试和原始计时见 [报告](../reports/s2-rope-cache.json)。

## 工作语义与个人实现

`csrc/rope_cache.cu` 自己实现一次 kernel launch：每个 token 一个 block，256 个线程分别旋转 Q/K 的成对维度，并将旋转后的 K 和原 V 写入对应 slot。Q/K 原地更新，V 不变；未分配 slot 不写缓存。没有调用上游融合 kernel。上游复用仅包括语义参考、编译工具和对照算子。

支持 FP16、完整 128 维 NeoX RoPE、Q28/KV4、packed `[T,36,128]`，token 行可有尾部填充；缓存连续布局 `[2,blocks,16|32,4,128]`。positions/slots 为连续 int64；有效写槽必须互异，projection/table/cache 不允许共享存储。检查入口会同步并验证索引；微基准事先验证输入后只计 GPU 工作。其他 dtype、头数、RoPE 变体和 cache 格式未声明支持。

## 对照与正确性

固定 vLLM v0.8.5 的 `RotaryEmbedding.forward_cuda` 调用原地 rotary_embedding，FA 后端随后调用 reshape_and_cache_flash。所测形状与这条路径匹配。上游 Dockerfile 固定 FlashInfer v0.2.1.post2，已按 commit `81277931facec98a9861cf1ed978222394d10753` 检查 rope/page 接口；该版本 RoPE 与 append 分开，fused RoPE attention 的输出工作不同，不能直接放入此算子表。来源、文件 hash 和核查结论在 JSON 报告中；没有声称较新版本也不存在融合。

48 组 CUDA 用例覆盖 token 数 0/1/2/15/16/17/31/32/33/127/512/2048，block16/32、行填充0/128。Q、K/V cache 与上游逐元素一致，未写槽、V 和填充保持不变；PyTorch FP16 中间舍入参考也通过。4 类非法索引被入口拒绝。compute-sanitizer 对 16 组边界子集报告 `ERROR SUMMARY: 0 errors`，不等于所有输入都已穷尽。

首次编译因 Ninja 不在 PATH 失败；保存失败 run，改用环境 bin 在 PATH 前部后编译成功。系统 nvcc12.1、torch2.6.0+cu124、sm89，编译 `-O3 -lineinfo`、MAX_JOBS2。移机须重新编译；未修改系统 torch。

## 初次 CUDA Event 微基准

每张 CUDA Graph 包含 100 次等价操作，每个方案 20 个样本，配对顺序随机，CUDA Event 前后同步；编译、分配、预热和源数据重置在计时外。反复执行会原地继续旋转 Q/K，两方案语义相同；这是缓存热的独立算子测量，不模拟完整服务。OSS 后台传输在运行，20 个样本来自同一进程。

| token 数 | 上游分步中位数 μs | 自定义融合中位数 μs |
|---:|---:|---:|
| 1 | 3.3587 | 2.7443 |
| 8 | 3.4202 | 2.7643 |
| 32 | 3.4714 | 2.7853 |
| 128 | 3.7786 | 2.9389 |
| 512 | 6.9734 | 4.7923 |
| 2048 | 17.7501 | 13.6858 |

这些初次微基准数值只描述本机、本形状和测量方法，不能替代独立重复、端到端服务或 TPOT 结果。原始 240 个样本在对应 run 的 timings.json。

## 复现

在 clean Git 工作树、已固定 GPU 环境中运行：

```bash
env PATH=/hy-tmp/driveserve/venv-rebuilt/bin:"$PATH" /hy-tmp/driveserve/venv-rebuilt/bin/python scripts/check_rope_cache.py --benchmark
python3 scripts/record_command.py --stage S2 --kind rope-cache-memcheck --formal -- env PATH=/hy-tmp/driveserve/venv-rebuilt/bin:"$PATH" /usr/local/cuda/bin/compute-sanitizer --tool memcheck --error-exitcode 99 /hy-tmp/driveserve/venv-rebuilt/bin/python scripts/check_rope_cache.py --quick --sanitizer
```

不要把 sanitizer 与性能测量放在同一运行；前者改变执行成本。
