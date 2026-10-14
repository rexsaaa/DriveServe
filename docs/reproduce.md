# 当前可复现入口

从仓库根目录执行。CPU 工具仅需要 Python 3.11 和支持 `--python` 的 pip，不要求 CUDA。当前 GPU 软件栈尚未锁定为已验证发布环境。

```bash
python3 scripts/bootstrap_cpu.py --env .venv-cpu --proxy http://127.0.0.1:7890
.venv-cpu/bin/driveserve data --output data/samples/proxy-v1.jsonl
.venv-cpu/bin/driveserve demo --dataset data/samples/proxy-v1.jsonl
.venv-cpu/bin/python -m unittest discover -s tests -v
.venv-cpu/bin/driveserve doctor
```

代理参数可省略；代理服务需要已运行。`demo` 输出清楚标注 rule-oracle，不调用任何模型。已有数据如与生成结果不同会拒绝覆盖，须另建版本。项目没有系统依赖自动安装或平台自动开机功能。

当前宿主预装 torch 的设备检查（不等于项目 GPU 环境验收）：

```bash
python3 -m driveserve gpu-smoke
```

真实 OpenAI 兼容服务启动后可以运行客户端；当前不会自动替你启动 vLLM，也不将失败或本地协议 fixture 视为服务成功：

```bash
.venv-cpu/bin/driveserve bench --dataset data/samples/proxy-v1.jsonl --model Qwen/Qwen2.5-7B-Instruct --endpoint http://127.0.0.1:8000/v1 --limit 16
```

此入口仅供探索性客户端冒烟：闭环线程池、temperature=0、seed=0、未热身、cache 状态未知，正式服务 benchmark 暂时禁用。TTFT 是客户端首个非空内容时间；TPOT 是首/末内容 chunk 时间除以服务端 token 数减一，受 chunk 合并影响；不报告伪造的逐 token ITL。成功请求百分位伴随总请求数、失败/超时数，质量分母为所有尝试。`requests.jsonl` 保存响应 chunk 与原始计时，summary 可重聚合。

小任务恢复（仅演练 CPU 数据任务，不是训练续训）：

```bash
.venv-cpu/bin/driveserve recovery --dataset data/samples/proxy-v1.jsonl --state-dir artifacts/recovery-demo --stop-after 7
.venv-cpu/bin/driveserve recovery --dataset data/samples/proxy-v1.jsonl --state-dir artifacts/recovery-demo
```

每条处理结果 fsync 并原子更新 checkpoint；resume 验证数据 hash 和已完成结果，flock 防止同一任务同时启动。manifest 保存 PID、boot ID、进程启动 ticks；接管先核验实际进程。重试使用新 run ID 并关联 previous_run_id。benchmark 中断必须新测整个单元，不使用该机制拼接性能记录。训练以后另行实现优化器/随机状态续训。

每个关键单元完成、任务启动/结束/失败时更新记录。当前任务每条保存；未来长训练计划每 5 分钟状态心跳、每 15 分钟或每个 epoch 保存可恢复 checkpoint，实际实现后验证；这不是已部署承诺。日志与状态写入 `experiments/runs/<run_id>`，小证据进入 Git，大资产置于 artifact 存储并保存 hash。`scripts/record_command.py` 可记录长命令的子进程、日志、退出码；不接受含秘密的 argv。

资产读回：`driveserve verify experiments/runs/<实际ID>/manifest.json`。存储读回成功只证明当次可读，不证明关机或迁移后的保留范围。
