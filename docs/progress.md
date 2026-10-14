# DriveServe 进度记录

更新：2026-10-14T22:00:07.653780+08:00（Asia/Shanghai）。当前阶段 **S1 in_progress**；没有已验收阶段、阶段 tag、可面试完整发布版或已证明的性能收益。

## 已完成的具体工作

- 建立 `/hy-netdisk/jq/project/DriveServe` 独立 Git 仓库；保留原始规范包，根目录 `docs/` 为执行记录入口。
- GitHub 关联及首次推送成功：`https://github.com/rexsaaa/DriveServe`。fetch 使用 HTTPS，push 使用仓库专用 SSH key。后续提交采用 `S1 类型：中文说明`，阶段编号不表示验收完成。
- 实现 Python 安装入口、可执行任务 schema、独立规则评分、128 条场景样本及场景组隔离检查。规则 Demo 不调用模型。
- 实现探索性 SSE 客户端，保存原始 chunk、token usage、成功/失败/超时与质量；正式服务性能入口暂未开放。
- 实现 run ID、代码/环境记录、资产 hash 读回、原子 checkpoint、进程身份核验及任务互斥。
- 固定 vLLM v0.8.5 源码 SHA 与压缩包 hash；固定两个 Qwen 模型 revision 和 tokenizer/template metadata。

## 已有验证证据

| 工作 | 实际证据 | 边界 |
|---|---|---|
| 12 项 CPU 测试 | `experiments/runs/20261014T214318+0800-a2cf1c5764` | 代码 SHA `ddc6dc2`，运行时 clean；协议 fixture 不是 vLLM |
| 独立 CPU 环境重建及测试 | `experiments/runs/20261014T214352+0800-fedbc33c34` | 从定义重建 `.venv-verified-rebuild`；没有 GPU 依赖 |
| 真正 SIGTERM 中断、拒绝重复进程、恢复 128 条 | `experiments/runs/20261014T214445+0800-77a7a9a4f4` | 中断时完成 3 条；CPU 小任务，不是训练续训 |
| 双卡实际 matmul 检查 | `experiments/runs/20261014T214446+0800-9ef446501b` | 预装 torch 2.4.0/cu121；不是独立 vLLM 环境验收 |
| 父进程退出后清理子进程组 | `experiments/runs/20261014T215406+0800-96202772ff` | 修复 pip 子进程继续写日志的问题，旧错误和原 hash 保留 |
| 模型预检 | `reports/model-preflight.json`、`reports/model-metadata/` | tokenizer 同 hash、template/BOS/EOS 相同，但配置 vocab_size 不同 |

具体覆盖见 [coverage.md](coverage.md)，累计讲解及验收缺口见 [stages/S1/README.md](stages/S1/README.md)。六条主线没有任何已完整验证项。

## 阶段状态

| 阶段 | 状态 | tag |
|---|---|---|
| S1 基础环境 | in_progress | 无 |
| S2 六线最小完整闭环 | not_started | 无 |
| S3 工程与实验完善 | not_started | 无 |
| S4 至少两个深化专题 | not_started | 无 |
| S5 组合及完整场景验收 | not_started | 无 |
| S6 发布与材料固化 | not_started | 无 |

## 当前环境、资源与资产

- 实测两张 RTX 4090，每张 nvidia-smi 报告 49140 MiB；设备 API 报告的可用总量另见环境记录。驱动 550.163.01，nvcc 12.1，拓扑 NODE。未观察到 NVLink。
- 用户确认按量计费、当前持续开机；无固定 30 天截止日期，也没有授权新增付费资源。优先完成兼容验证，避免以闲置 GPU 等待文档。
- `/hy-netdisk/` 是用户指出的长期云盘候选；容器内检测为 30GiB overlay，没有独立挂载记录。平台保留范围尚未核实，不写成已验证迁移或持久备份。
- `/hy-tmp/` 实测独立 50GiB XFS 临时盘。GPU 环境与下载存放 `/hy-tmp/driveserve/`，可重建；不是持久交付位置。下载器检查剩余容量并保留 3GiB，训练前另做容量预算。
- 源码/配置/小证据进入 Git；大权重本地校验后仍需持久归档。当前没有训练 checkpoint、量化产物或 Nsight trace。
- mihomo 使用现有配置，监听 127.0.0.1:7890；进程 6941，仅当前观测，恢复时重新检测。SSH 私钥在 `/root/.ssh/`，不进 Git；不承诺实例迁移保留。

## 正在运行的任务（恢复时必须核验）

| 任务 | run ID | 位置/入口 |
|---|---|---|
| TP2 真实服务兼容检查 | `20261014T221412+0800-03e7ef970b` | `experiments/runs/<ID>/manifest.json` 包含真实 PID、进程组、30 秒心跳和完整 argv；日志 `command.log` |
| Draft 词表派生导出 | `20261014T221547+0800-bf8c310e33` | 内部导出保留所有原始权重值，增加 128 行零填充；不修改 target，不算训练 |

任务状态以实际 manifest、进程指纹、文件大小为准，不能仅凭本表重启。下载先以 ModelScope HEAD 的 LFS hash 对照固定 HF revision，再以完整文件 SHA256 校验；未校验完的 `.part` 不算模型产物。

## 已遇到的问题与处理

1. 直连 HF 失败：用户授权 mihomo 后 metadata 可获取。初始代理启动存在短暂连接拒绝，重查监听后成功。
2. GitHub HTTPS 无凭据：生成仓库专用 deploy key，用户在 GitHub 添加写权限后 SSH 推送成功；没有公开仓库或更改可见性。
3. 宿主无 ensurepip：采用 `venv --without-pip` + pip `--python`，CPU 独立重建通过。
4. 固定 vLLM 的 V0 Draft 要求词表维度一致，两个模型为 152064/151936。保留模型家族与规模，待真实验证和概率维度适配；未宣称 M3 兼容成功。
5. 大文件代理下载慢：保留完整 wheel 和 partial，切换可核验哈希的镜像；失败 run 留存。未通过缩小模型规避要求。
6. 终止 pip 父进程时孙进程存活，使 command.log 在摘要后继续变化：停止自身遗留进程，保留原 hash 与 reconciliation；记录器现使用独立进程组并核验退出，再封存日志。

## 下一步及验收门槛

1. 已完成两模型校验、依赖冻结和全新 GPU 环境重建；核验当前 TP2 服务与 Draft 导出任务，再继续兼容性检查。
2. 单卡真实服务已运行，开发集 32/32 请求成功、31/32 全字段正确（`20261014T221057+0800-131658d6b3`）。这是小样本冒烟，未热身，不能写成正式性能收益。下一步验证 TP2 和派生 Draft 固定 K。
3. 补充固定 K、词表适配、AWQ 加载格式、FA2 实际后端、图模式及 TP2 的小规模实机预检。没有权重/服务证据不能验收 S1。
4. 验证 GPU 环境可重建并完成持久资产读回；明确存储保留范围。24GB/48GB 通过资源 profile 区分，未测配置不承诺可用。
5. 所有 S1 条件满足后再创建 stage-1-foundation，之后进入 S2 六线实际闭环。

## 最短恢复入口

读取本文件、规范、覆盖和阶段报告；执行 `git status --short --branch`、`git log -5 --oneline`、`python3 -m driveserve status`。对 running 记录核对 PID + boot ID + start_ticks 与子进程组，查看日志，再决定接管或重试。运行记录每 30 秒心跳；CPU 小任务每条 fsync；训练恢复以后另行实现。未部署平台自动唤醒或关机自动恢复。

## 本轮新增运行事实

- 独立栈为 torch 2.6.0+cu124、vLLM 0.8.5、Transformers 4.51.3；`requirements/gpu.lock.txt` 保存 153 个版本。全新重建验证：`20261014T221232+0800-1dbfa02c19`，原目录 sync 记录不冒充全新重建。
- 两模型已下载、哈希验证，并在项目 artifacts 保存第二份本地副本，见 `reports/target-local-copy.json` 与 `reports/draft-local-copy.json`；未做真实迁移。
- 原始 Draft 固定 K 启动实际失败：`20261014T221247+0800-770dbdad58`，命中词表相等断言；不是只根据源码推测。
- 单卡 32 样本中的唯一错误是 speed=24.134m/s、lead=21.104m 应 slow，模型答 proceed；标签和样本均保留，没有删除失败。
