# 历史复现说明：S1–S5迭代入口

当前入口见[复现说明](reproduce.md)。本文件保留各阶段当时的命令与限制，历史状态措辞不代表当前验收状态。

# 当前可复现入口

从仓库根目录执行。CPU 工具仅需要 Python 3.11 和支持 `--python` 的 pip，不要求 CUDA。GPU 独立环境已固定为 torch 2.6.0+cu124 / vLLM 0.8.5 / Transformers 4.51.3，并在新目录重建验证；S1已验收，S2实施中。

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
.venv-cpu/bin/driveserve bench --dataset data/samples/proxy-v1.jsonl --model driveserve-target --endpoint http://127.0.0.1:8000/v1 --limit 16
```

此入口仅供探索性客户端冒烟：闭环线程池、temperature=0、seed=0、未热身、cache 状态未知，正式服务 benchmark 暂时禁用。TTFT 是客户端首个非空内容时间；TPOT 是首/末内容 chunk 时间除以服务端 token 数减一，受 chunk 合并影响；不报告伪造的逐 token ITL。成功请求百分位伴随总请求数、失败/超时数，质量分母为所有尝试。`requests.jsonl` 保存响应 chunk 与原始计时，summary 可重聚合。

小任务恢复（仅演练 CPU 数据任务，不是训练续训）：

```bash
.venv-cpu/bin/driveserve recovery --dataset data/samples/proxy-v1.jsonl --state-dir artifacts/recovery-demo --stop-after 7
.venv-cpu/bin/driveserve recovery --dataset data/samples/proxy-v1.jsonl --state-dir artifacts/recovery-demo
```

每条处理结果 fsync 并原子更新 checkpoint；resume 验证数据 hash 和已完成结果，flock 防止同一任务同时启动。manifest 保存 PID、boot ID、进程启动 ticks；接管先核验实际进程。重试使用新 run ID 并关联 previous_run_id。benchmark 中断必须新测整个单元，不使用该机制拼接性能记录。训练全状态续训已另行实测，见S2累计材料。

每个关键单元完成、任务启动/结束/失败时更新记录。当前任务每条保存；训练每步日志、每8optimizer步及SIGTERM后的当前步结束时保存全状态checkpoint，恢复等同已有实测。日志与状态写入 `experiments/runs/<run_id>`，小证据进入 Git，大资产置于 artifact 存储并保存 hash。`scripts/record_command.py` 可记录长命令的子进程、日志、退出码；不接受含秘密的 argv。

资产读回：`driveserve verify experiments/runs/<实际ID>/manifest.json`。存储读回成功只证明当次可读，不证明关机或迁移后的保留范围。

## GPU 环境与真实服务

已验证的环境在 `/hy-tmp/driveserve/venv-rebuilt`，该路径是临时盘。重建时选不存在的目录；uv 版本固定于 requirements/tools.txt，当前二进制在 `/hy-tmp/driveserve/tools/bin/uv`：

```bash
python3 scripts/bootstrap_gpu.py --env /hy-tmp/driveserve/venv-new --uv /hy-tmp/driveserve/tools/bin/uv --cache /hy-tmp/driveserve/uv-cache
python3 scripts/fetch_models.py --role target --destination /hy-tmp/driveserve/models/target --proxy http://127.0.0.1:7890 --weight-mirror modelscope
python3 scripts/fetch_models.py --role draft --destination /hy-tmp/driveserve/models/draft --proxy http://127.0.0.1:7890 --weight-mirror modelscope
python3 scripts/serve_smoke.py --python /hy-tmp/driveserve/venv-rebuilt/bin/python --model-dir /hy-tmp/driveserve/models/target --port 8000 --memory-fraction 0.4
```

下载固定 revision，ModelScope 权重先检查 LFS hash，再验证完整文件；.part 不算完成。服务启动也核对模型 hash。等 service.log 出现 Application startup complete 后，在另一终端执行下面命令，并将 SERVICE_RUN 替换成刚打印的目录名：

```bash
.venv-cpu/bin/python -m driveserve bench --dataset data/samples/proxy-v1.jsonl --endpoint http://127.0.0.1:8000/v1 --model driveserve-target --concurrency 2 --limit 32 --split dev --service-manifest experiments/runs/SERVICE_RUN/manifest.json
python3 scripts/reaggregate.py experiments/runs/CLIENT_RUN
```

所有 profile 为 V0 / FP16 / FA2 配置 / context 2048 / max_num_seqs 4。普通服务开启 APC；加 `--tp 2 --port 8002` 检查 TP2，加 `--graph` 检查 CUDA Graph（未验证 torch.compile）。顺序运行避免争用；不使用这些未热身小样本计算加速收益。检查后对本次 launcher PID 发 SIGTERM，核对进程组退出与日志 hash。

固定 K 需要派生 Draft（不覆盖源目录，不算训练）：

```bash
/hy-tmp/driveserve/venv-rebuilt/bin/python scripts/align_draft_vocab.py --source /hy-tmp/driveserve/models/draft --target /hy-tmp/driveserve/models/target --destination /hy-tmp/driveserve/models/draft-aligned-new
python3 scripts/serve_smoke.py --python /hy-tmp/driveserve/venv-rebuilt/bin/python --model-dir /hy-tmp/driveserve/models/target --draft-dir /hy-tmp/driveserve/models/draft-aligned-new --draft-tokens 3 --port 8001
```

固定 K profile 关闭 APC，不能直接用此处普通服务成绩解释推测加速。AWQ 格式冒烟使用 `fetch_models.py --role awq_smoke` 获取独立目录，然后 `serve_smoke.py --model-role awq_smoke --model-dir 该目录`；上游预量化模型不满足项目自主 AWQ 校准要求。

FA2 数值与 kernel 预检入口是 `/hy-tmp/driveserve/venv-rebuilt/bin/python scripts/fa2_smoke.py`，要求 clean 工作树；它使用 FP32 显式数学参考和 PyTorch profiler，只证明所测上游 kernel 可用，不替代 Nsight 或性能比较。

## OSS 留存

先在本机终端 `oss login`，用 `oss ls` 确认登录。平台截图的 OSS 免费额度为 0；用户已授权按项目需要留存，不设原先的 30GB 限制。`scripts/backup_models_oss.py --help` 提供上传入口，默认先计划、加 `--upload` 才实际上传。本平台个人根为 `oss://`，已验证 destination 为 `oss://DriveServe/s1-models-7b5208b2777b`；inventory 使用已有盘点 JSON，state 和 staging 沿用同一任务路径以续传。可选 `--cap-bytes` 是调用者主动设置的单次限制，默认无固定上限。模型39包与环境快照均已上传并完整读回，完成收据在reports中，不能将 dry-run 视为备份完成。


按收据恢复到新目录（可用 `--include target/config.json` 恢复少量文件；全量恢复需至少约36GB本地空闲空间）：

```bash
python3 scripts/restore_models_oss.py --receipt reports/s1-oss-models-receipt.json --destination /hy-tmp/driveserve/restored-models --include target/config.json --include target/tokenizer_config.json --report artifacts/oss/restore-probe.json
```

省略 `--include` 会恢复清单全部文件。脚本验证归档与成员 SHA256 后写入，拒绝覆盖 hash 不同的已有文件；相同文件可跳过并重新校验。恢复目录沿用清单角色名 `target`、`draft`、`draft_aligned`、`awq_smoke`。这只是恢复入口，是否实测成功看对应 report/run。完整收据已进入reports。CUDA 原型复现另见 [rope-cache.md](rope-cache.md)。


环境本体完成收据是 `reports/s1-environment-receipt.json`，归档内含snapshot-manifest.json与venv目录，逐文件hash清单的Git副本是reports/s1-environment-inventory.json.gz。可用 `oss cp` 按收据object取回并比对sha256；跨宿主/路径优先重建，不把带绝对链接和editable路径的venv复制描述成万能迁移。S1已在当前实例独立重建GPU环境；真实迁移尚未发生。

双副本冒烟：用 `serve_smoke.py --stage S2 --devices 0 --port 8000 --memory-fraction 0.4` 和 `--devices 1 --port 8003 --memory-fraction 0.4` 分别启动（其余python/model-dir参数同前）；两者就绪后用 `scripts/dual_replica_smoke.py --service-manifest 第一份manifest --service-manifest 第二份manifest`。客户端轮询分配，原始请求记录保留replica和endpoint；这是开发冒烟，公平部署比较另做。

显存迁移配置参考：当前约47.5GiB卡已测fraction0.40；若迁移到约23.5GiB卡，可从fraction约0.80、context2048、maxseq4、eager开始重新做服务/显存检查，使Target预算仍约19GiB。Draft还会增加整进程占用，真实24GB卡尚未验证；不要在24GB卡机械沿用0.40或把比例当硬限额。


S2六条主线的累计回放入口见 [S2 replay](stages/S2/replay.md)，包括三个隔离overlay、真实训练/续训、三组AWQ、CUDA与匹配HTTP部署；普通 `driveserve bench` 仍是早期探索性入口，正式矩阵使用专用脚本。
