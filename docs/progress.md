# DriveServe 进度记录

更新：2026-10-14T22:48:56.344711+08:00（Asia/Shanghai）。当前阶段 **S1 verification_pending**；尚无已验收阶段或 tag。主要实机兼容检查已完成，持久备份等待 OSS 登录与实际上传读回。没有六线完整发布版或已证明的性能提升。

## 本轮结果与证据

| 工作 | 证据 | 结论和边界 |
|---|---|---|
| 12 项 CPU 检查与独立重建 | `20261014T214318+0800-a2cf1c5764`、`20261014T214352+0800-fedbc33c34` | schema、评分、SSE、失败分母、资产篡改、PID 复用等基础检查通过 |
| 实际中断恢复 | `20261014T214445+0800-77a7a9a4f4` | SIGTERM 时完成 3 条，重复启动被拒绝，恢复到 128 条；非训练续训 |
| 独立 GPU 栈全新重建 | `20261014T221232+0800-1dbfa02c19` | torch 2.6.0+cu124 / vLLM 0.8.5 / Transformers 4.51.3；153 项锁，pip check 与双卡算术通过 |
| 普通单卡服务 | `20261014T221057+0800-131658d6b3` | 32/32 成功，JSON 32/32，全字段正确 31/32；开发冒烟 |
| TP2 服务 | `20261014T221618+0800-9dac230faf`；`reports/s1-tp2-smoke.json` | 32/32 成功、31/32 正确；P2P 不可用，自定义 all-reduce 关闭；无 TP 加速结论 |
| 固定 K=3 | `20261014T221829+0800-04533a6845`；`reports/s1-fixed-k-smoke.json` | 派生 Draft 输出与普通贪心 32/32 文本一致；没有训练或自适应 K |
| CUDA Graph 固定代码复测 | `20261014T223225+0800-b5f3eb5448` / 客户端 `20261014T223323+0800-0940ab2015` | clean SHA `95e48c3`；捕获 1/2/4，32/32 成功、31/32 正确；仅 V0 CUDA Graph，未测 torch.compile |
| 实际 FA2 kernel | `20261014T223106+0800-ba33e0ae35`；`reports/s1-fa2-smoke.json` | 长度 127/512、FP16、28Q/4KV 头、head_dim=128；FP32 数学参考通过；最大绝对误差 0.0009933 / 0.0010126；PyTorch profiler 捕获 flash forward，不替代 Nsight |
| 上游 AWQ 格式加载 | `20261014T223430+0800-34c643f968` / 客户端 `20261014T223537+0800-a2fa74210b` | W4A16 / group128 / 原生 AWQ，32/32 成功、30/32 正确；不是个人校准，不是公平速度对照 |
| 模型资产读回盘点 | `reports/s1-model-assets.json` | 四组模型 27,023,473,848 字节；原 Target/Draft 第二份本地副本也完整 SHA256 通过；尚无云端读回收据 |

TP2、Graph 和 AWQ 新格式客户端的 `requests.jsonl` + `measurement.json` 重新聚合与 summary 完全一致。所有误判保留。服务结束后受控 SIGTERM，其 interrupted 状态不替代关联客户端的成功判定。Graph 早期 dirty 探索保留于 `reports/s1-graph-smoke.json`，后续 clean 复测另存，不覆盖原记录。

## 阶段和覆盖

| 阶段 | 状态 | tag |
|---|---|---|
| S1 基础环境 | verification_pending | 无 |
| S2 六线最小闭环 | not_started（允许实现准备） | 无 |
| S3 工程与实验完善 | not_started | 无 |
| S4 至少两个深化专题 | not_started | 无 |
| S5 组合及完整场景验收 | not_started | 无 |
| S6 发布与材料固化 | not_started | 无 |

[coverage.md](coverage.md) 的 27 项尚无 validated；兼容预检不能代替引擎插桩、缓存/调度、自适应 K、实际蒸馏、AWQ 校准、自定义 CUDA 和完整部署实验。累计讲解见 [stages/S1/README.md](stages/S1/README.md)，接入准备见 [s2-implementation-plan.md](s2-implementation-plan.md)。

## 环境与资产

- GPU：两张 RTX 4090，nvidia-smi 各 49140MiB；API 总量另见 run 环境。驱动 550.163.01，系统 nvcc 12.1；独立 torch 为 cu124。拓扑 NODE，无 NVLink；TP2 实际 P2P 检查失败。
- GPU 环境：`/hy-tmp/driveserve/venv`；全新重建环境 `/hy-tmp/driveserve/venv-rebuilt`。原系统 torch 2.4.0+cu121 未修改。vLLM 上游 v0.8.5 / `ba41cc90e8ef7f236347b2f1599eec2cbb9e1f0d`，当前没有核心补丁。
- 实机 profile：V0、FP16、context2048、max_num_seqs4；普通单卡 Graph 用 0.4 显存比例，TP2 每卡 0.4，固定 K 单卡 0.55，AWQ 单卡 0.3。固定 K 当前预算超过 24GiB，24GB 配置仍需调整与验证；没有声称在真实 24GB 卡通过。
- 存储：`/hy-tmp` 50GiB XFS 临时盘，最近约剩 16GiB；项目路径为 30GiB overlay，最近约剩 11GiB。平台截图证实内网存储有同主机共享范围，但当前实例接入未核实，详见 [storage.md](storage.md)。
- 用户按量使用 GPU、保持开机，无固定截止日；没有新增算力授权。**已明确授权新增最多 30GB OSS 存储**，按截图单价估计新增最多约 0.288 元/天；等待用户终端 `oss login`，只读检查目前 401，不在聊天接收凭据。
- 源码/配置/小证据推送至 `https://github.com/rexsaaa/DriveServe`；作者 jq，提交使用中文且标明阶段，按相关实现、验证和文档成组提交，不改写历史。
- mihomo 已用现有配置运行，代理 127.0.0.1:7890；不修改 Codex 连接或认证。SSH 私钥不进入仓库。

## 任务状态与下一步

当前服务、下载和客户端均已结束；恢复时仍须核对 manifest 和实际 PID，不能仅相信此表。OSS 备份尚未启动，脚本和容量计划已准备，确认登录后再只读确定专用前缀。

1. 固定本轮代码/报告，核验终态 run 的资产 hash 并推送；完成受控服务停止检查。
2. OSS 登录成功后，在授权 30GB 内运行分包上传→下载读回→内容 hash 校验，原子保存收据；中断按同一前缀和 state 续传，不创建第二套收费副本。
3. 补齐持久资产条件及 S1 清单审阅后才打 stage-1-foundation；随后推进六条主线实际闭环，不把备份授权当作备份完成。

## 问题和处理记录

- GitHub HTTPS 缺少凭据：用户添加仓库专用写入 deploy key 后，SSH 443 推送已成功；未更改仓库可见性。
- HF 代理间歇超时：ModelScope 权重先比对固定 HF LFS hash，再校验完整文件；AWQ 两次失败保留 `20261014T221831+0800-aad02709a2`、`20261014T223107+0800-70552fa616`；续传成功 `20261014T223250+0800-e81b31d0e3`，不重复下载完整权重。
- 原 Draft 的 vocab152064/151936 不同，真实固定 K 启动失败 `20261014T221247+0800-770dbdad58`；派生导出仅增 128 行零 embedding，338 个原张量值逐项不变。见 ADR 0002，不算训练或概率完全等价。
- 终止 pip 父进程曾留下孙进程继续写日志：旧 hash 与 reconciliation 保留，记录器已改为监督整个进程组，实测 `20261014T215406+0800-96202772ff`。
- AWQ 比普通模型多误判一条 `proxy-v1-20261014-dev-0003-01`；两者共享的错误为 `dev-0002-02`。不删失败，不用教师输出替换独立规则标签。

## 最短恢复入口

读 AGENTS、规范、本文件、覆盖矩阵及阶段报告；执行 `git status --short --branch`、`git log -5 --oneline`、`python3 -m driveserve status`。running 记录核对 PID + boot_id + start_ticks；命令包装器每 30 秒心跳，服务记录器当前无周期心跳。CPU 任务每条 fsync；OSS 每包读回后原子写收据；训练恢复以后另验。未部署自动开机或平台自动唤醒。
