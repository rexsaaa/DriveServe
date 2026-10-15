# S2 AWQ 实测与配置选择

三组自主校准已导出并实际加载；固定 KV 计时、总预算容量及局部误差由 `scripts/analyze_awq.py` 从原始记录重新聚合，见 [机器报告](../reports/s2-awq.json)。M4 的完整持久留存与阶段验收仍须核对收据。

## 相同输入、固定 512 KV 块的单次 GPU 独占测试

FP16/eager、maxseq4、context1536，128 dev+9边界共137请求，全部完成。每个模型独占GPU0，GPU1空闲；后台OSS上传/下载仍在运行。没有独立重复，不声明稳定性能或P99。计量是35个barrier wave墙钟之和，不含加载与热身；各模型输出长度不同，因此不能只按token/s说等工作量加速。

| 模型 | 业务正确/128 | 总输出tokens | 秒数 | 输出token/s | 业务平均TTFT ms | 业务观测TPOT ms |
|---|---:|---:|---:|---:|---:|---:|
| fp16/None | 121 | 2968 | 17.5901 | 168.73 | 88.356 | 17.119 |
| general/128 | 118 | 3841 | 18.5961 | 206.55 | 126.416 | 14.614 |
| domain/128 | 121 | 3841 | 18.5402 | 207.17 | 126.376 | 14.606 |
| domain/64 | 121 | 3274 | 18.0751 | 181.13 | 126.954 | 14.601 |

group128总量约3841tokens，而FP16为2968；领域128总完成时间18.5402秒比FP16的17.5901秒更长，即使其token/s更高。四条固定128输出的合成长文本同为512tokens，其平均观测TPOT为FP16 17.074ms、领域128 14.533ms；只有4条且是不同文本，不能推广为业务端到端收益。TPOT是引擎观察时间，不是kernel或逐token ITL。

## 权重、运行显存与容量分开

下表为实际模型state_dict权重相关tensor的逻辑字节和最终Torch计量，单位十进制GB；未把共享storage重复计作物理占用。各模型实际KV均512×16=8192tokens，FP16 KV占469,762,048bytes。

| 模型 | 权重GB | Torch allocated GB | reserved GB | peak allocated GB |
|---|---:|---:|---:|---:|
| fp16/None | 15.2312 | 15.7778 | 16.1879 | 15.9925 |
| general/128 | 5.5707 | 6.0656 | 6.8430 | 6.4850 |
| domain/128 | 5.5707 | 6.0656 | 6.8430 | 6.4850 |
| domain/64 | 5.6982 | 6.1931 | 6.9143 | 6.6125 |

group128权重15,231,233,024→5,570,747,392bytes，减少63.4255%；固定KV的Torch allocated减少61.5557%。nvidia-smi对应独占GPU0进程最终15900→6988MiB，包含CUDA运行时与allocator保留，不能用它替代权重大小；宿主PID与容器PID不同，原始查询保留。

W4打包196个线性层，group128中qweight3,262,644,224bytes、qzeros25,489,408、scales101,957,632；非量化weight2,180,398,080及bias258,048bytes仍高精度。具体高精度tensor名单保存在JSON。group64的scale与zero翻倍，权重增加127,447,040bytes。

同样gpu_memory_utilization=0.5容量实验：FP16分配10,780块=172,480token槽位、KV9,890,693,120bytes；领域128分配21,144块=338,304token槽位、KV19,399,704,576bytes。公式每token=2(K/V)×28层×4KV头×128维×2bytes=57,344bytes。两组Torch allocated约25GB，总占用没有按权重比例下降，因为自动KV消耗剩余空间。此时GPU1在校准，时间不作为性能对照；没有将全KV槽位同时填满做并发容量验收。

## 校准误差与选择

每来源16384tokens，0/13/27层各7个模块、每模块256输入；局部失真定义与事前规则见[协议](awq-protocol.md)。

| 来源/group | 21模块平均relative MSE | 前层 | 中层 | 后层 | safetensors文件bytes |
|---|---:|---:|---:|---:|---:|
| domain/128 | 0.00336435 | 0.00248196 | 0.00489716 | 0.00271393 | 5570828760 |
| general/128 | 0.00351609 | 0.00265257 | 0.00529180 | 0.00260391 | 5570828760 |
| domain/64 | 0.00256786 | 0.00202945 | 0.00390224 | 0.00177189 | 5698275808 |

领域64/128平均误差比0.763256，即下降23.6744%，未达到25%门槛；dev正确数均121，128没有需恢复的FP16正确数损失。通用128正确118较低。按冻结规则保留领域128作为S2量化候选，FP16仍为发布默认，待S3质量阈值/独立重复及S5交互确认。group64输出长度不同，吞吐比0.8743只按事前统计口径记录，不能独立解释为kernel变慢。

两类校准局部MSE来自不同输入，不能做同输入因果比较。64与128采样recipe相同，但后层输入也受前层量化影响，仍只是代表性局部敏感性分析，不是全层搜索、held-out损失或真实道路泛化。

## 原始记录与复现

| 类型 | run ID |
|---|---|
| 校准 domain/128 | 20261015T022410+0800-8f072791c4 |
| 校准 general/128 | 20261015T022843+0800-a2b942b160 |
| 校准 domain/64 | 20261015T111741+0800-284a52ba00 |
| 固定KV fp16/None | 20261015T113149+0800-8f78f79b66 |
| 固定KV general/128 | 20261015T113250+0800-3e6d26ce10 |
| 固定KV domain/128 | 20261015T113347+0800-a6bfcde61a |
| 固定KV domain/64 | 20261015T113445+0800-80cc362768 |
| 容量 fp16/None | 20261015T112635+0800-330eac66b8 |
| 容量 domain/128 | 20261015T112738+0800-819e8c611c |

首次容量run `20261015T112504+0800-071f900ac8` 在清单采集时误把Tensor.shape当函数，已保留失败；b9085ab修复元数据访问，新run完整重测。原先通用/领域加载时GPU1并行校准的结果仅作正确性诊断。

```bash
/hy-tmp/driveserve/venv-rebuilt/bin/python scripts/benchmark_speculation.py --mode target --target /hy-tmp/driveserve/models/awq-domain-g128-v1 --quantization awq --purpose timing --dataset data/frozen-v1/dev.jsonl --limit 128
```

容量比较把 `--purpose timing` 换成 `--purpose capacity --automatic-kv`；FP16使用target路径并去掉quantization。其他组替换实际产物目录。需要clean代码和正确的环境/模型/overlay，计时前两卡空闲。重聚合参数由JSON中calibration/inference的run_id给出，只有四个timing run加入 `--timing-eligible`。
