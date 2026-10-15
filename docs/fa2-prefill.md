# FA2 Prefill 实测

代码 `1436607`，run `20261014T235957+0800-280a7d5829`。固定 FP16、causal、Q28/KV4、D128，使用 vLLM FA2 与 PyTorch原生flash SDPA（明确启用GQA）比较，双方均由profiler实际捕获flash kernel。没有用故意关闭flash的数学实现来构造性能优势。

所有batch内所有输出与独立显式FP32矩阵乘法/softmax参考比较，双方最大绝对误差均为0.0012522，atol=rtol=0.003。参考显式展开GQA，不隐式调用SDPA。

CUDA Event环绕每图10次调用，20个样本、随机配对顺序、热身和同步；编译、分配和profiler排除在计时外。数值为中位数μs：

| Batch | 输入长度 | vLLM FA2 | PyTorch flash SDPA |
|---:|---:|---:|---:|
| 1 | 128 | 9.224 | 8.949 |
| 1 | 512 | 35.104 | 35.251 |
| 1 | 1024 | 86.208 | 86.078 |
| 1 | 2048 | 265.227 | 268.982 |
| 4 | 128 | 12.774 | 12.557 |
| 4 | 512 | 70.566 | 70.725 |
| 4 | 1024 | 223.645 | 226.590 |
| 4 | 2048 | 816.411 | 830.483 |

这组结果总体接近，不能据此宣称自研Attention加速。两者都复用上游flash能力；测量只包含独立固定形状Attention，没有整个模型、HTTP、KV写入或scheduler。小差异需要独立重复后再判断；后台OSS传输在运行。完整kernel名称、原始320个样本、每个序列误差和16份profiler trace在run目录。

```bash
/hy-tmp/driveserve/venv-rebuilt/bin/python scripts/benchmark_fa2.py
```

需clean工作树。Nsight整模型时间线与这些CUDA Event实验分别报告，见 [engine-diagnostics.md](engine-diagnostics.md)。后续公平部署对照见deployments.md。
